# Giám sát (Phase 11): một workbook của Azure Monitor đọc log trong Log Analytics, và một cảnh báo gắn với
# buổi diễn tập lỗi. Không thêm agent hay dịch vụ nào: mọi số liệu lấy từ log JSON mà api và job đã ghi sẵn.

variable "alert_email" {
  description = "Địa chỉ nhận email khi cảnh báo nổ. Để trống thì cảnh báo chỉ hiện trong Azure Portal. Chỉ đặt trong terraform.tfvars (đã gitignore)."
  type        = string
  default     = ""
  sensitive   = true

  validation {
    condition     = var.alert_email == "" || can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email phải là một địa chỉ email hoặc để trống."
  }
}

locals {
  transcode_prefix   = "${local.name}-transcode"
  maintenance_prefix = "${local.name}-maintenance"
  worker_memory_gib  = tonumber(trimsuffix(var.worker_memory, "Gi"))

  # Giá niêm yết của Container Apps (Consumption) tại malaysiawest, đọc từ Azure Retail Prices API ngày 2026-11-21.
  # Dùng cho cột ước tính trong workbook; không phải hoá đơn, và chưa trừ phần miễn phí hằng tháng.
  price_vcpu_second = 0.000028
  price_gib_second  = 0.000004
  # Thời gian kéo image và khởi động container trước khi worker chạy (đo được khoảng 20–25 giây); là giả định.
  start_seconds = 25
  # Số lượt xem giả định cho mỗi clip khi ước tính dung lượng tải xuống.
  plays_per_clip = 3

  # Mỗi dòng log của job là một JSON; chỉ lấy các dòng của logger app.pipeline.
  kql_pipeline = <<-KQL
    let pipeline = ContainerAppConsoleLogs_CL
      | where ContainerGroupName_s startswith "${local.transcode_prefix}"
      | extend d = parse_json(Log_s)
      | where tostring(d.logger) == "app.pipeline"
      | extend job_id = tostring(d.job_id), status = tostring(d.status);
  KQL

  kql_clips = <<-KQL
    ${local.kql_pipeline}
    let first_claim = pipeline | where status == "PROCESSING"
      | summarize attempts = max(toint(d.attempt)), queue_age_s = round(min(todouble(d.queue_age_seconds)), 1) by job_id;
    let clips = pipeline | where status == "READY"
      | project ready_at = TimeGenerated, job_id, processing_s = todouble(d.processing_seconds), output_bytes = tolong(d.output_bytes)
      | join kind=leftouter first_claim on job_id
      | extend egress_estimate_bytes = output_bytes * ${local.plays_per_clip},
               compute_usd_estimate = round((${local.start_seconds} + processing_s) * (${var.worker_cpu} * ${local.price_vcpu_second} + ${local.worker_memory_gib} * ${local.price_gib_second}), 6);
  KQL

  # Điều kiện của cảnh báo: một lần chuyển mã hỏng vì lỗi hệ thống. File không hợp lệ đi thẳng tới FAILED và không
  # bao giờ qua RETRYING, nên người dùng tải file sai không làm cảnh báo nổ. Dòng thứ hai bắt trường hợp worker chết
  # không kịp ghi gì: job bảo trì thu hồi lease hết hạn (recovered > 0).
  kql_alert = <<-KQL
    ContainerAppConsoleLogs_CL
    | where (ContainerGroupName_s startswith "${local.transcode_prefix}" and Log_s contains "app.pipeline" and Log_s contains "\"status\": \"RETRYING\"")
        or (ContainerGroupName_s startswith "${local.maintenance_prefix}" and Log_s matches regex "\"recovered\": [1-9]")
  KQL

  workbook_panels = [
    {
      title = "Job chuyển mã theo kết quả, mỗi giờ"
      chart = "barchart"
      query = <<-KQL
        ContainerAppConsoleLogs_CL
        | where ContainerGroupName_s startswith "${local.transcode_prefix}"
        | extend d = parse_json(Log_s)
        | where tostring(d.event) == "worker_outcome"
        | summarize executions = count() by bin(TimeGenerated, 1h), outcome = tostring(d.outcome)
      KQL
    },
    {
      title = "Tổng hợp các clip đã READY (thời gian đo thật; egress và chi phí là ước tính)"
      chart = "table"
      query = <<-KQL
        ${local.kql_clips}
        clips
        | summarize clips = count(), processing_p50_s = round(percentile(processing_s, 50), 2), processing_p95_s = round(percentile(processing_s, 95), 2),
                    queue_age_p50_s = round(percentile(queue_age_s, 50), 1), queue_age_p95_s = round(percentile(queue_age_s, 95), 1),
                    output_bytes_total = sum(output_bytes), egress_estimate_bytes = sum(egress_estimate_bytes),
                    compute_usd_per_clip_estimate = round(avg(compute_usd_estimate), 6)
      KQL
    },
    {
      title = "Từng clip: thời gian chờ trong hàng đợi, thời gian xử lý, dung lượng kết quả"
      chart = "table"
      query = <<-KQL
        ${local.kql_clips}
        clips
        | project ready_at, job_id, attempts, queue_age_s, processing_s, output_bytes, egress_estimate_bytes, compute_usd_estimate
        | order by ready_at desc
      KQL
    },
    {
      title = "Lỗi và lần thử lại (kèm job ID và attempt ID để tra log)"
      chart = "table"
      query = <<-KQL
        ${local.kql_pipeline}
        pipeline
        | where status in ("RETRYING", "FAILED")
        | project TimeGenerated, status, error = tostring(d.error), job_id, attempt_id = tostring(d.attempt_id), execution = ContainerGroupName_s
        | order by TimeGenerated desc
      KQL
    },
    {
      title = "Nối request của API với video và job (request_id -> video_id -> job_id -> trạng thái cuối)"
      chart = "table"
      query = <<-KQL
        ${local.kql_pipeline}
        let last_state = pipeline | summarize arg_max(TimeGenerated, status) by job_id | project job_id, last_status = status, last_seen = TimeGenerated;
        ContainerAppConsoleLogs_CL
        | where ContainerAppName_s == "${local.api_name}"
        | extend d = parse_json(Log_s)
        | where tostring(d.logger) == "app.pipeline" and tostring(d.status) == "QUEUED"
        | project queued_at = TimeGenerated, request_id = tostring(d.request_id), video_id = tostring(d.video_id), job_id = tostring(d.job_id)
        | join kind=leftouter last_state on job_id
        | project queued_at, request_id, video_id, job_id, last_status, last_seen
        | order by queued_at desc
      KQL
    },
    {
      title = "API: số request, lỗi 5xx và p95 thời gian xử lý, mỗi 5 phút (không tính /health)"
      chart = "table"
      query = <<-KQL
        ContainerAppConsoleLogs_CL
        | where ContainerAppName_s == "${local.api_name}"
        | extend d = parse_json(Log_s)
        | where tostring(d.logger) == "app.access" and tostring(d.path) != "/health"
        | summarize requests = count(), errors_5xx = countif(toint(d.status) >= 500), refused_4xx = countif(toint(d.status) between (400 .. 499)),
                    p95_ms = percentile(toint(d.ms), 95) by bin(TimeGenerated, 5m)
        | order by TimeGenerated desc
      KQL
    },
    {
      title = "Job bảo trì: những lần có việc phải làm (thu hồi lease, gửi lại sự kiện, dọn file)"
      chart = "table"
      query = <<-KQL
        ContainerAppConsoleLogs_CL
        | where ContainerGroupName_s startswith "${local.maintenance_prefix}"
        | extend d = parse_json(Log_s)
        | where tostring(d.event) == "maintenance"
        | project TimeGenerated, recovered = toint(d.recovered), published = toint(d.published), work = toint(d.work), uploads = toint(d.uploads), outputs = toint(d.outputs)
        | where recovered + published + work + uploads + outputs > 0
        | order by TimeGenerated desc
      KQL
    },
  ]
}

resource "random_uuid" "workbook" {}

resource "azurerm_application_insights_workbook" "portal" {
  name                = random_uuid.workbook.result
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  display_name        = "Video Portal"
  source_id           = lower(azurerm_log_analytics_workspace.main.id)
  tags                = local.tags

  data_json = jsonencode({
    version = "Notebook/1.0"
    items = concat([{
      type = 1
      name = "intro"
      content = {
        json = join("\n", [
          "## Video Portal",
          "Số liệu lấy từ log JSON của `api` và hai job trong Log Analytics (chậm khoảng 1–3 phút).",
          "- **Đo thật:** thời gian xử lý, thời gian chờ trong hàng đợi, dung lượng kết quả, số request và lỗi.",
          "- **Ước tính, không phải hoá đơn:** egress = dung lượng kết quả x ${local.plays_per_clip} lượt xem giả định; chi phí tính toán mỗi clip = (${local.start_seconds} giây khởi động + thời gian xử lý) x giá niêm yết của ${var.worker_cpu} vCPU và ${local.worker_memory_gib} GiB, chưa trừ phần miễn phí hằng tháng.",
          "- Chi phí cố định (database, registry, load balancer) không nằm trong con số mỗi clip: xem Cost Management.",
        ])
      }
      }], [for index, panel in local.workbook_panels : {
      type = 3
      name = "panel-${index + 1}"
      content = {
        version                 = "KqlItem/1.0"
        title                   = panel.title
        query                   = panel.query
        size                    = 0
        timeContext             = { durationMs = 604800000 }
        queryType               = 0
        resourceType            = "microsoft.operationalinsights/workspaces"
        crossComponentResources = [azurerm_log_analytics_workspace.main.id]
        visualization           = panel.chart
      }
    }])
  })
}

resource "azurerm_monitor_action_group" "ops" {
  count = nonsensitive(var.alert_email) == "" ? 0 : 1

  name                = "${local.name}-ops"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "vportal"
  tags                = local.tags

  email_receiver {
    name                    = "owner"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }
}

# Một cảnh báo, có việc phải làm ngay: lần chuyển mã hỏng vì lỗi hệ thống (worker bị dừng, lỗi storage/queue, lease hết hạn).
# Đánh giá mỗi 5 phút trên cửa sổ 5 phút; log tới Log Analytics chậm 1–3 phút nên thông báo tới sau sự cố khoảng 3–10 phút.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "transcode_failure" {
  name                = "${local.name}-transcode-system-failure"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  display_name        = "Video Portal: transcode attempt failed (system error, retry scheduled)"
  description         = "A transcode attempt ended in RETRYING, or maintenance recovered an expired lease. First action: open the workbook 'Video Portal', panel 'Lỗi và lần thử lại', take the job ID, check that a later attempt reached READY and that the queue and dead-letter queue are empty. If the same job fails 3 times it becomes FAILED and needs a new upload."
  severity            = 2
  enabled             = true
  tags                = local.tags

  scopes                  = [azurerm_log_analytics_workspace.main.id]
  evaluation_frequency    = "PT5M"
  window_duration         = "PT5M"
  auto_mitigation_enabled = true

  criteria {
    query                   = local.kql_alert
    time_aggregation_method = "Count"
    operator                = "GreaterThan"
    threshold               = 0

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  dynamic "action" {
    for_each = azurerm_monitor_action_group.ops[*].id
    content {
      action_groups = [action.value]
    }
  }
}

output "workbook_name" {
  description = "Tên hiển thị của workbook trong Azure Portal (Monitor > Workbooks, hoặc Log Analytics workspace > Workbooks)."
  value       = azurerm_application_insights_workbook.portal.display_name
}

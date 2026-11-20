# ---------- Pub/Sub: topic chính, push tới dispatcher, dead-letter ----------

resource "google_pubsub_topic" "jobs" {
  name       = "video-jobs"
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_topic" "dead" {
  name       = "video-jobs-dead"
  depends_on = [google_project_service.apis]
}

# Push có OIDC. Tối đa 5 lần giao; sau đó message sang dead-letter thay vì retry vô hạn.
resource "google_pubsub_subscription" "jobs_push" {
  name                       = "video-jobs-push"
  topic                      = google_pubsub_topic.jobs.id
  ack_deadline_seconds       = 60
  message_retention_duration = "86400s"

  expiration_policy {
    ttl = ""
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "300s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead.id
    max_delivery_attempts = 5
  }

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.app["dispatcher"].uri}/internal/dispatch"

    oidc_token {
      service_account_email = google_service_account.sa["pubsub-push"].email
      audience              = google_cloud_run_v2_service.app["dispatcher"].uri
    }
  }
}

# Giữ message chết 7 ngày để người vận hành xem lại; topic không có subscription sẽ làm mất message.
resource "google_pubsub_subscription" "dead_pull" {
  name                       = "video-jobs-dead-pull"
  topic                      = google_pubsub_topic.dead.id
  message_retention_duration = "604800s"

  expiration_policy {
    ttl = ""
  }
}

# ---------- Cloud Scheduler: gọi relay và reconcile định kỳ (mặc định tạm dừng) ----------

resource "google_cloud_scheduler_job" "relay" {
  name             = "video-relay-tick"
  region           = var.region
  schedule         = var.relay_schedule
  time_zone        = "Etc/UTC"
  paused           = var.scheduler_paused
  attempt_deadline = "60s"
  depends_on       = [google_project_service.apis]

  retry_config {
    retry_count = 0
  }

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.app["relay"].uri}/internal/relay"

    oidc_token {
      service_account_email = google_service_account.sa["scheduler"].email
      audience              = google_cloud_run_v2_service.app["relay"].uri
    }
  }
}

resource "google_cloud_scheduler_job" "reconcile" {
  name             = "video-reconcile-tick"
  region           = var.region
  schedule         = var.relay_schedule
  time_zone        = "Etc/UTC"
  paused           = var.scheduler_paused
  attempt_deadline = "60s"
  depends_on       = [google_project_service.apis]

  retry_config {
    retry_count = 0
  }

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.app["dispatcher"].uri}/internal/reconcile"

    oidc_token {
      service_account_email = google_service_account.sa["scheduler"].email
      audience              = google_cloud_run_v2_service.app["dispatcher"].uri
    }
  }
}

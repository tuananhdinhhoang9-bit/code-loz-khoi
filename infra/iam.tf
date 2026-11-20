# Mỗi workload một service account riêng, không tạo key JSON.
locals {
  service_accounts = {
    api         = "Video portal API"
    relay       = "Video portal outbox relay"
    dispatcher  = "Video portal dispatcher"
    worker      = "Video portal FFmpeg worker"
    pubsub-push = "Pub/Sub push to dispatcher"
    scheduler   = "Cloud Scheduler to relay and dispatcher"
  }

  pubsub_agent = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
  bucket_path  = "projects/_/buckets/${google_storage_bucket.media.name}/objects"
}

resource "google_service_account" "sa" {
  for_each     = local.service_accounts
  account_id   = "video-${each.key}"
  display_name = each.value
  depends_on   = [google_project_service.apis]
}

# ---------- Mật khẩu DB: chỉ 4 workload cần kết nối PostgreSQL ----------

resource "google_secret_manager_secret_iam_member" "db_password" {
  for_each  = toset(["api", "relay", "dispatcher", "worker"])
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.sa[each.key].email}"
}

# ---------- Bucket: đọc cả bucket, ghi theo prefix; objectCreator không ghi đè/xoá được ----------

resource "google_storage_bucket_iam_member" "read" {
  for_each = toset(["api", "worker"])
  bucket   = google_storage_bucket.media.name
  role     = "roles/storage.objectViewer"
  member   = "serviceAccount:${google_service_account.sa[each.key].email}"
}

resource "google_storage_bucket_iam_member" "api_write_input" {
  bucket = google_storage_bucket.media.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.sa["api"].email}"

  condition {
    title      = "input-prefix-only"
    expression = "resource.name.startsWith(\"${local.bucket_path}/input/\")"
  }
}

resource "google_storage_bucket_iam_member" "worker_write_output" {
  bucket = google_storage_bucket.media.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.sa["worker"].email}"

  condition {
    title      = "output-prefixes-only"
    expression = "resource.name.startsWith(\"${local.bucket_path}/staging/\") || resource.name.startsWith(\"${local.bucket_path}/published/\")"
  }
}

# API tự ký signed URL bằng signBlob trên chính service account của nó (không cần key).
resource "google_service_account_iam_member" "api_signs_urls" {
  service_account_id = google_service_account.sa["api"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.sa["api"].email}"
}

# ---------- Pub/Sub ----------

resource "google_pubsub_topic_iam_member" "relay_publishes" {
  topic  = google_pubsub_topic.jobs.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.sa["relay"].email}"
}

# Service agent của Pub/Sub cần các quyền này để chuyển message sang dead-letter và ký OIDC khi push.
resource "google_pubsub_topic_iam_member" "agent_publishes_dead" {
  topic  = google_pubsub_topic.dead.name
  role   = "roles/pubsub.publisher"
  member = local.pubsub_agent
}

resource "google_pubsub_subscription_iam_member" "agent_subscribes" {
  subscription = google_pubsub_subscription.jobs_push.name
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_agent
}

resource "google_service_account_iam_member" "agent_signs_push" {
  service_account_id = google_service_account.sa["pubsub-push"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = local.pubsub_agent
}

# ---------- Cloud Run: ai được gọi ai ----------

# Cổng công khai duy nhất. Ứng dụng tự kiểm tra Firebase ID token ở mọi API riêng tư.
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  name     = google_cloud_run_v2_service.app["api"].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "pubsub_invokes_dispatcher" {
  name     = google_cloud_run_v2_service.app["dispatcher"].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.sa["pubsub-push"].email}"
}

resource "google_cloud_run_v2_service_iam_member" "scheduler_invokes" {
  for_each = toset(["relay", "dispatcher"])
  name     = google_cloud_run_v2_service.app[each.key].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.sa["scheduler"].email}"
}

# Dispatcher chỉ được chạy đúng job worker, kèm override (truyền job_id cho từng lần chạy).
resource "google_cloud_run_v2_job_iam_member" "dispatcher_runs_worker" {
  name     = google_cloud_run_v2_job.worker.name
  location = var.region
  role     = "roles/run.jobsExecutorWithOverrides"
  member   = "serviceAccount:${google_service_account.sa["dispatcher"].email}"
}

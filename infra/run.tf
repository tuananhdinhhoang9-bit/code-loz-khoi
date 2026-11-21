locals {
  worker_job_name = "video-worker"

  # Biến môi trường chung. Tên các biến GCS/PubSub/job là hợp đồng đề xuất cho Phase 08.
  app_env = {
    APP_ENV              = "gcp"
    GOOGLE_CLOUD_PROJECT = var.project_id
    GCP_REGION           = var.region
    POSTGRES_HOST        = google_sql_database_instance.main.private_ip_address
    POSTGRES_PORT        = "5432"
    POSTGRES_DB          = google_sql_database.app.name
    POSTGRES_USER        = google_sql_user.app.name
    FIREBASE_PROJECT_ID  = local.firebase_project_id
    FIREBASE_WEB_API_KEY = var.firebase_web_api_key
    GCS_BUCKET           = google_storage_bucket.media.name
    PUBSUB_TOPIC         = google_pubsub_topic.jobs.name
    WORKER_JOB_NAME      = local.worker_job_name
  }

  # Ba service dùng chung image Flask, khác nhau về danh tính, ingress và giới hạn.
  services = {
    api = {
      ingress       = "INGRESS_TRAFFIC_ALL"
      max_instances = 2
      concurrency   = 20
    }
    relay = {
      ingress       = "INGRESS_TRAFFIC_INTERNAL_ONLY"
      max_instances = 1
      concurrency   = 1
    }
    dispatcher = {
      ingress       = "INGRESS_TRAFFIC_INTERNAL_ONLY"
      max_instances = 1
      concurrency   = 10
    }
  }
}

resource "google_cloud_run_v2_service" "app" {
  for_each            = local.services
  name                = "video-${each.key}"
  location            = var.region
  ingress             = each.value.ingress
  deletion_protection = var.deletion_protection

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.db_password,
    google_secret_manager_secret_iam_member.db_password,
  ]

  template {
    service_account                  = google_service_account.sa[each.key].email
    timeout                          = "60s"
    max_instance_request_concurrency = each.value.concurrency

    scaling {
      min_instance_count = 0
      max_instance_count = each.value.max_instances
    }

    # Direct VPC egress: chỉ lưu lượng tới IP riêng (Cloud SQL) đi qua VPC, không cần Cloud NAT.
    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"

      network_interfaces {
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.run.id
      }
    }

    containers {
      image = var.app_image

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      dynamic "env" {
        for_each = local.app_env
        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name = "POSTGRES_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }
    }
  }
}

# Mỗi lần chạy xử lý đúng 1 video. max_retries = 0: retry do DB lease/attempt quyết định,
# tránh Cloud Run tự retry chồng lên retry của Pub/Sub và của ứng dụng.
resource "google_cloud_run_v2_job" "worker" {
  name                = local.worker_job_name
  location            = var.region
  deletion_protection = var.deletion_protection

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.db_password,
    google_secret_manager_secret_iam_member.db_password,
  ]

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = google_service_account.sa["worker"].email
      timeout         = "300s"
      max_retries     = 0

      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"

        network_interfaces {
          network    = google_compute_network.main.id
          subnetwork = google_compute_subnetwork.run.id
        }
      }

      containers {
        image = var.worker_image

        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
          }
        }

        dynamic "env" {
          for_each = local.app_env
          content {
            name  = env.key
            value = env.value
          }
        }

        env {
          name = "POSTGRES_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.db_password.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }
}

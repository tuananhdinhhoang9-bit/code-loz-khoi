locals {
  apis = [
    "artifactregistry.googleapis.com",
    "cloudscheduler.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
  ]

  firebase_project_id = var.firebase_project_id != "" ? var.firebase_project_id : var.project_id
}

data "google_project" "this" {}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  service            = each.value
  disable_on_destroy = false
}

# ---------- Mạng: 1 VPC, 1 subnet cho Direct VPC egress, dải riêng cho Cloud SQL ----------

resource "google_compute_network" "main" {
  name                    = "video-portal-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}

resource "google_compute_subnetwork" "run" {
  name                     = "video-portal-run"
  region                   = var.region
  network                  = google_compute_network.main.id
  ip_cidr_range            = "10.10.0.0/24"
  private_ip_google_access = true
}

# Private Services Access: Cloud SQL nhận IP riêng trong dải này, không có IP công khai.
resource "google_compute_global_address" "sql_range" {
  name          = "video-portal-sql-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "sql" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.sql_range.name]
  depends_on              = [google_project_service.apis]
}

# ---------- Cloud SQL PostgreSQL: 1 instance zonal, tính phí liên tục khi đang chạy ----------

resource "google_sql_database_instance" "main" {
  name                = "video-portal-db"
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = var.deletion_protection
  depends_on          = [google_service_networking_connection.sql]

  settings {
    tier              = var.db_tier
    edition           = "ENTERPRISE"
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 10
    disk_autoresize   = false

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.main.id
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = false

      backup_retention_settings {
        retained_backups = 3
      }
    }
  }
}

# ABANDON: khi destroy chỉ cần xoá instance, tránh lỗi drop user đang sở hữu bảng.
resource "google_sql_database" "app" {
  name            = "video_portal"
  instance        = google_sql_database_instance.main.name
  deletion_policy = "ABANDON"
}

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "google_sql_user" "app" {
  name            = "video_portal"
  instance        = google_sql_database_instance.main.name
  password        = random_password.db.result
  deletion_policy = "ABANDON"
}

resource "google_secret_manager_secret" "db_password" {
  secret_id  = "video-portal-db-password"
  depends_on = [google_project_service.apis]

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db.result
}

# ---------- Bucket riêng tư: input/ staging/ published/ ----------

resource "google_storage_bucket" "media" {
  name                        = "${var.project_id}-video-portal"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  depends_on                  = [google_project_service.apis]

  # Chỉ xoá staging/. Output đã publish phải nằm ở published/, nếu không sẽ bị xoá sau 1 ngày.
  lifecycle_rule {
    condition {
      age            = 1
      matches_prefix = ["staging/"]
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age = 1
    }
    action {
      type = "AbortIncompleteMultipartUpload"
    }
  }

  dynamic "cors" {
    for_each = length(var.cors_origins) > 0 ? [1] : []
    content {
      origin          = var.cors_origins
      method          = ["GET", "HEAD", "PUT"]
      response_header = ["Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"]
      max_age_seconds = 3600
    }
  }
}

# ---------- Artifact Registry cho image app và worker ----------

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "video-portal"
  format        = "DOCKER"
  description   = "Images for the video portal app and FFmpeg worker"
  depends_on    = [google_project_service.apis]
}

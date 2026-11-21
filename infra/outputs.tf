output "api_url" {
  description = "URL HTTPS cong khai cua video-api."
  value       = google_cloud_run_v2_service.app["api"].uri
}

output "media_bucket" {
  value = google_storage_bucket.media.name
}

output "image_repository" {
  description = "Tien to de docker push image."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "db_private_ip" {
  value = google_sql_database_instance.main.private_ip_address
}

output "db_password_secret" {
  description = "Ten secret, khong phai gia tri mat khau."
  value       = google_secret_manager_secret.db_password.secret_id
}

output "service_accounts" {
  value = { for key, sa in google_service_account.sa : key => sa.email }
}

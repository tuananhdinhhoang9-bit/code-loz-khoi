# Không output nào chứa secret. Mật khẩu DB chỉ nằm trong Key Vault và trong state cục bộ.

output "resource_group" {
  value = azurerm_resource_group.main.name
}

output "registry_login_server" {
  description = "Đẩy hai image lên đây trước khi đặt deploy_apps = true."
  value       = azurerm_container_registry.main.login_server
}

output "default_url" {
  description = "Địa chỉ HTTPS mặc định của trang (có ngay khi app api được tạo)."
  value       = local.default_origin
}

output "oidc_redirect_uris" {
  description = "Khai báo các địa chỉ này làm redirect URI kiểu Single-page application trong app registration."
  value       = [for origin in local.origins : "${origin}/"]
}

output "storage_account" {
  value = azurerm_storage_account.media.name
}

output "servicebus_namespace" {
  value = azurerm_servicebus_namespace.main.name
}

output "postgres_server" {
  description = "Chỉ phân giải được bên trong VNet."
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "job_names" {
  description = "Tên hai job (rỗng khi deploy_apps = false)."
  value       = concat(azurerm_container_app_job.transcode[*].name, azurerm_container_app_job.maintenance[*].name)
}

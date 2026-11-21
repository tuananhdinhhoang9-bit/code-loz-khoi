# Danh tính của workload: hai user-assigned managed identity, không có khoá hay client secret nào.
#   api    - app api: ký SAS, đọc/xoá blob, gửi message.
#   worker - hai job (transcode, maintenance): đọc nguồn, ghi output, nhận/gửi message; KEDA dùng nó để đếm message.
# Danh sách role suy ra từ code và tài liệu, CHƯA được kiểm chứng trên Azure thật (xem README).

resource "azurerm_user_assigned_identity" "api" {
  name                = "${local.name}-api"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags
}

resource "azurerm_user_assigned_identity" "worker" {
  name                = "${local.name}-worker"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags
}

locals {
  identities = {
    api    = azurerm_user_assigned_identity.api.principal_id
    worker = azurerm_user_assigned_identity.worker.principal_id
  }
}

# Kéo image từ registry.
resource "azurerm_role_assignment" "acr_pull" {
  for_each = local.identities

  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = each.value
}

# Đọc đúng một secret (mật khẩu DB), không phải cả vault.
resource "azurerm_role_assignment" "secret_reader" {
  for_each = local.identities

  scope                = azurerm_key_vault_secret.db_password.resource_versionless_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = each.value
}

# Blob: chỉ trong container media. Cần "Owner" (không phải "Contributor") vì xoá video phải xoá từng phiên bản cũ của blob,
# và thao tác deleteBlobVersion chỉ có trong role này. Phạm vi là một container, không phải cả storage account.
resource "azurerm_role_assignment" "blob_data" {
  for_each = local.identities

  scope                = azurerm_storage_container.media.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = each.value
}

# Chỉ api ký SAS: lấy user delegation key là thao tác ở mức storage account.
resource "azurerm_role_assignment" "blob_delegator" {
  scope                = azurerm_storage_account.media.id
  role_definition_name = "Storage Blob Delegator"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

# api chỉ gửi message (relay outbox sau khi commit).
resource "azurerm_role_assignment" "queue_sender" {
  scope                = azurerm_servicebus_queue.jobs.id
  role_definition_name = "Azure Service Bus Data Sender"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

# worker nhận, gửi (relay), dead-letter; KEDA đếm message bằng chính identity này, việc đó cần quyền quản trị queue.
# Giả định chưa kiểm chứng: thử thu hẹp về Data Receiver + Data Sender sau khi job đã chạy thật.
resource "azurerm_role_assignment" "queue_worker" {
  scope                = azurerm_servicebus_queue.jobs.id
  role_definition_name = "Azure Service Bus Data Owner"
  principal_id         = azurerm_user_assigned_identity.worker.principal_id
}

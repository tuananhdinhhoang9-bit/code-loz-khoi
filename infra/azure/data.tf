# Dữ liệu: PostgreSQL, Blob Storage riêng tư, hàng đợi Service Bus, Key Vault giữ mật khẩu DB.

# ---------- PostgreSQL ----------

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                = "${local.name}-pg-${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  version             = var.db_version
  sku_name            = var.db_sku
  storage_mb          = var.db_storage_mb

  # Private access: không có địa chỉ public; chỉ tài nguyên trong VNet tới được.
  delegated_subnet_id           = azurerm_subnet.db.id
  private_dns_zone_id           = azurerm_private_dns_zone.db.id
  public_network_access_enabled = false

  administrator_login    = "video_portal"
  administrator_password = random_password.db.result

  backup_retention_days = 7
  tags                  = local.tags

  # Azure tự chọn availability zone; không để Terraform coi đó là thay đổi.
  lifecycle {
    ignore_changes = [zone]
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.db]
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = "video_portal"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# ---------- Blob Storage ----------

resource "azurerm_storage_account" "media" {
  name                     = "${local.name}${local.suffix}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  min_tls_version          = "TLS1_2"

  # Không blob nào công khai được, và không ai dùng account key được: mọi truy cập đi qua Entra ID hoặc SAS do identity ký.
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true

  blob_properties {
    # version ID của blob nguồn là `source_generation` của job (app/storage_blob.py).
    versioning_enabled = true

    # Trình duyệt PUT file và phát video thẳng từ Blob Storage bằng SAS.
    cors_rule {
      allowed_origins    = local.origins
      allowed_methods    = ["GET", "HEAD", "PUT"]
      allowed_headers    = ["content-type", "x-ms-blob-type", "x-ms-blob-content-type", "range"]
      exposed_headers    = ["Content-Length", "Content-Range", "Accept-Ranges", "Content-Type"]
      max_age_in_seconds = 600
    }
  }

  tags = local.tags
}

resource "azurerm_storage_container" "media" {
  name                  = "media"
  storage_account_id    = azurerm_storage_account.media.id
  container_access_type = "private"
}

# Lưới an toàn: phiên bản cũ của blob (bị ghi đè hoặc xoá dở) tự mất sau 7 ngày, kể cả khi ứng dụng không xoá được.
resource "azurerm_storage_management_policy" "media" {
  storage_account_id = azurerm_storage_account.media.id

  rule {
    name    = "expire-old-versions"
    enabled = true

    filters {
      blob_types = ["blockBlob"]
    }

    actions {
      version {
        delete_after_days_since_creation = 7
      }
    }
  }
}

# ---------- Service Bus ----------

resource "azurerm_servicebus_namespace" "main" {
  name                = "${local.name}-sb-${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  # Chỉ nhận xác thực bằng Entra ID (managed identity); khoá SAS của namespace bị tắt.
  local_auth_enabled = false
  tags               = local.tags
}

resource "azurerm_servicebus_queue" "jobs" {
  name         = "transcode-jobs"
  namespace_id = azurerm_servicebus_namespace.main.id

  # Khoá tối đa của Service Bus là 5 phút; worker gia hạn khoá trong lúc job chạy (app/queue_servicebus.py).
  lock_duration = "PT5M"
  # Quá 10 lần giao, message tự sang dead-letter queue có sẵn của queue này.
  max_delivery_count                   = 10
  dead_lettering_on_message_expiration = true
}

# ---------- Key Vault ----------

resource "azurerm_key_vault" "main" {
  name                = "${local.name}-kv-${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
  tags                       = local.tags
}

# Người chạy Terraform cần quyền ghi secret vào vault vừa tạo (vault dùng RBAC, không dùng access policy).
resource "azurerm_role_assignment" "deployer_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_secret" "db_password" {
  name         = "postgres-password"
  value        = random_password.db.result
  key_vault_id = azurerm_key_vault.main.id
  content_type = "PostgreSQL password of the application user"

  depends_on = [azurerm_role_assignment.deployer_secrets]
}

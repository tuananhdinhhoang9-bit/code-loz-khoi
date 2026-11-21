terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# State lưu cục bộ (đã gitignore). State chứa mật khẩu DB nên không được commit hay chia sẻ.
# Quyền truy cập Azure lấy từ `az login` của người chạy; subscription lấy từ biến môi trường ARM_SUBSCRIPTION_ID.
# Không có ID subscription/tenant, khoá hay client secret nào trong file của thư mục này.
provider "azurerm" {
  features {
    key_vault {
      # Mặc định giữ vault đã xoá 7 ngày (khôi phục được); chỉ xoá hẳn khi dọn dẹp sau demo.
      purge_soft_delete_on_destroy = var.allow_destroy_data
    }
  }

  # Storage account tắt account key, nên Terraform cũng phải dùng Entra ID khi đọc/ghi cấu hình blob.
  storage_use_azuread = true

  # Terraform không tự đăng ký resource provider của subscription (kể cả lúc `plan`): việc đó làm bằng lệnh
  # `az provider register` ở README, một lần, trước lần `apply` đầu tiên.
  resource_provider_registrations = "none"
}

data "azurerm_client_config" "current" {}

# Tên của storage account, Key Vault, registry, Service Bus và máy chủ PostgreSQL phải duy nhất toàn Azure.
resource "random_string" "suffix" {
  length  = 6
  lower   = true
  upper   = false
  numeric = true
  special = false
}

locals {
  name   = var.project
  suffix = random_string.suffix.result
  tags = {
    Project   = var.project
    ManagedBy = "terraform"
  }

  api_name = "${var.project}-api"
  # Hostname mặc định của app api có sẵn HTTPS: <tên app>.<miền mặc định của environment>.
  default_origin = "https://${local.api_name}.${azurerm_container_app_environment.main.default_domain}"
  # Origin được phép gọi thẳng Blob Storage (CORS) và là redirect URI của đăng nhập OIDC.
  origins = concat([local.default_origin], var.domain_name == "" ? [] : ["https://${var.domain_name}"])
}

resource "azurerm_resource_group" "main" {
  name     = "${local.name}-rg"
  location = var.location
  tags     = local.tags
}

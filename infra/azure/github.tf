# GitHub Actions đẩy image lên registry mà không có mật khẩu hay khoá nào: workflow của đúng kho và đúng nhánh
# đổi token OIDC của GitHub lấy token Azure của identity `deploy` (federated credential).
# Gói Azure for Students không cho dùng ACR Tasks và không tạo được máy ảo để build, nên image được build trên GitHub.

variable "github_repository" {
  description = "Kho GitHub được phép đẩy image, dạng owner/name. Để trống thì không tạo identity này."
  type        = string
  default     = ""

  validation {
    condition     = var.github_repository == "" || can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository phải có dạng owner/name."
  }
}

variable "github_subject" {
  description = "Chuỗi `sub` đầy đủ trong token OIDC của GitHub cho nhánh main. GitHub hiện phát dạng có kèm ID số: repo:owner@<id>/name@<id>:ref:refs/heads/main (đọc từ thông báo lỗi AADSTS700213 của lần chạy đầu). Để trống thì dùng dạng cũ suy ra từ github_repository."
  type        = string
  default     = ""
}

resource "azurerm_user_assigned_identity" "deploy" {
  count = var.github_repository == "" ? 0 : 1

  name                = "${local.name}-deploy"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags
}

# Chỉ workflow chạy trên nhánh main của kho này mới đổi được token; pull request và nhánh khác thì không.
resource "azurerm_federated_identity_credential" "github_main" {
  count = var.github_repository == "" ? 0 : 1

  name                = "github-main"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.deploy[0].id
  issuer              = "https://token.actions.githubusercontent.com"
  subject             = var.github_subject != "" ? var.github_subject : "repo:${var.github_repository}:ref:refs/heads/main"
  audience            = ["api://AzureADTokenExchange"]
}

# Quyền duy nhất: đẩy (và kéo) image trong registry này. Quyền cập nhật app và job thuộc Phase 12.
resource "azurerm_role_assignment" "deploy_push" {
  count = var.github_repository == "" ? 0 : 1

  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPush"
  principal_id         = azurerm_user_assigned_identity.deploy[0].principal_id
}

output "github_client_id" {
  description = "Giá trị của secret AZURE_CLIENT_ID trong kho GitHub (ID công khai của identity, không phải mật khẩu)."
  value       = one(azurerm_user_assigned_identity.deploy[*].client_id)
}

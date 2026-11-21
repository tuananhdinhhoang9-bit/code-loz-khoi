variable "project" {
  description = "Tiền tố tên tài nguyên: chữ thường và số, bắt đầu bằng chữ (dùng cả cho storage account và registry nên không có gạch nối)."
  type        = string
  default     = "videoportal"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,11}$", var.project))
    error_message = "project chỉ gồm 3-12 chữ thường/số và bắt đầu bằng chữ."
  }
}

variable "location" {
  description = "Region của Azure. Subscription sinh viên có thể chỉ cho phép một số region: kiểm tra trước khi plan."
  type        = string
  default     = "southeastasia"
}

variable "domain_name" {
  description = "Tên miền riêng của trang (ví dụ video.example.com), hoặc để trống khi chỉ dùng hostname mặc định của Azure. Chỉ dùng cho CORS; gắn tên miền vào app làm bằng lệnh ở README."
  type        = string
  default     = ""

  validation {
    condition     = var.domain_name == "" || can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.domain_name))
    error_message = "domain_name phải là tên miền chữ thường, không kèm https:// hay dấu gạch chéo."
  }
}

# ---------- Triển khai theo hai bước ----------

variable "deploy_apps" {
  description = "false: chỉ tạo hạ tầng nền (registry, database, storage...). true: tạo thêm app api và hai job. Chỉ bật sau khi hai image đã được đẩy lên registry với đúng image_tag."
  type        = bool
  default     = false
}

variable "image_tag" {
  description = "Tag của image video-portal-api và video-portal-worker trong registry (thường là commit SHA)."
  type        = string
  default     = "initial"
}

# ---------- Kích thước (ảnh hưởng chi phí) ----------

variable "db_sku" {
  description = "SKU của PostgreSQL flexible server. B_Standard_B1ms là nhỏ nhất (1 vCore, 2 GiB)."
  type        = string
  default     = "B_Standard_B1ms"
}

variable "db_version" {
  description = "Phiên bản PostgreSQL. Bản VPS và bộ test đang dùng 18."
  type        = string
  default     = "18"
}

variable "db_storage_mb" {
  description = "Dung lượng lưu trữ của PostgreSQL (MB). Chỉ tăng được, không giảm được."
  type        = number
  default     = 32768
}

variable "api_min_replicas" {
  description = "0: app api co về 0 khi không ai dùng (không tốn tiền, request đầu phải chờ khởi động). 1: luôn có một replica."
  type        = number
  default     = 0
}

variable "api_cpu" {
  type    = number
  default = 0.5
}

variable "api_memory" {
  type    = string
  default = "1Gi"
}

variable "worker_cpu" {
  description = "CPU của một lần chạy job chuyển mã."
  type        = number
  default     = 1
}

variable "worker_memory" {
  type    = string
  default = "2Gi"
}

variable "transcode_timeout_seconds" {
  description = "Thời gian tối đa của FFmpeg cho một video. Thời hạn của cả lần chạy job (replica timeout) lớn hơn số này 300 giây."
  type        = number
  default     = 300
}

variable "maintenance_cron" {
  description = "Lịch (UTC) của job maintenance: thu hồi lease hết hạn, gửi lại outbox còn sót, dọn dẹp."
  type        = string
  default     = "*/5 * * * *"
}

variable "max_upload_bytes" {
  description = "Giới hạn kích thước một file tải lên (byte). Đề bài: 50 MB."
  type        = number
  default     = 50000000
}

variable "log_retention_days" {
  type    = number
  default = 30
}

# ---------- Đăng nhập ----------

variable "auth_provider" {
  description = "oidc: Microsoft Entra External ID (cần các biến oidc_* bên dưới). local: tài khoản nội bộ trong PostgreSQL, là phương án lùi nếu không tạo được external tenant."
  type        = string
  default     = "oidc"

  validation {
    condition     = contains(["oidc", "local"], var.auth_provider)
    error_message = "auth_provider phải là oidc hoặc local."
  }
}

# Các giá trị dưới đây lấy từ tài liệu OpenID configuration của external tenant và từ app registration.
# Chúng đều công khai (không phải secret), nhưng vẫn chỉ đặt trong terraform.tfvars (đã gitignore).
variable "oidc_issuer" {
  type    = string
  default = ""
}

variable "oidc_client_id" {
  type    = string
  default = ""
}

variable "oidc_jwks_url" {
  type    = string
  default = ""
}

variable "oidc_authorize_url" {
  type    = string
  default = ""
}

variable "oidc_token_url" {
  type    = string
  default = ""
}

variable "oidc_logout_url" {
  type    = string
  default = ""
}

variable "oidc_email_claim" {
  description = "Claim chứa e-mail trong ID token. Với Entra, `email` là optional claim phải bật trong app registration."
  type        = string
  default     = "email"
}

# ---------- Chỉ bật khi dọn dẹp sau demo ----------

variable "allow_destroy_data" {
  description = "true: cho phép terraform destroy xoá Key Vault ngay (purge) thay vì giữ 7 ngày. Dữ liệu trong database và Blob Storage luôn mất khi destroy."
  type        = bool
  default     = false
}

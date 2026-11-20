variable "region" {
  description = "Region cho mọi tài nguyên. Tài khoản AWS của dự án là một project đặt ở Sydney và từ chối Singapore (2026-11-20)."
  type        = string
  default     = "ap-southeast-2"
}

variable "project" {
  description = "Tiền tố tên tài nguyên: chữ thường, số và gạch nối."
  type        = string
  default     = "video-portal"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,20}$", var.project))
    error_message = "project chỉ gồm chữ thường, số, gạch nối; dài 3-21 ký tự."
  }
}

variable "domain_name" {
  description = "Tên miền của trang, ví dụ video.example.com. DNS do chủ dự án quản lý ngoài AWS."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.domain_name))
    error_message = "domain_name phải là tên miền viết thường, không có https:// hay dấu /."
  }
}

# ---------- Kích thước và số lượng (đều ảnh hưởng chi phí) ----------

variable "api_desired_count" {
  description = "Số task API. Để 0 cho đến khi image đã có trong ECR; 1 khi chạy demo."
  type        = number
  default     = 0
}

variable "worker_desired_count" {
  description = "Số task worker: chỉ 0 hoặc 1 (worker giữ advisory lock, mỗi lúc một video)."
  type        = number
  default     = 0

  validation {
    condition     = contains([0, 1], var.worker_desired_count)
    error_message = "worker_desired_count chỉ được là 0 hoặc 1."
  }
}

variable "image_tag" {
  description = "Tag image trong ECR mà task definition dùng (CI/CD đặt bằng mã commit)."
  type        = string
  default     = "initial"
}

variable "api_cpu" {
  description = "CPU của task API (1024 = 1 vCPU)."
  type        = number
  default     = 256
}

variable "api_memory" {
  description = "RAM của task API, tính bằng MB."
  type        = number
  default     = 512
}

variable "worker_cpu" {
  description = "CPU của task worker (FFmpeg)."
  type        = number
  default     = 1024
}

variable "worker_memory" {
  description = "RAM của task worker, tính bằng MB."
  type        = number
  default     = 2048
}

variable "db_instance_class" {
  description = "Loại máy RDS. Giả định cho demo; kiểm tra giá và gói Free plan trước khi apply."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_engine_version" {
  description = "Phiên bản PostgreSQL trên RDS. Giả định; kiểm tra phiên bản có ở region trước khi apply."
  type        = string
  default     = "17"
}

variable "db_backup_days" {
  description = "Số ngày giữ bản sao lưu tự động của RDS."
  type        = number
  default     = 1
}

variable "max_upload_bytes" {
  description = "Giới hạn kích thước file tải lên (đề bài: 50 MB)."
  type        = number
  default     = 50000000
}

variable "log_retention_days" {
  description = "Số ngày giữ log trong CloudWatch."
  type        = number
  default     = 14
}

# ---------- An toàn dữ liệu khi xoá ----------

variable "deletion_protection" {
  description = "Chặn xoá RDS và Cognito user pool. Bật khi đã có dữ liệu cần giữ."
  type        = bool
  default     = false
}

variable "skip_final_snapshot" {
  description = "true = xoá RDS không chụp snapshot cuối. Chỉ bật khi dọn dẹp sau demo."
  type        = bool
  default     = false
}

variable "force_destroy_bucket" {
  description = "true = cho phép terraform destroy xoá bucket còn file. Chỉ bật khi dọn dẹp sau demo."
  type        = bool
  default     = false
}

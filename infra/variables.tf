variable "project_id" {
  description = "GCP project ID da duoc chu du an phe duyet."
  type        = string

  validation {
    condition     = length(var.project_id) > 0
    error_message = "project_id khong duoc de trong."
  }
}

variable "region" {
  description = "Region cho moi tai nguyen. Kiem tra gia/quota truoc khi apply."
  type        = string
  default     = "asia-southeast1"
}

variable "db_tier" {
  description = "Cloud SQL tier. db-f1-micro la gia dinh cho demo, chua kiem chung gia/quota."
  type        = string
  default     = "db-f1-micro"
}

variable "app_image" {
  description = "Image Flask cho api/relay/dispatcher. Mac dinh la image mau cua Google cho den khi Phase 08 build image that."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "worker_image" {
  description = "Image FFmpeg worker. Mac dinh la image job mau cua Google cho den khi Phase 08 build image that."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/job"
}

variable "firebase_project_id" {
  description = "Firebase project ID. De trong thi dung project_id."
  type        = string
  default     = ""
}

variable "firebase_web_api_key" {
  description = "Firebase Web API key (cau hinh cong khai phia client, khong phai secret)."
  type        = string
  default     = ""
}

variable "cors_origins" {
  description = "Origin duoc phep upload truc tiep len bucket bang signed URL, vi du URL cua video-api."
  type        = list(string)
  default     = []
}

variable "relay_schedule" {
  description = "Lich cron goi relay va reconcile."
  type        = string
  default     = "*/2 * * * *"
}

variable "scheduler_paused" {
  description = "Tam dung Cloud Scheduler cho den khi Phase 08 co endpoint that."
  type        = bool
  default     = true
}

variable "deletion_protection" {
  description = "Chan xoa nham Cloud SQL va Cloud Run. Chi tat khi da duoc dong y destroy."
  type        = bool
  default     = true
}

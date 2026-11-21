terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# State mặc định lưu cục bộ (đã gitignore). State chứa mật khẩu DB nên không được commit/chia sẻ.
provider "google" {
  project = var.project_id
  region  = var.region
}

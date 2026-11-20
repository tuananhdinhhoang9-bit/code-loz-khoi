terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# State lưu cục bộ (đã gitignore). State chứa mật khẩu DB nên không được commit hay chia sẻ.
# Quyền truy cập AWS lấy từ môi trường của người chạy (CloudShell, SSO); không có access key trong file nào.
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name = var.project
  # Tên bucket phải duy nhất toàn cầu và không có dấu chấm (app/main.py kiểm tra điều này).
  bucket = "${var.project}-${data.aws_caller_identity.current.account_id}-${var.region}"
  origin = "https://${var.domain_name}"
  azs    = slice(data.aws_availability_zones.available.names, 0, 2)
}

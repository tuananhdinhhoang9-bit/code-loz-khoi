# Cho GitHub Actions đẩy image lên ECR mà không cần access key: workflow đổi token OIDC của GitHub
# lấy quyền tạm thời của role dưới đây. Chỉ nhánh main của đúng kho `github_repository` dùng được role.
# Để trống `github_repository` thì không tạo gì ở file này.

variable "github_repository" {
  description = "Kho GitHub dạng chủ-kho/tên-kho được phép đẩy image. Để trống nếu chưa dùng GitHub Actions."
  type        = string
  default     = ""

  validation {
    condition     = var.github_repository == "" || can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository phải có dạng chủ-kho/tên-kho, không có https://."
  }
}

locals {
  github_enabled = var.github_repository != "" ? 1 : 0
}

resource "aws_iam_openid_connect_provider" "github" {
  count = local.github_enabled

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_policy_document" "github_assume" {
  count = local.github_enabled

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github[0].arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Chỉ workflow chạy trên nhánh main của kho này; pull request và nhánh khác không lấy được quyền.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_images" {
  count = local.github_enabled

  name                 = "${local.name}-github-images"
  assume_role_policy   = data.aws_iam_policy_document.github_assume[0].json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "github_images" {
  count = local.github_enabled

  # Lệnh đăng nhập ECR không giới hạn được theo kho; nó chỉ cấp token, chưa cho đẩy gì.
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "PushProjectImages"
    actions = [
      "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage", "ecr:DescribeImages",
    ]
    resources = [for repository in aws_ecr_repository.app : repository.arn]
  }
}

resource "aws_iam_role_policy" "github_images" {
  count = local.github_enabled

  name   = "push-images"
  role   = aws_iam_role.github_images[0].id
  policy = data.aws_iam_policy_document.github_images[0].json
}

output "github_images_role_arn" {
  description = "Đặt giá trị này vào biến AWS_ROLE_ARN của kho GitHub (Settings > Secrets and variables > Actions > Variables)."
  value       = one(aws_iam_role.github_images[*].arn)
}

# Dữ liệu: RDS PostgreSQL (metadata, outbox), S3 riêng tư (video), SQS (job) và mật khẩu DB trong Secrets Manager.

# ---------- PostgreSQL ----------

# Mật khẩu sinh ngẫu nhiên, lưu ở Secrets Manager và trong state cục bộ của Terraform (không ở file nào khác).
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "db_password" {
  name        = "${local.name}/db-password"
  description = "Mat khau PostgreSQL cua Video Portal; ECS nap vao task luc khoi dong"
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db.result
}

resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "main" {
  identifier     = local.name
  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "video_portal"
  username = "video_portal"
  password = random_password.db.result

  # Không có địa chỉ public; chỉ security group của API và worker kết nối được.
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period    = var.db_backup_days
  auto_minor_version_upgrade = true
  apply_immediately          = true

  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = "${local.name}-final"
}

# ---------- S3 ----------

resource "aws_s3_bucket" "media" {
  bucket        = local.bucket
  force_destroy = var.force_destroy_bucket
}

resource "aws_s3_bucket_public_access_block" "media" {
  bucket = aws_s3_bucket.media.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Versioning là bắt buộc: VersionId của file gốc chính là source_generation của job (ADR-022).
resource "aws_s3_bucket_versioning" "media" {
  bucket = aws_s3_bucket.media.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "media" {
  bucket = aws_s3_bucket.media.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Trình duyệt tải lên (POST) và phát (GET) thẳng với S3 bằng URL ký sẵn, chỉ từ đúng origin của trang.
resource "aws_s3_bucket_cors_configuration" "media" {
  bucket = aws_s3_bucket.media.id

  cors_rule {
    allowed_origins = [local.origin]
    allowed_methods = ["POST", "GET", "HEAD"]
    allowed_headers = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "media" {
  bucket     = aws_s3_bucket.media.id
  depends_on = [aws_s3_bucket_versioning.media]

  rule {
    id     = "bound-storage"
    status = "Enabled"

    filter {}

    # Phiên bản cũ chỉ xuất hiện khi một object bị ghi đè; không giữ mãi.
    noncurrent_version_expiration {
      noncurrent_days = 7
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

data "aws_iam_policy_document" "media_tls_only" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.media.arn, "${aws_s3_bucket.media.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "media" {
  bucket     = aws_s3_bucket.media.id
  policy     = data.aws_iam_policy_document.media_tls_only.json
  depends_on = [aws_s3_bucket_public_access_block.media]
}

# ---------- SQS ----------

resource "aws_sqs_queue" "dead" {
  name                      = "${local.name}-jobs-dead"
  message_retention_seconds = 1209600 # 14 ngày để người vận hành kịp xem
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "jobs" {
  name                       = "${local.name}-jobs"
  visibility_timeout_seconds = 300    # khớp VISIBILITY_SECONDS trong app/queue_sqs.py
  message_retention_seconds  = 345600 # 4 ngày
  sqs_managed_sse_enabled    = true

  # Giao quá 10 lần mà chưa được ack thì SQS tự chuyển sang dead-letter queue.
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead.arn
    maxReceiveCount     = 10
  })
}

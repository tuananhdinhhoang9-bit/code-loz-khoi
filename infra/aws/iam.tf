# Danh tính của workload: mỗi service một task role riêng, chỉ có quyền nó cần.
# Không có IAM user hay access key nào được tạo ở đây.

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ---------- Execution role: ECS dùng để kéo image, ghi log và nạp mật khẩu DB vào task ----------

resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secret" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.db_password.arn]
  }
}

resource "aws_iam_role_policy" "execution_secret" {
  name   = "read-db-password"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secret.json
}

# ---------- API ----------

resource "aws_iam_role" "api" {
  name               = "${local.name}-api"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "api" {
  # URL ký sẵn mang quyền của chính role này: tải lên chỉ vào inputs/, đọc theo đúng phiên bản.
  statement {
    sid       = "UploadSources"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.media.arn}/inputs/*"]
  }

  statement {
    sid       = "ReadAndDeleteObjects"
    actions   = ["s3:GetObject", "s3:GetObjectVersion", "s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = ["${aws_s3_bucket.media.arn}/inputs/*", "${aws_s3_bucket.media.arn}/outputs/*"]
  }

  # Có ListBucket thì object chưa tồn tại trả 404 (thay vì 403), để API báo đúng "chưa tải lên xong".
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket", "s3:ListBucketVersions"]
    resources = [aws_s3_bucket.media.arn]
  }

  statement {
    sid       = "QueueDepth"
    actions   = ["sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.jobs.arn, aws_sqs_queue.dead.arn]
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "api"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

# ---------- Worker ----------

resource "aws_iam_role" "worker" {
  name               = "${local.name}-worker"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "worker" {
  statement {
    sid       = "ReadObjects"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.media.arn}/inputs/*", "${aws_s3_bucket.media.arn}/outputs/*"]
  }

  statement {
    sid       = "PublishOutputs"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.media.arn}/outputs/*"]
  }

  # Dọn upload bỏ dở và output mồ côi.
  statement {
    sid       = "Cleanup"
    actions   = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = ["${aws_s3_bucket.media.arn}/inputs/*", "${aws_s3_bucket.media.arn}/outputs/*"]
  }

  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket", "s3:ListBucketVersions"]
    resources = [aws_s3_bucket.media.arn]
  }

  statement {
    sid = "JobQueue"
    actions = [
      "sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.jobs.arn]
  }

  statement {
    sid       = "DeadLetterQueue"
    actions   = ["sqs:SendMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.dead.arn]
  }
}

resource "aws_iam_role_policy" "worker" {
  name   = "worker"
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker.json
}

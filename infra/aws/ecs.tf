# Tính toán: hai image trong ECR, một cluster ECS, hai service Fargate (api sau ALB, worker chạy FFmpeg).

resource "aws_ecr_repository" "app" {
  for_each = toset(["api", "worker"])

  name                 = "${local.name}-${each.key}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  for_each = aws_ecr_repository.app

  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Giu 10 image moi nhat"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}

resource "aws_cloudwatch_log_group" "app" {
  for_each = toset(["api", "worker"])

  name              = "/ecs/${local.name}/${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_cluster" "main" {
  name = local.name
}

locals {
  # Cấu hình chung của hai container. Không có secret nào ở đây: mật khẩu DB đi qua `secrets`.
  app_environment = [
    { name = "AWS_REGION", value = var.region },
    { name = "S3_BUCKET", value = aws_s3_bucket.media.bucket },
    { name = "SQS_QUEUE_URL", value = aws_sqs_queue.jobs.url },
    { name = "SQS_DEAD_LETTER_URL", value = aws_sqs_queue.dead.url },
    { name = "COGNITO_USER_POOL_ID", value = aws_cognito_user_pool.main.id },
    { name = "COGNITO_CLIENT_ID", value = aws_cognito_user_pool_client.web.id },
    { name = "POSTGRES_HOST", value = aws_db_instance.main.address },
    { name = "POSTGRES_PORT", value = tostring(aws_db_instance.main.port) },
    { name = "POSTGRES_DB", value = aws_db_instance.main.db_name },
    { name = "POSTGRES_USER", value = aws_db_instance.main.username },
    { name = "MAX_UPLOAD_BYTES", value = tostring(var.max_upload_bytes) },
  ]

  app_secrets = [
    { name = "POSTGRES_PASSWORD", valueFrom = aws_secretsmanager_secret.db_password.arn },
  ]

  log_options = {
    for name in ["api", "worker"] : name => {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.app[name].name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = name
      }
    }
  }
}

# ---------- API ----------

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.api.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name             = "api"
    image            = "${aws_ecr_repository.app["api"].repository_url}:${var.image_tag}"
    essential        = true
    portMappings     = [{ containerPort = 8000, protocol = "tcp" }]
    environment      = local.app_environment
    secrets          = local.app_secrets
    logConfiguration = local.log_options["api"]
  }])
}

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  health_check_grace_period_seconds = 60

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = true # không có NAT: task cần IP public để gọi dịch vụ AWS; không cổng nào mở ra Internet
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  # Bản mới không khoẻ thì ECS tự quay về bản trước.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_lb_listener.https]
}

# ---------- Worker ----------

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.worker.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "worker"
    image     = "${aws_ecr_repository.app["worker"].repository_url}:${var.image_tag}"
    essential = true
    environment = concat(local.app_environment, [
      { name = "FFMPEG_THREADS", value = "1" },
      { name = "TRANSCODE_TIMEOUT_SECONDS", value = "300" },
    ])
    secrets          = local.app_secrets
    logConfiguration = local.log_options["worker"]
    # ECS gửi SIGTERM rồi chờ tối đa 60 giây. Job chưa xong sẽ bị kill và được cứu bằng lease + reconcile.
    stopTimeout = 60
  }])
}

resource "aws_ecs_service" "worker" {
  name            = "worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  # Chỉ một worker giữ advisory lock: dừng task cũ rồi mới chạy task mới.
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.worker.id]
    assign_public_ip = true
  }
}

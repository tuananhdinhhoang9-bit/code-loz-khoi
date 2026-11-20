# Không output nào chứa secret. Mật khẩu DB chỉ nằm trong Secrets Manager và state.

output "site_url" {
  description = "Địa chỉ trang sau khi DNS trỏ về ALB."
  value       = local.origin
}

output "alb_dns_name" {
  description = "Tạo bản ghi CNAME cho tên miền trỏ về giá trị này."
  value       = aws_lb.main.dns_name
}

output "acm_validation_records" {
  description = "Bản ghi CNAME cần thêm ở nhà đăng ký tên miền để ACM cấp chứng chỉ."
  value = [for option in aws_acm_certificate.site.domain_validation_options : {
    name  = option.resource_record_name
    type  = option.resource_record_type
    value = option.resource_record_value
  }]
}

output "ecr_repositories" {
  description = "Nơi đẩy image api và worker."
  value       = { for name, repository in aws_ecr_repository.app : name => repository.repository_url }
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "ecs_services" {
  value = { api = aws_ecs_service.api.name, worker = aws_ecs_service.worker.name }
}

output "media_bucket" {
  value = aws_s3_bucket.media.bucket
}

output "job_queue_url" {
  value = aws_sqs_queue.jobs.url
}

output "dead_letter_queue_url" {
  value = aws_sqs_queue.dead.url
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "db_endpoint" {
  description = "Địa chỉ nội bộ của RDS; không truy cập được từ Internet."
  value       = aws_db_instance.main.address
}

output "db_password_secret_arn" {
  description = "ARN của secret (không phải giá trị)."
  value       = aws_secretsmanager_secret.db_password.arn
}

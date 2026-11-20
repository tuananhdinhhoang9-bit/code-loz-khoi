# Điểm vào duy nhất của hệ thống: Application Load Balancer, HTTPS bằng chứng chỉ ACM cho tên miền của dự án.

resource "aws_lb" "main" {
  name               = local.name
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  drop_invalid_header_fields = true
  enable_deletion_protection = var.deletion_protection
}

resource "aws_lb_target_group" "api" {
  name                 = "${local.name}-api"
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = aws_vpc.main.id
  deregistration_delay = 30

  # /health có chạy một câu truy vấn DB: task mất kết nối DB sẽ bị rút khỏi ALB.
  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

# Chứng chỉ được xác minh bằng một bản ghi CNAME. DNS của tên miền nằm ngoài AWS nên bản ghi này
# do chủ dự án tự thêm ở nhà đăng ký (giá trị nằm trong output `acm_validation_records`).
resource "aws_acm_certificate" "site" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# Chờ đến khi ACM xác minh xong. `terraform apply` sẽ đứng ở đây cho tới khi bản ghi DNS được thêm.
resource "aws_acm_certificate_validation" "site" {
  certificate_arn = aws_acm_certificate.site.arn
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.site.certificate_arn

  # Trên VPS hai header này do Caddy thêm; trên AWS do ALB thêm.
  routing_http_response_strict_transport_security_header_value = "max-age=31536000"
  routing_http_response_server_enabled                         = false

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

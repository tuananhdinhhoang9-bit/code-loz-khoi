# Mạng: 2 subnet public (ALB và task Fargate) + 2 subnet private (RDS), trải trên 2 AZ.
# Không có NAT Gateway (chi phí cố định): task có IP public để gọi ECR, S3, SQS, Cognito,
# nhưng security group không cho Internet gọi vào task. RDS không có đường ra/vào Internet.

resource "aws_vpc" "main" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = local.name }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = { Name = local.name }
}

resource "aws_subnet" "public" {
  count = 2

  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  availability_zone = local.azs[count.index]

  tags = { Name = "${local.name}-public-${count.index + 1}" }
}

resource "aws_subnet" "private" {
  count = 2

  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index + 10)
  availability_zone = local.azs[count.index]

  tags = { Name = "${local.name}-private-${count.index + 1}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${local.name}-public" }
}

resource "aws_route_table_association" "public" {
  count = 2

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Subnet private dùng route table mặc định của VPC: chỉ có đường nội bộ, không có đường ra Internet.

# ---------- Security group ----------

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "Internet toi ALB: chi 443 va 80 (80 chi chuyen huong sang HTTPS)"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP, chi de chuyen huong"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Toi task API"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  tags = { Name = "${local.name}-alb" }
}

resource "aws_security_group" "api" {
  name        = "${local.name}-api"
  description = "Task API: chi ALB goi vao cong 8000"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Tu ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "HTTPS toi dich vu AWS (ECR, S3, Secrets Manager, Cognito, CloudWatch)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "PostgreSQL trong VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  tags = { Name = "${local.name}-api" }
}

resource "aws_security_group" "worker" {
  name        = "${local.name}-worker"
  description = "Task worker: khong nhan ket noi vao"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "HTTPS toi dich vu AWS (ECR, S3, SQS, Secrets Manager, CloudWatch)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "PostgreSQL trong VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  tags = { Name = "${local.name}-worker" }
}

resource "aws_security_group" "db" {
  name        = "${local.name}-db"
  description = "RDS: chi task API va worker ket noi duoc"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL tu API va worker"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id, aws_security_group.worker.id]
  }

  tags = { Name = "${local.name}-db" }
}

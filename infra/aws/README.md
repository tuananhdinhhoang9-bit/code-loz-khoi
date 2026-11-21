# Terraform cho AWS (Phase 08)

**Trạng thái (2026-11-21): đã `fmt`, `init`, `validate` và `plan`. Mới `apply` đúng một tài nguyên là chứng chỉ ACM (`aws_acm_certificate.site`, đã `ISSUED`); phần còn lại CHƯA `apply` (`Plan: 56 to add, 0 to change, 0 to destroy`, gồm cả 3 tài nguyên của `github.tf`).** Chưa có database, bucket, hàng đợi, user pool, load balancer hay service nào trên AWS. Thiết kế: `docs/AWS_ARCHITECTURE.md`, quyết định: ADR-021, ADR-023. Các file `.tf` ở thư mục cha `infra/` là bản GCP đã lưu trữ, không liên quan.

## Tạo ra những gì (48 khối `resource`)

| File | Nội dung |
| --- | --- |
| `network.tf` | VPC, 2 subnet public (ALB, task), 2 subnet private (RDS), internet gateway, 4 security group. Không có NAT Gateway |
| `alb.tf` | Application Load Balancer, target group (`/health`), chứng chỉ ACM, listener 80 (chuyển hướng) và 443 |
| `ecs.tf` | 2 kho ECR, cluster ECS, task definition và service `api`, `worker` (Fargate), log group |
| `data.tf` | RDS PostgreSQL, bucket S3 riêng tư (versioning, CORS, chặn truy cập công khai, chỉ TLS), SQS + dead-letter queue, secret mật khẩu DB |
| `auth.tf` | Cognito user pool, app client cho trình duyệt, nhóm `admin` |
| `iam.tf` | Execution role, task role riêng cho `api` và `worker` |

## Trước khi chạy

1. Cần quyền AWS ở dòng lệnh. Dùng AWS CloudShell (đã đăng nhập sẵn) hoặc đăng nhập SSO; **không** tạo access key cho tài khoản root và không ghi key vào file nào.
2. `cp terraform.tfvars.example terraform.tfvars` rồi điền `domain_name`.
3. Region là `ap-southeast-2` (Sydney): tài khoản AWS của dự án là một "project" đặt ở đó và từ chối đăng nhập vào Singapore. Đăng nhập dòng lệnh: `aws login --region ap-southeast-2`.
4. Đã kiểm tra bằng lệnh chỉ đọc (2026-11-20): `db.t4g.micro` đặt được cho PostgreSQL 18.6 và 17.11 ở Sydney; tài khoản chưa có tài nguyên nào ngoài VPC mặc định.
5. Chưa kiểm chứng (chỉ lộ ra khi `apply`): gói Free plan có cho tạo các dịch vụ này không; tài khoản đang trong giai đoạn xác minh có bị chặn tạo tài nguyên nào không; RDS có nhận `engine_version = "18"` (chỉ ghi phiên bản chính) không.

## Trình tự (mỗi lệnh `apply` phải được chủ dự án đồng ý trước)

```bash
terraform init
terraform plan -out=tfplan          # đọc kỹ; chưa tạo gì

# Bước 1: chỉ tạo chứng chỉ để lấy bản ghi xác minh
terraform apply -target=aws_acm_certificate.site
terraform output acm_validation_records
#   -> thêm bản ghi CNAME này ở nhà đăng ký tên miền

# Bước 2: tạo phần còn lại. Lệnh sẽ chờ ở aws_acm_certificate_validation đến khi DNS có hiệu lực.
terraform apply

# Bước 3: đẩy hai image lên ECR với tag T, chạy init-db một lần, rồi bật service
terraform apply -var image_tag=T -var api_desired_count=1 -var worker_desired_count=1

# Bước 4: trỏ tên miền về ALB
terraform output alb_dns_name       # -> bản ghi CNAME của tên miền con
```

Hai service bắt đầu với `desired_count = 0` vì ECR còn trống; không có task nào chạy (và tính tiền) cho đến bước 3.

## Chi phí (giá On-Demand tại `ap-southeast-2` Sydney, AWS Price List công bố 2026-11-11 đến 2026-11-19, tra ngày 2026-11-20)

| Thành phần | Đơn giá | Chạy liên tục 730 giờ/tháng |
| --- | --- | --- |
| ALB | 0,0252 USD/giờ (+ 0,008 USD mỗi LCU-giờ) | 18,40 USD + LCU |
| RDS `db.t4g.micro` Single-AZ | 0,025 USD/giờ | 18,25 USD |
| RDS lưu trữ gp3 20 GB | 0,138 USD/GB-tháng | 2,76 USD |
| Task `api` 0,25 vCPU + 0,5 GB | 0,04856 USD/vCPU-giờ, 0,00532 USD/GB-giờ | 10,80 USD |
| Task `worker` 1 vCPU + 2 GB | như trên | 43,22 USD |
| 4 địa chỉ IPv4 public (2 của ALB, 2 của task) | 0,005 USD/giờ mỗi địa chỉ | 14,60 USD |
| **Cộng các mục trên** | khoảng 0,144 USD/giờ | **khoảng 108 USD/tháng** |

(Bảng trước đó tính cho Singapore: Fargate 0,05056 và 0,00553 USD, tổng khoảng 110 USD/tháng; các đơn giá còn lại giống nhau ở hai region.)

Chưa tính (chưa tra giá, dự kiến nhỏ với tải demo): S3, SQS, CloudWatch Logs, Secrets Manager, ECR, bản sao lưu RDS, lưu lượng ra Internet, LCU của ALB. Số liệu trên là công thức minh hoạ, không phải hoá đơn; tính lại bằng [AWS Pricing Calculator](https://calculator.aws/) trước khi `apply`. Cảnh báo ngân sách không phải là trần chi tiêu.

Cách giảm khi không demo: `worker_desired_count = 0` và `api_desired_count = 0` dừng tiền Fargate và IP của task; ALB, RDS và IP của ALB vẫn tính tiền cho tới khi `terraform destroy`.

## Dọn dẹp (cần chủ dự án đồng ý; mất dữ liệu)

```bash
terraform apply -var skip_final_snapshot=true -var force_destroy_bucket=true   # cho phép xoá DB và bucket còn file
terraform destroy
```

Sau đó kiểm tra lại trong Console (đúng region) rằng không còn ALB, RDS, snapshot, bucket, log group, secret (secret bị giữ 7 ngày trước khi xoá hẳn) và image ECR nào.

## State

State lưu cục bộ trong thư mục này (`terraform.tfstate`, đã gitignore) và **chứa mật khẩu DB**. Không commit, không chia sẻ. `.terraform.lock.hcl` thì phải commit.

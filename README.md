# Video Portal — bản chạy trên AWS (nhánh `aws`)

Đề tài số 10 “Video Upload and Processing Portal” (`references/10_video_upload_and_processing_portal.pdf`). Nhánh này là bản dùng **database và các dịch vụ của AWS**, đúng với yêu cầu của đề bài. Bản chạy trên một máy Windows Server nằm ở nhánh [`vps`](../../tree/vps); nhánh `main` là nơi phát triển và chứa cả hai.

## Mọi thứ nằm ở đâu

| Việc | Bản AWS dùng | Cấu hình của container |
| --- | --- | --- |
| Web và API | Application Load Balancer (HTTPS, chứng chỉ ACM) trước service `api` trên ECS Fargate | `TRUSTED_PROXY` |
| Database | RDS for PostgreSQL 18, `db.t4g.micro`, trong subnet private | `POSTGRES_*`, mật khẩu lấy từ Secrets Manager |
| Lưu video gốc, MP4, ảnh thu nhỏ | Bucket S3 riêng tư có versioning; trình duyệt tải lên và xem bằng URL ký sẵn sống ngắn | `STORAGE_BACKEND=s3`, `S3_BUCKET` |
| Hàng đợi công việc | SQS kèm dead-letter queue | `QUEUE_BACKEND=sqs`, `SQS_QUEUE_URL`, `SQS_DEAD_LETTER_URL` |
| Chuyển mã | Service `worker` trên ECS Fargate, FFmpeg nằm trong container | `FFMPEG_*` |
| Đăng nhập | Cognito user pool; quản trị viên là thành viên nhóm `admin` | `AUTH_PROVIDER=cognito`, `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID` |
| Quyền truy cập AWS | IAM task role riêng cho `api` và `worker`; không có access key nào trong mã hay cấu hình | `AWS_REGION` |

Thiết kế đầy đủ: `docs/AWS_ARCHITECTURE.md`. Các quyết định: ADR-021 đến ADR-023 trong `docs/DECISIONS.md`.

## Trạng thái thật (2026-11-21) — đọc kỹ trước khi dùng

- **Chưa có database, bucket, hàng đợi, user pool, load balancer hay service nào trên AWS.** Tài nguyên duy nhất đã tạo là chứng chỉ ACM cho `video.uploadmdm.id.vn` (đã `ISSUED`).
- Mã: các adapter S3, SQS và Cognito (`app/storage_s3.py`, `app/queue_sqs.py`, `app/auth_oidc.py`) đã viết xong và được kiểm thử bằng **stub của botocore, không phải dịch vụ AWS thật** (`tests/test_aws_adapters.py`). Toàn bộ bộ test trên máy phát triển: `RUN_DB_TESTS=1 pytest -q` -> **172 passed, 7 skipped**.
- Terraform (`infra/aws/`): `fmt`, `validate` và `plan` đã chạy với tài khoản thật ở region `ap-southeast-2` (Sydney): `Plan: 56 to add, 0 to change, 0 to destroy`. **Chưa `apply`.**
- `deploy/aws/Dockerfile` (hai image `api` và `worker`) **chưa từng được build**.
- Chưa làm: triển khai, diễn tập sự cố, giám sát và cảnh báo, CI triển khai và rollback, kiểm thử tải, hoá đơn thật.

Vì vậy bản này hiện là mã nguồn và hạ tầng dạng mã sẵn sàng để dựng, chưa phải một hệ thống đang chạy. Site đang chạy thật (`https://video.uploadmdm.id.vn`) là bản VPS.

## Dựng trên tài khoản AWS của bạn

Việc này **tốn tiền**: chạy liên tục khoảng 108 USD/tháng theo giá Sydney tra ngày 2026-11-20 (bảng chi tiết và cách giảm trong `infra/aws/README.md`). Cần: một tài khoản AWS, một tên miền bạn quản lý được DNS, Terraform 1.x, AWS CLI v2, Docker.

1. Đăng nhập dòng lệnh bằng phiên ngắn hạn (`aws login` hoặc SSO). Không tạo access key cho tài khoản root, không ghi key vào file nào.
2. Trong `infra/aws/`: chép `terraform.tfvars.example` thành `terraform.tfvars`, điền `domain_name` và region. File này và `terraform.tfstate` đã được gitignore; state **chứa mật khẩu database**, không chia sẻ.
3. `terraform init`, `terraform plan`, đọc kỹ kế hoạch.
4. `terraform apply -target=aws_acm_certificate.site`, thêm bản ghi CNAME xác minh vào DNS, chờ chứng chỉ `ISSUED`.
5. `terraform apply` tạo phần còn lại. Hai service bắt đầu với `desired_count = 0` nên chưa có task nào chạy.
6. Build và đẩy hai image lên ECR (thủ công, hoặc bằng GitHub Actions sau khi đặt biến `AWS_ROLE_ARN` của kho), chạy `init-db` một lần, rồi `terraform apply -var image_tag=<tag> -var api_desired_count=1 -var worker_desired_count=1`.
7. Tạo người dùng trong Cognito, thêm quản trị viên vào nhóm `admin`.
8. Trỏ tên miền về ALB (`terraform output alb_dns_name`).
9. Kiểm tra: `python scripts/smoke_test.py --base-url https://ten-mien-cua-ban --email ban@example.com --clip duong/dan/clip.mp4`.

Lệnh đầy đủ, điều chưa kiểm chứng và cách dọn dẹp (`terraform destroy`): `infra/aws/README.md` và `prompts/09-AWS-DEPLOY.md`. Các bước 5 đến 9 chưa ai chạy thật; coi chúng là kế hoạch, không phải quy trình đã được chứng minh.

## Chạy thử trên máy (không cần AWS)

Không đặt ba biến `*_BACKEND`/`AUTH_PROVIDER=cognito` thì ứng dụng dùng thư mục riêng tư, hàng đợi PostgreSQL và tài khoản nội bộ. Cần Python 3.12, PostgreSQL và FFmpeg; tạo `.env` từ `.env.example` (mẫu đó viết cho Windows, sửa đường dẫn theo máy bạn).

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m flask --app app.main init-db
.\.venv\Scripts\python.exe -m flask --app app.main create-user ban@example.com --admin
.\.venv\Scripts\python.exe -m app.serve              # API tại 127.0.0.1:8000
.\.venv\Scripts\python.exe -m app.worker_service     # worker
$env:RUN_DB_TESTS = '1' ; .\.venv\Scripts\python.exe -m pytest -q
```

## GitHub Actions

`.github/workflows/ci.yml`: job `test` chạy ở mọi lần push. Job `images` (build hai image, đẩy lên ECR bằng quyền tạm thời qua OIDC, không có secret trong kho) chỉ chạy trên nhánh `main` và chỉ khi biến `AWS_ROLE_ARN` của kho đã được đặt; hiện biến đó chưa đặt nên job này luôn bị bỏ qua.

## Nhánh này không có gì

- Script và tài liệu cài đặt cho VPS Windows (`scripts/windows/`, `deploy/windows/`, `docs/WINDOWS_VPS_*.md`, hai prompt VPS): xem nhánh `vps`.
- Một số tài liệu dùng chung (`AGENTS.md`, `docs/PHASES.md`, `docs/SECURITY.md`, `docs/PROGRESS.md`) có nhắc tới các file VPS đó. Chúng là nhật ký chung của dự án, bản mới nhất nằm ở `main`.
- Các file `.tf` nằm ngay trong `infra/` (không phải `infra/aws/`) là thiết kế Google Cloud cũ đã lưu trữ, không dùng.

## Tài liệu chung

| File | Mục đích |
| --- | --- |
| `docs/REQUIREMENTS.md` | Yêu cầu gốc và scope |
| `docs/AWS_ARCHITECTURE.md` | Kiến trúc AWS, cấu hình container, việc chưa quyết |
| `docs/PHASES.md` | Các phase AWS 07 đến 13 và tiêu chí nghiệm thu |
| `docs/DATA_MODEL.md` | Các bảng PostgreSQL |
| `docs/API_CONTRACT.md` | API và luồng xem video riêng tư |
| `docs/PIPELINE_RELIABILITY.md` | Outbox, hàng đợi, thử lại, chống xử lý trùng |
| `docs/SECURITY.md` | Phân quyền, secret, mạng |
| `docs/PROGRESS.md` | Nhật ký việc đã làm, bằng chứng, việc còn BLOCKED |

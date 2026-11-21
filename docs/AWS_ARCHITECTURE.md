# Kiến trúc trên AWS (mục tiêu triển khai từ 2026-11-20)

> **LƯU TRỮ (2026-11-21): chủ dự án đã bỏ AWS, mục tiêu triển khai hiện là Azure (ADR-024, `docs/AZURE_ARCHITECTURE.md`).** Tài liệu này giữ lại để tham khảo và không còn được cập nhật. Trên AWS chỉ từng tạo một chứng chỉ ACM; không chạy lệnh AWS hay Terraform nào theo tài liệu này trừ khi chủ dự án yêu cầu.

**Trạng thái: THIẾT KẾ + ADAPTER TRONG CODE (Phase 07, 2026-11-20).** Adapter S3, SQS và xác minh token Cognito đã viết và kiểm thử bằng stub/fake trên máy; **chưa có tài nguyên AWS nào được tạo và chưa có lời gọi nào tới AWS**. Image container chưa được build. Hạ tầng đã viết bằng Terraform trong `infra/aws/` và qua `terraform validate` (Phase 08), nhưng **chưa `plan`, chưa `apply`**. Mọi mục về hạ tầng dưới đây vẫn là kế hoạch cho đến khi `docs/PROGRESS.md` ghi PASS kèm bằng chứng thật. Quyết định: ADR-021, ADR-022 trong `docs/DECISIONS.md`.

Lý do đổi: đề bài (`references/…pdf`, trang 1–2) yêu cầu **một nhà cung cấp cloud**, website chạy trên cloud, chuyển mã **bằng container**, hạ tầng tạo lại được từ code. Bản VPS Windows (ADR-015) lệch ở đúng các điểm đó. Dòng AWS trong bảng gợi ý của đề: *Application Load Balancer; ECS on Fargate API; RDS for PostgreSQL; S3; SQS; Lambda or Fargate workers; bounded Fargate tasks for conversion; Cognito; Secrets Manager.*

Bản VPS vẫn chạy nguyên trạng cho tới khi bản AWS qua được Phase 09; không sửa gì trên VPS trong lúc chuyển.

## Sơ đồ (dự kiến)

```text
Trình duyệt ──HTTPS──> Application Load Balancer (subnet public, 2 AZ)
     │                        │ chỉ nhận 443; SG của task chỉ cho ALB vào
     │                        ▼
     │            ECS Fargate service "api"  (container Flask + Waitress)
     │                 │            │ task role: ký URL S3, đọc secret
     │                 ▼            ▼
     │       RDS PostgreSQL     Cognito User Pool (xác minh ID token qua JWKS)
     │       (subnet private,
     │        SG chỉ cho api + worker)
     │                 ▲
     │                 │ claim job (lease + attempt ID, như hiện tại)
     │            ECS Fargate service "worker" (container Python + FFmpeg)
     │              reconcile → relay outbox → SQS → nhận 1 message → 1 job
     │                 │            ▲
     │                 ▼            │
     └─presigned URL─> S3 bucket riêng tư        SQS queue ──quá số lần giao──> SQS dead-letter queue
        (upload / phát / thumbnail)  inputs/  outputs/<job>/<attempt>/

Secrets Manager: mật khẩu DB.   CloudWatch: log JSON, dashboard, 1 alarm → SNS email.
ECR: image api và worker.       Terraform: `infra/aws/`.   GitHub Actions: test, build, deploy, rollback.
```

## Ánh xạ từ code hiện có

| Hiện tại (VPS) | AWS | Việc phải làm trong code |
| --- | --- | --- |
| Waitress sau Caddy (`app/serve.py`) | Container `api` trên ECS Fargate sau ALB | Dockerfile cho API; tin `X-Forwarded-*` từ ALB; log ra stdout |
| PostgreSQL trên VPS | RDS for PostgreSQL, subnet private | Không đổi model; `init-db` chạy một lần bằng ECS task; mật khẩu lấy từ Secrets Manager |
| Thư mục NTFS + ticket ký (`app/storage.py`) | S3 riêng tư, Block Public Access, versioning | Adapter S3 cùng giao diện: URL ký sẵn để upload/phát, `head`, `write`, `delete`. `source_generation` = VersionId của object nguồn |
| Bảng `queue_messages` (`app/queue_pg.py`) | SQS + dead-letter queue | `SqsBroker` cùng giao diện `publish/receive/ack/dead_letter`; heartbeat gia hạn visibility |
| Worker native trong Job Object (`app/worker_native.py`) | Container `worker` trên Fargate (CPU/RAM cố định của task) | Image có FFmpeg; `run_native` đã chạy được trên Linux; bỏ phần Job Object khi không phải Windows (đã có nhánh) |
| Tài khoản nội bộ (`app/auth_local.py`) | Cognito User Pool | Bộ xác minh OIDC chung (issuer, audience, JWKS); trang đăng nhập gọi Cognito; `admin` lấy từ group |
| File `.env` + NTFS ACL | Secrets Manager + biến môi trường của task | Không đọc file `.env` trong container |
| Log file xoay vòng + `healthcheck.ps1` | CloudWatch Logs, dashboard, alarm | `LOG_DIR` để trống → log JSON ra stderr (đã hỗ trợ) |
| Script PowerShell plan/`-Apply` | Terraform `infra/aws/` | Viết mới; thư mục `infra/` cũ là GCP đã lưu trữ |

**Giữ nguyên:** model dữ liệu, outbox giao dịch, khoá logic `(video, source_generation, profile)`, lease + attempt UUID, tối đa 3 lần thử, chỉ công bố khi MP4 và JPG đã kiểm tra, `worker/transcode.py`, giao diện, toàn bộ test hiện có. Chế độ `local` (thư mục + hàng đợi PostgreSQL + tài khoản nội bộ) vẫn tồn tại để phát triển và chạy test không cần AWS.

## Cấu hình của container (Phase 07)

Image build từ `deploy/aws/Dockerfile` (target `api` và `worker`) đã đặt sẵn `APP_ENV=production`, `STORAGE_BACKEND=s3`, `QUEUE_BACKEND=sqs`, `AUTH_PROVIDER=cognito`, `WORK_ROOT`. Task definition phải cấp thêm:

| Biến | Nguồn | Ghi chú |
| --- | --- | --- |
| `AWS_REGION` | ECS tự đặt | Dùng cho S3, SQS, Cognito và CSP |
| `S3_BUCKET` | Terraform | Tên không có dấu chấm; bucket bật versioning, Block Public Access, CORS cho origin của trang (POST, GET) |
| `SQS_QUEUE_URL`, `SQS_DEAD_LETTER_URL` | Terraform | Queue chính có redrive policy sang dead-letter queue |
| `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID` | Terraform | App client không có secret, bật `USER_PASSWORD_AUTH`; nhóm `admin` cho quản trị viên |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` | Terraform | Endpoint RDS |
| `POSTGRES_PASSWORD` | Secrets Manager (`secrets` của task) | Không nằm trong image, Terraform output hay log |
| `MAX_UPLOAD_BYTES`, `FFMPEG_THREADS`, `TRANSCODE_TIMEOUT_SECONDS` | Tuỳ chọn | Mặc định 50 MB, 1 luồng, 90 giây |

Không có access key nào trong cấu hình: boto3 lấy quyền từ task role. Quyền cần cho task role — `api`: `s3:PutObject` trên `inputs/*`, `s3:GetObject`/`s3:GetObjectVersion` trên `outputs/*`, `s3:ListBucketVersions`, `s3:DeleteObject`/`s3:DeleteObjectVersion` (xoá video), và đọc thuộc tính queue nếu dùng `system-status`. `worker`: `s3:GetObjectVersion` trên `inputs/*`, `s3:PutObject` trên `outputs/*`, `s3:ListBucket`/`s3:ListBucketVersions` và xoá phiên bản (dọn dẹp), `sqs:SendMessage`, `ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility` trên queue chính và `sqs:SendMessage` trên dead-letter queue. Danh sách này suy ra từ code, **chưa được kiểm chứng bằng IAM thật**.

## Các lựa chọn thiết kế và đánh đổi

1. **Worker là một ECS service chạy liên tục (1 task), mỗi lúc một job**, không phải `RunTask` cho từng video. Lý do: dùng lại nguyên vòng lặp `reconcile → relay → dispatch` đã kiểm thử; diễn tập sự cố đơn giản (`aws ecs stop-task` giữa lúc chuyển mã, ECS tự dựng task mới, lease hết hạn, job được thử lại). Đánh đổi: task chạy cả khi không có video; đặt `desired_count = 0` khi không demo. Xem lại nếu thầy yêu cầu đúng nghĩa "một task cho một lần chuyển mã".
2. **Task Fargate đặt ở subnet public có IP public, không dùng NAT Gateway.** Security group của task chỉ cho ALB đi vào; RDS ở subnet private và chỉ nhận từ SG của `api`/`worker`. Lý do: NAT Gateway là chi phí cố định lớn nhất có thể tránh. Đánh đổi: task có địa chỉ public (không cổng nào mở từ Internet). Phải vẽ rõ trong sơ đồ mạng cuối cùng.
3. **Upload dùng presigned POST có `content-length-range`** để S3 tự từ chối file quá giới hạn; sau đó `complete` vẫn kiểm tra lại kích thước và VersionId. Trình duyệt gửi thẳng tới S3 nên bucket cần CORS cho đúng origin của trang, và CSP của trang phải cho phép host của bucket ở `connect-src`, `media-src`, `img-src`.
4. **Thu hồi quyền**: như hiện tại, chỉ chặn URL mới; URL đã cấp sống tới khi hết hạn (120 giây).
5. **Dữ liệu trên VPS không được chuyển sang.** RDS bắt đầu trống, nạp bằng seed 10 clip chuẩn. Nếu cần giữ video thật trên VPS thì phải nói trước Phase 09.

## Việc chưa quyết (cần thông tin từ chủ dự án)

| Việc | Vì sao cần | Chốt ở |
| --- | --- | --- |
| ~~Loại tài khoản AWS~~ | **Đã rõ 2026-11-20** (xem mục "Tài khoản AWS đã kiểm tra" bên dưới): tài khoản cá nhân, gói Free plan có credit, không phải Learner Lab | — |
| ~~Region~~ | **Đã chốt lại 2026-11-20: `ap-southeast-2` (Sydney)**, chủ dự án đồng ý sau phát hiện dưới đây. Trước đó chủ dự án đã chọn `ap-southeast-1` (Singapore), nhưng khi đăng nhập bằng `aws login --region ap-southeast-1` trang đăng nhập của AWS báo: "You're trying to log into an AWS Region that's not supported for your project. Project Fresh Deploy is set up in ap-southeast-2… use `aws login --region ap-southeast-2`". Tài khoản là một "project" gắn với Sydney; chưa biết có thêm được region khác trong AWS Settings hay không (trang Settings không tải được trong trình duyệt nhúng). Đánh đổi: xa Việt Nam hơn Singapore nên độ trễ cao hơn; chưa đo | — |
| Tài khoản mới đang được AWS xác minh | CloudShell báo "account verification is in progress… up to two days"; một số dịch vụ có thể cũng chưa tạo được | Thử lại trước khi `plan`/`apply` |
| Giới hạn của gói Free plan | Chưa biết dịch vụ nào trong thiết kế (ALB, RDS, Fargate, NAT…) bị gói này hạn chế; credit và thời hạn là trần chi tiêu thực tế | Phase 08, bằng `terraform plan` và trang Billing |
| Cách cấp quyền cho Terraform | CloudShell chưa dùng được; chưa biết đăng nhập bằng root hay IAM user. Không dùng access key của root | Phase 08 |
| ~~Tên miền~~ | **Đã rõ 2026-11-20: chủ dự án có tên miền.** Dùng chứng chỉ ACM (xác minh bằng bản ghi DNS) gắn vào ALB cổng 443, cổng 80 chỉ chuyển hướng sang HTTPS; không cần CloudFront. Còn thiếu: tên miền/tên miền con cụ thể và nơi quản lý DNS (Route 53 hay nhà đăng ký khác) để biết ai tạo bản ghi xác minh và bản ghi trỏ về ALB | Tên cụ thể: trước Phase 09 |
| ~~Tên miền cho bản AWS~~ | **Đã chốt 2026-11-20: dùng lại `video.uploadmdm.id.vn`** (chủ dự án chọn, dù đề xuất là tên miền con riêng). Tên này hiện là bản ghi A trỏ về VPS và đang phục vụ bản VPS qua Caddy, nên sẽ có một lần chuyển DNS; xem mục "Chuyển tên miền từ VPS sang AWS" | — |
| Nơi build image | Máy này không có Docker, AWS CLI, Terraform, Git. Phương án: GitHub Actions build và đẩy lên ECR, hoặc AWS CloudShell | Phase 08 |
| Kho GitHub | CI/CD và rollback cần repo; thư mục này hiện không phải git repository | Trước Phase 12 |
| Ngân sách và thời gian giữ tài nguyên | ALB, RDS, Fargate, IP public tính tiền theo giờ kể cả khi không dùng | Trước Phase 09 |

### Chuyển tên miền từ VPS sang AWS (kế hoạch cho Phase 09, chưa thực hiện)

Hai bản dùng chung một tên nên không chạy song song trên tên đó được. Trình tự để bản VPS chỉ mất địa chỉ khi bản AWS đã được kiểm tra:

1. Thêm bản ghi CNAME xác minh của ACM ở nhà đăng ký. Bản ghi này có tên riêng (bắt đầu bằng `_`), **không ảnh hưởng** bản ghi A `video` đang trỏ về VPS.
2. `apply` phần còn lại, đẩy image, `init-db`, tạo tài khoản, bật service. Lúc này trang vẫn do VPS phục vụ.
3. Kiểm thử bản AWS **trước khi đổi DNS**: gọi thẳng ALB nhưng giữ đúng tên miền (ví dụ `curl --resolve video.uploadmdm.id.vn:443:<IP của ALB> …`, hoặc sửa file `hosts` trên một máy thử). Chứng chỉ và CORS đều khớp vì tên miền không đổi.
4. Hạ TTL của bản ghi `video` (đang 3600 giây) xuống thấp trước khi chuyển, để quay lui nhanh.
5. Chuyển: đổi bản ghi `video` từ A (IP của VPS) thành CNAME trỏ về `alb_dns_name`. Từ lúc này bản VPS không còn truy cập được bằng tên miền; service trên VPS vẫn chạy và không bị sửa.
6. Quay lui: đổi bản ghi `video` về lại bản ghi A cũ. Ghi lại giá trị cũ trước khi đổi.

Hệ quả cần biết: dữ liệu (tài khoản, video) trên VPS không sang AWS; sau khi chuyển, Caddy trên VPS sẽ không gia hạn được chứng chỉ cho tên miền này nữa.

### Tài khoản AWS đã kiểm tra (2026-11-20, chỉ đọc, qua Console do chủ dự án tự đăng nhập)

- Tài khoản cá nhân trên gói **Free plan**; menu tài khoản hiện "Credits remaining $180 USD", "Days remaining 182 days". Không có dấu hiệu Learner Lab.
- Region đang chọn trong Console: `ap-southeast-2`.
- CloudShell không mở được: "Unable to create the environment. Your account verification is in progress. This may take up to two days for new accounts."
- Trang RDS (`ap-southeast-2`): 0 database. Trang ECS và Cognito mở được; chưa có user pool nào.
- Trang IAM và EC2 không tải được trong khung trình duyệt nhúng, nên **chưa xác định** được: đăng nhập bằng root hay IAM user, quyền IAM, và có instance EC2 nào đang chạy không.
- Số tài khoản, tên người dùng và email cố ý không ghi vào repo.

### Lệnh kiểm tra tài khoản (chỉ đọc, chạy trong AWS CloudShell khi tài khoản đã xác minh xong)

```bash
aws sts get-caller-identity
aws configure get region
aws iam get-role --role-name LabRole --query Role.Arn
aws cognito-idp list-user-pools --max-results 1
aws ecs list-clusters
```

Dán kết quả lại (không dán access key). `LabRole` tồn tại và ARN người dùng có `voclabs` nghĩa là Learner Lab.

## Chi phí

Ước tính sơ bộ từ giá On-Demand tra ngày 2026-11-20 (AWS Price List, `ap-southeast-2`), bảng đầy đủ ở `infra/aws/README.md`: ALB, RDS `db.t4g.micro` + 20 GB, task `api`, task `worker` và 4 địa chỉ IPv4 public chạy liên tục tốn **khoảng 0,144 USD/giờ, tức khoảng 108 USD/tháng**; riêng task worker chiếm khoảng 43 USD. Chưa tính S3, SQS, CloudWatch, Secrets Manager, ECR, sao lưu và lưu lượng ra Internet (chưa tra giá). Tài khoản có 180 USD credit trên gói Free plan: chưa xác minh credit áp dụng cho những dịch vụ nào. Đây là công thức minh hoạ, không phải hoá đơn; bảng ước tính theo tải thực tế vẫn thuộc Phase 11.

## Miền lỗi

ALB và subnet trải 2 AZ; RDS một AZ (single-AZ để tiết kiệm), mỗi service một task. Mất AZ chứa RDS là mất dịch vụ cho tới khi khôi phục từ snapshot. Task chết thì ECS dựng lại; job đang chạy được cứu bởi lease + reconcile.

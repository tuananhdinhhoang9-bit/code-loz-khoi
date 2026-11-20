# Vận hành trên VPS Windows Server

Chạy các script trong PowerShell (elevated khi cần) tại `C:\VideoPortal\app\scripts\windows`. Lệnh `flask` chạy trong `C:\VideoPortal\app` với venv và `$env:VIDEO_PORTAL_ENV_FILE = 'C:\VideoPortal\config\.env'`.

## Lệnh hằng ngày

| Việc | Lệnh |
| --- | --- |
| Xem tình trạng | `.\status.ps1` (service, `/health`, đĩa, hàng đợi, bản sao lưu) |
| Khởi động / dừng / khởi động lại | `.\start-services.ps1` · `.\stop-services.ps1` · `.\restart-services.ps1` |
| Kiểm tra sức khoẻ một lần | `.\healthcheck.ps1` (ghi một dòng JSON vào `logs\health.log`, exit 1 nếu có lỗi) |
| Sao lưu ngay | `.\backup.ps1 -OffsitePath <nơi ngoài VPS>` |
| Xem job | `flask --app app.main local-jobs` |
| Thử lại một job FAILED | `flask --app app.main retry-job <job-id>` |
| Hàng đợi và đĩa | `flask --app app.main system-status` |
| Dọn file tạm | `flask --app app.main cleanup --max-age-hours 24` (worker tự chạy mỗi giờ) |
| Tạo / khoá tài khoản | `flask --app app.main create-user EMAIL [--admin]` · `set-password EMAIL` · `disable-user EMAIL` |

## Service

| Service | Chạy gì | Dừng |
| --- | --- | --- |
| `VideoPortal-API` | `python -m app.serve` (Waitress, 127.0.0.1:8000) | 30 giây |
| `VideoPortal-Worker` | `python -m app.worker_service` | Chờ tới 180 giây để clip đang mã hoá xong |
| `VideoPortal-Caddy` | `caddy run --config C:\VideoPortal\config\Caddyfile` | 30 giây |
| `postgresql-x64-16` | Có sẵn; script không bao giờ dừng nó | — |

Tự khởi động cùng Windows (delayed), tự chạy lại sau khi crash sau 10/30/60 giây (WinSW `onfailure`). Dispatcher và outbox relay nằm trong worker nên không có service riêng.

Tắt an toàn: worker bắt Ctrl+C/Ctrl+Break, không nhận job mới và thoát mã 0 (đã test với tiến trình thật khi worker đang rảnh). Thiết kế là làm xong job đang chạy rồi mới thoát; trường hợp dừng **giữa lúc đang mã hoá** qua WinSW chưa được kiểm chứng. Nếu Windows giết worker giữa chừng, Job Object giết luôn FFmpeg (đã test); job không mất: lease hết hạn sau tối đa 180 giây và lần chạy sau thử lại (đã test).

## Log

| File (trong `C:\VideoPortal\logs`) | Nội dung | Xoay vòng |
| --- | --- | --- |
| `api.log`, `api-error.log` | Mỗi request một dòng JSON: method, path (không có query), status, ms, request_id, uid | 10 MB × 5 |
| `worker.log`, `worker-error.log` | Trạng thái job, attempt, thời gian xử lý, 40 dòng cuối stderr của FFmpeg khi lỗi | 10 MB × 5 |
| `caddy-access.log` | Truy cập qua proxy, đã xoá ticket | 10 MiB × 5 |
| `health.log` | Kết quả health check | 5 MB, giữ 1 bản cũ |
| `services\*.log` | stdout/stderr do WinSW bắt | 10 MB × 5 |

Tra một sự cố: lấy `request_id` từ thông báo lỗi của người dùng → tìm trong `api.log`; lấy `job_id` từ `local-jobs` → tìm trong `worker.log`.

## Trạng thái job và mã lỗi thường gặp

`QUEUED → PROCESSING → READY`; lỗi tạm thời → `RETRYING` (chờ 5 rồi 10 giây) tối đa 3 lần; hết lượt hoặc lỗi vĩnh viễn → `FAILED`.

| `last_error_code` | Loại | Xử lý |
| --- | --- | --- |
| `invalid_media`, `unsupported_codec`, `input_too_long`, `invalid_dimensions`, `input_size_invalid` | Vĩnh viễn | Báo người dùng tải file khác |
| `lease_expired` | Tạm thời | Worker đã chết giữa chừng; tự thử lại |
| `worker_timeout`, `processing_timeout` | Tạm thời | Clip quá nặng cho máy: tăng `TRANSCODE_TIMEOUT_SECONDS` hoặc từ chối |
| `source_or_storage_unavailable` | Tạm thời | Kiểm tra đĩa và quyền NTFS |
| `attempts_exhausted`, `dispatch_exhausted`, `publish_exhausted` | Vĩnh viễn | Sửa nguyên nhân rồi `retry-job` |
| `decode_or_encode_failed` | Vĩnh viễn | Xem `stderr_tail` trong `worker.log` |

Message hỏng nằm trong `queue_messages` với `dead_at` khác NULL (đếm qua `system-status` hoặc `/api/monitor`).

## Quy trình khôi phục nhanh

| Triệu chứng | Kiểm tra | Hành động |
| --- | --- | --- |
| Trang không mở | `.\status.ps1` | Service nào dừng thì `.\start-services.ps1`; xem `logs\services\<tên>.err.log` |
| `/health` trả 503 | PostgreSQL có chạy không | `Start-Service postgresql-x64-16`; API kiểm tra kết nối trước mỗi lần dùng (`pool_pre_ping`) nên request kế tiếp sẽ nối lại; nếu không, khởi động lại `VideoPortal-API` |
| Video kẹt ở "Đã xếp hàng" | `VideoPortal-Worker` có chạy không; `worker-error.log` | Khởi động worker; nếu log báo `another_worker_is_running` thì còn một tiến trình worker cũ |
| Video kẹt ở "Đang xử lý" quá 5 phút | `local-jobs` xem `due` | Chờ lease hết hạn (≤ 180 giây) hoặc khởi động lại worker |
| Upload báo đầy | `system-status` | Xoá video không cần, `cleanup`, hoặc tăng đĩa; đừng hạ `MIN_FREE_BYTES` xuống 0 |
| Sau khi mất điện/khởi động lại | `.\status.ps1` | Không cần thao tác: service tự chạy, job dở tự được thử lại |

## Theo dõi dung lượng

`healthcheck.ps1` báo lỗi khi ổ còn dưới `-MinFreeGb` (mặc định 5 GB) hoặc bản sao lưu mới nhất cũ hơn 26 giờ, và ghi Windows Event (nguồn `VideoPortal`, ID 1001). `register-tasks.ps1` đặt lịch chạy mỗi 5 phút. Đây là cảnh báo tại chỗ; chưa có kênh gửi email/chat.

## Cập nhật phiên bản

```powershell
.\backup.ps1 -OffsitePath <nơi ngoài VPS>
.\stop-services.ps1
cd C:\VideoPortal\app ; git pull            # hoặc giải nén bản mới
C:\VideoPortal\venv\Scripts\python.exe -m pip install -r requirements.txt
C:\VideoPortal\venv\Scripts\python.exe -m flask --app app.main init-db
.\scripts\windows\start-services.ps1 ; .\scripts\windows\status.ps1
```

Quay lui: xem `docs/WINDOWS_VPS_ROLLBACK.md`.

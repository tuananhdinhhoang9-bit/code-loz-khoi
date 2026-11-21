# Video Portal — bản chạy trên VPS Windows Server (nhánh `vps`)

Đề tài số 10 “Video Upload and Processing Portal” (`references/10_video_upload_and_processing_portal.pdf`). Nhánh này là bản chạy trọn trên **một máy Windows Server**: không cần tài khoản cloud nào. Bản cloud theo đề bài đang được thiết kế cho Azure trên nhánh `main` (chủ dự án đã bỏ AWS ngày 2026-11-21; bản AWS cũ còn ở nhánh [`aws`](../../tree/aws), đã đóng băng). Nhánh `main` là nơi phát triển.

## Mọi thứ nằm ở đâu

| Việc | Bản VPS dùng | Cấu hình |
| --- | --- | --- |
| Web và API | Flask chạy bằng Waitress, đứng sau Caddy (HTTPS, chứng chỉ tự gia hạn) | `BIND_HOST`, `BIND_PORT` |
| Database | PostgreSQL cài ngay trên VPS, chỉ nghe ở `localhost` | `POSTGRES_*` |
| Lưu video gốc, MP4, ảnh thu nhỏ | Thư mục riêng tư trên ổ đĩa, ngoài thư mục web | `STORAGE_BACKEND=local` (mặc định), `STORAGE_ROOT` |
| Hàng đợi công việc | Bảng `queue_messages` trong PostgreSQL, có dead-letter | `QUEUE_BACKEND=postgres` (mặc định) |
| Chuyển mã | Tiến trình worker gọi FFmpeg cài trên máy, giới hạn CPU và bộ nhớ | `FFMPEG_BIN`, `FFMPEG_THREADS` |
| Đăng nhập | Tài khoản nội bộ lưu trong PostgreSQL, do quản trị viên tạo | `AUTH_PROVIDER=local` |

Mẫu cấu hình đầy đủ: `.env.example`. File `.env` thật chỉ nằm trên máy chủ, không bao giờ đưa vào Git.

## Trạng thái thật (2026-11-21)

- Site đang chạy tại `https://video.uploadmdm.id.vn` với ba service Windows `VideoPortal-API`, `VideoPortal-Worker`, `VideoPortal-Caddy` và PostgreSQL 18. Lần kiểm tra đầu-cuối gần nhất trên máy chủ: `scripts/smoke_test.py` 23/23 PASS (xem `docs/PROGRESS.md`).
- **Mã đang chạy trên VPS là nhánh này tại commit `2c35b23`** (cập nhật ngày 2026-11-21, có sao lưu mã và database trước khi thay; file `C:\VideoPortal\app\DEPLOYED_COMMIT.txt` trên máy chủ ghi commit đang chạy). Sau lần cập nhật đã kiểm tra `/health`, trang chủ, các API trả 401 khi chưa đăng nhập và log không có lỗi; **chưa kiểm tra đăng nhập, tải lên và phát video trên site thật với mã mới**. Chi tiết và cách quay lại bản cũ ở `docs/PROGRESS.md`.
- Kiểm thử của nhánh này trên máy phát triển Windows (PostgreSQL 18 và FFmpeg thật): `RUN_DB_TESTS=1 pytest -q` -> **172 passed, 7 skipped** (các test bị bỏ qua cần Docker hoặc điều kiện không có trên máy đó).
- Chưa có: sao lưu database ra ngoài VPS, kiểm thử tải, cảnh báo giám sát.

## Cài lên một VPS mới

Yêu cầu: Windows Server (bản đang chạy dùng Windows Server 2022), quyền Administrator, một tên miền trỏ về địa chỉ của VPS. Script nào thay đổi hệ thống cũng **chỉ in kế hoạch** nếu thiếu `-Apply`; đọc kế hoạch rồi mới chạy lại với `-Apply`.

```powershell
.\scripts\windows\preflight.ps1 -AllowNetwork        # chỉ đọc, báo PASS/WARN/FAIL
.\scripts\windows\install-prerequisites.ps1          # thư mục, venv, mẫu cấu hình, tải FFmpeg/Caddy/WinSW
.\scripts\windows\setup-database.ps1                 # role quyền tối thiểu + database + init-db
.\scripts\windows\rehearsal.ps1                      # chạy thử cả hệ thống trên loopback, không cài service
.\scripts\windows\install-services.ps1               # VideoPortal-API / -Worker / -Caddy
.\scripts\windows\start-services.ps1 ; .\scripts\windows\status.ps1
.\scripts\windows\backup.ps1 ; .\scripts\windows\restore.ps1 -DumpFile <file> -DropAfterVerify
```

Tạo tài khoản quản trị đầu tiên (mật khẩu được hỏi trên màn hình, không ghi vào lệnh):

```powershell
python -m flask --app app.main create-user ban@example.com --admin
```

| Tài liệu | Nội dung |
| --- | --- |
| `docs/WINDOWS_VPS_ARCHITECTURE.md` | Kiến trúc, cấu trúc thư mục, tài nguyên |
| `docs/WINDOWS_VPS_SETUP.md` | Phần mềm cần cài, trình tự script, biến cấu hình, cổng và firewall |
| `docs/WINDOWS_VPS_SECURITY.md` | Tài khoản nội bộ, phân quyền, storage riêng tư, tài khoản service, NTFS |
| `docs/WINDOWS_VPS_OPERATIONS.md` | Lệnh vận hành, log, mã lỗi, xử lý sự cố |
| `docs/WINDOWS_VPS_BACKUP.md` | Sao lưu, khôi phục, diễn tập |
| `docs/WINDOWS_VPS_ROLLBACK.md` | Quay lui mã nguồn, cấu hình, dữ liệu |

## Chạy thử trên máy phát triển (không cài service)

Cần Python 3.12, PostgreSQL và FFmpeg. Tạo `.env` từ `.env.example` với đường dẫn và mật khẩu của máy bạn.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m flask --app app.main init-db
.\.venv\Scripts\python.exe -m flask --app app.main create-user ban@example.com --admin
.\.venv\Scripts\python.exe -m app.serve              # API tại 127.0.0.1:8000
.\.venv\Scripts\python.exe -m app.worker_service     # worker: hàng đợi PostgreSQL + FFmpeg
$env:RUN_DB_TESTS = '1' ; .\.venv\Scripts\python.exe -m pytest -q
```

Kiểm tra một máy chủ đang chạy: `python scripts/smoke_test.py --base-url https://ten-mien-cua-ban --email ban@example.com --clip duong\dan\clip.mp4` (hỏi mật khẩu trên màn hình, tải clip đó lên, chờ xử lý xong, thử xem rồi xoá).

## Cập nhật giao diện trên VPS đang chạy

Sao lưu ba file `templates\index.html`, `static\portal.css`, `static\portal.js` trong `C:\VideoPortal\app\app`, chép bản mới đè lên, rồi `Restart-Service VideoPortal-API`. Các bản sao lưu trước nằm trong `C:\VideoPortal\backups\ui-before-*`; quay lui bằng cách chép ngược lại và khởi động lại service.

## Nhánh này không có gì

- Dockerfile, tài liệu và prompt cho Azure (`deploy/azure/`, `docs/AZURE_ARCHITECTURE.md`, `prompts/*-AZURE-*.md`): xem nhánh `main`.
- Terraform, Dockerfile và tài liệu AWS (đã bỏ): xem nhánh `aws`.
- Job build image trong GitHub Actions; ở nhánh này CI chỉ chạy test.
- Một số tài liệu dùng chung (`AGENTS.md`, `docs/PHASES.md`, `docs/DECISIONS.md`, `docs/PROGRESS.md`) có nhắc tới các file Azure và AWS đó. Chúng là nhật ký chung của dự án, bản mới nhất nằm ở `main`.
- Mã adapter Azure (`app/storage_blob.py`, `app/queue_servicebus.py`, `app/auth_oidc.py`) vẫn ở đây vì mã ứng dụng giống nhau ở mọi nhánh; với cấu hình `local`/`postgres` thì ứng dụng không gọi tới dịch vụ cloud nào và chạy được cả khi ba gói `azure-*` trong `requirements.txt` chưa được cài.

## Tài liệu chung

| File | Mục đích |
| --- | --- |
| `docs/REQUIREMENTS.md` | Yêu cầu gốc và scope |
| `docs/DATA_MODEL.md` | Các bảng PostgreSQL |
| `docs/API_CONTRACT.md` | API và luồng xem video riêng tư |
| `docs/PIPELINE_RELIABILITY.md` | Outbox, hàng đợi, thử lại, chống xử lý trùng |
| `docs/SECURITY.md` | Phân quyền, secret, mạng |
| `docs/PROGRESS.md` | Nhật ký việc đã làm, bằng chứng, việc còn BLOCKED |
| `docs/DECISIONS.md` | Các quyết định công nghệ |

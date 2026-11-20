# Cài đặt trên VPS Windows Server

**Chưa thực hiện trên VPS thật.** Các bước dưới đây là kế hoạch cho Phase 08. Trên máy phát triển, các script đã được chạy thật ở mức ghi trong cột "Đã kiểm chứng".

Mọi script thay đổi hệ thống đều **chỉ in kế hoạch** nếu không có `-Apply`. Không script nào tự tắt Firewall/Defender, đổi RDP, mở cổng, hay xoá dữ liệu.

## Phần mềm cần có trên VPS (đều miễn phí)

| Phần mềm | Phiên bản đã dùng khi kiểm thử | Ghi chú |
| --- | --- | --- |
| Python | 3.12.10 | Cài **cho mọi người dùng** (Program Files) để tài khoản service đọc được |
| PostgreSQL | 16.4 | Cài bằng EDB installer thành Windows service; bạn tự đặt mật khẩu `postgres` |
| FFmpeg | 9.0.1 essentials (gyan.dev) | Cần `libx264` và `aac`; đặt ở `C:\VideoPortal\tools\ffmpeg` |
| Caddy | 2.11.9 | `C:\VideoPortal\tools\caddy\caddy.exe` |
| WinSW | 2.12.0 | `C:\VideoPortal\tools\winsw\WinSW-x64.exe` |
| Git | tuỳ chọn | Chỉ để kéo bản cập nhật |

Không cần Docker, WSL2, Redis, hay Google Cloud.

## Trình tự

| # | Lệnh (PowerShell, trong `C:\VideoPortal\app\scripts\windows`) | Quyền | Đã kiểm chứng trên máy dev |
| --- | --- | --- | --- |
| 1 | `.\preflight.ps1 -AllowNetwork -Domain ten.mien.cua.ban` | thường | Chạy thật: 35 kiểm tra, báo đúng FAIL/WARN |
| 2 | Đưa mã nguồn vào `C:\VideoPortal\app` (git clone hoặc giải nén) | admin | — |
| 3 | `.\install-prerequisites.ps1` rồi `-Apply -Download` | admin | Plan + `-Apply -SkipVenv` chạy thật; `-Download` và tạo venv **chưa chạy** |
| 4 | Cài PostgreSQL 16 bằng EDB installer (nếu chưa có) | admin | — |
| 5 | `.\setup-database.ps1` rồi `-Apply` | admin | Chạy thật: tạo role không superuser, giới hạn 20 kết nối; chạy lại không đổi gì |
| 6 | `flask --app app.main create-user ban@example.com --admin` | thường | Lệnh đã test bằng pytest |
| 7 | Sao chép `deploy\windows\Caddyfile` → `C:\VideoPortal\config\Caddyfile`, sửa tên miền | admin | `caddy validate`: Valid configuration |
| 8 | `.\rehearsal.ps1` (chạy thử cả hệ thống bằng tiến trình thường, chưa cài service) | thường | Chạy thật: 20/20 bước smoke test qua HTTPS nội bộ |
| 9 | `.\install-services.ps1` rồi `-Apply` | admin | Chỉ chạy plan; **cài service thật chưa kiểm chứng** |
| 10 | `.\start-services.ps1`, `.\status.ps1` | admin | `status.ps1` chạy thật; start/stop chưa chạy với service thật |
| 11 | `.\register-tasks.ps1 -Apply -OffsitePath <nơi lưu ngoài VPS>` | admin | Chỉ chạy plan |
| 12 | Mở cổng 80/443 trên Firewall **sau khi được duyệt** | admin | Không thực hiện |

### Bước 5 chi tiết — database

`setup-database.ps1 -Apply` hỏi mật khẩu của `postgres` (không lưu), rồi:

- tạo role `video_portal` với `NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 20` nếu chưa có;
- tạo database `video_portal` thuộc role đó và thu hồi quyền của `PUBLIC` nếu chưa có;
- sinh mật khẩu ngẫu nhiên, ghi vào `config\.env`, không in ra màn hình, không đưa lên dòng lệnh;
- chạy `flask init-db` (tạo bảng/cột còn thiếu và profile `mp4-480p`; không bao giờ xoá).

Role hoặc database đã tồn tại thì giữ nguyên. Script cảnh báo nếu `listen_addresses` không phải `localhost`. Các giá trị gợi ý cho 4 GB RAM (`max_connections=30`, `shared_buffers=512MB`, `work_mem=8MB`) chỉ được in ra; sửa `postgresql.conf` là việc bạn tự làm trong giờ bảo trì.

### Bước 7 chi tiết — tên miền và HTTPS

- **Có tên miền:** trong `Caddyfile` thay `localhost` bằng tên miền và xoá dòng `tls internal`. Cần bản ghi A trỏ về VPS và cổng 80 + 443 mở từ Internet. Caddy tự xin và gia hạn chứng chỉ công khai.
- **Chưa có tên miền:** giữ `localhost` + `tls internal`. Chỉ thử được ngay trên VPS (qua RDP). Đây **không phải** HTTPS công khai hợp lệ; trình duyệt máy khác sẽ không tin chứng chỉ này.
- Giới hạn body trong Caddyfile (`201MB`) phải đi cùng `MAX_UPLOAD_BYTES` trong `.env`.

## Biến cấu hình (`C:\VideoPortal\config\.env`)

Mẫu đầy đủ ở `.env.example`. Service đọc file này qua biến `VIDEO_PORTAL_ENV_FILE`; khi biến này được đặt, file đó luôn thắng mọi `.env` khác.

| Biến | Mặc định trong code | Giá trị mẫu cho VPS | Ý nghĩa |
| --- | --- | --- | --- |
| `APP_ENV` | `local` | `production` | `production` bắt buộc đường dẫn storage tuyệt đối, ngoài thư mục mã nguồn |
| `STORAGE_ROOT`, `WORK_ROOT`, `LOG_DIR` | `.local/...` | `C:\VideoPortal\storage\...` | Thư mục riêng tư, tạm, log |
| `MAX_UPLOAD_BYTES` | 50 000 000 | 200 000 000 | Giới hạn upload (xem ghi chú dưới) |
| `MIN_FREE_BYTES` | 500 000 000 | 2 000 000 000 | Từ chối upload mới khi đĩa sắp đầy (HTTP 507) |
| `AUTH_PROVIDER` | `firebase` | `local` | `local` = tài khoản trong PostgreSQL |
| `SESSION_HOURS` | 12 | 12 | Thời hạn phiên đăng nhập |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | 4, 2 | 4, 2 | Kết nối DB của API |
| `BIND_HOST`, `BIND_PORT`, `WAITRESS_THREADS` | 127.0.0.1, 8000, 6 | như mặc định | Waitress chỉ nghe loopback |
| `FFMPEG_BIN`, `FFPROBE_BIN` | tìm trong PATH | đường dẫn tới `.exe` | Service không dựa vào PATH của người dùng |
| `FFMPEG_THREADS` | 1 | 2 | Số luồng codec **và** số CPU worker được dùng (tối đa 2) |
| `TRANSCODE_TIMEOUT_SECONDS` | 90 | 600 | Thời gian tối đa cho một lần mã hoá |
| `WORKER_MEMORY_LIMIT_MB` | 1536 | 1536 | Trần RAM cho cả cây tiến trình FFmpeg |

**Ghi chú về 200 MB:** đề bài yêu cầu bộ dữ liệu mẫu ≤ 50 MB và ≤ 30 giây mỗi clip. Mặc định trong code vẫn là 50 MB để giữ hành vi và test của Phase 01–06; mẫu cấu hình VPS đặt 200 MB theo yêu cầu mới. Giới hạn **30 giây** không đổi: file 200 MB dài hơn 30 giây vẫn bị từ chối sau khi ffprobe kiểm tra.

## Cổng và firewall

| Cổng | Ai nghe | Từ Internet |
| --- | --- | --- |
| 443, 80 | Caddy | **Cần mở** (80 dùng cho xác thực chứng chỉ và chuyển hướng) — chỉ sau khi được duyệt |
| 8000 | Waitress, chỉ `127.0.0.1` | Không bao giờ |
| 5432 | PostgreSQL, chỉ `localhost` | Không bao giờ |
| 2019 | Caddy admin, chỉ `127.0.0.1` | Không bao giờ |
| 3389 | RDP | Không đụng tới; nên giới hạn IP nguồn (việc của bạn) |

Lệnh mở cổng, chỉ chạy khi đã duyệt:

```powershell
New-NetFirewallRule -DisplayName 'VideoPortal HTTP(S)' -Direction Inbound -Protocol TCP -LocalPort 80,443 -Action Allow
```

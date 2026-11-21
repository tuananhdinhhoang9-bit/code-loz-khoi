# Sao lưu và khôi phục

## Cần sao lưu những gì

| Dữ liệu | Ở đâu | Cách sao lưu | Mất thì sao |
| --- | --- | --- | --- |
| Database (video, quyền, job, tài khoản) | PostgreSQL | `backup.ps1` → file `.dump` | Mất toàn bộ danh mục và tài khoản |
| File video gốc + đã xử lý | `storage\objects` | `backup.ps1 -IncludeStorage -OffsitePath …` (robocopy, không xoá ở đích) | Mất nội dung; DB còn nhưng không phát được |
| Cấu hình | `config\.env`, `config\Caddyfile` | Sao chép thủ công vào nơi an toàn (có mật khẩu DB) | Phải cấu hình lại |
| Khoá ký ticket | `storage\objects\.signing-key` | **Không** sao lưu ra ngoài; mất thì tự sinh lại | Chỉ làm các link phát đang mở (≤ 2 phút) hết hiệu lực |
| Chứng chỉ Caddy | `caddy\` | Không cần; Caddy tự xin lại | Chờ vài phút khi khởi động |

Database và file video phải được sao lưu **cùng thời điểm gần nhau**: dump mới hơn file thì có video trỏ tới file chưa được chép; ngược lại thì có file mồ côi (vô hại, `cleanup` sẽ dọn output không được tham chiếu).

## Một bản dump trên cùng ổ đĩa chưa phải là phương án khôi phục

`C:\VideoPortal\backups` nằm cùng ổ với database. Nếu ổ hỏng, VPS bị xoá, hay bị mã hoá tống tiền thì mất cả hai. Cần ít nhất một bản **ngoài VPS**. Các lựa chọn 0đ:

| Lựa chọn | Cách dùng | Lưu ý |
| --- | --- | --- |
| Thư mục đồng bộ lên máy khác (ví dụ ứng dụng đồng bộ đám mây đã có sẵn tài khoản) | `-OffsitePath D:\Sync\videoportal` | Dump chứa hash mật khẩu và email: chỉ dùng nơi bạn tin cậy |
| Chia sẻ SMB tới máy ở nhà/văn phòng | `-OffsitePath \\may-khac\videoportal` | Cần đường mạng riêng (VPN); không mở SMB ra Internet |
| Tải về thủ công qua RDP mỗi tuần | Sao chép file `.dump` + `.sha256` | Dễ quên; RPO = 1 tuần |

Script in cảnh báo mỗi lần chạy mà không có bản sao ngoài VPS. **Hiện chưa có nơi lưu ngoài VPS nào được cấu hình** — đây là việc còn mở.

## `backup.ps1`

```powershell
.\backup.ps1                                            # chỉ dump tại chỗ (có cảnh báo)
.\backup.ps1 -OffsitePath \\may-khac\videoportal -IncludeStorage
```

Trình tự: `pg_dump -Fc` vào file `.partial` → `pg_restore --list` phải đọc được và có dữ liệu của `videos`, `transcode_jobs`, `outbox_events` → đổi tên thành `videoportal-<UTC>.dump` → ghi `.sha256` → (tuỳ chọn) chép ra ngoài và so hash → xoá dump cũ hơn `-KeepDays` (mặc định 14), luôn giữ 3 bản mới nhất. File chưa qua kiểm tra không bao giờ mang tên `.dump`.

Mật khẩu DB được đọc từ `config\.env` vào biến môi trường của chính tiến trình đó; không in, không đưa lên dòng lệnh.

Lịch: `register-tasks.ps1 -Apply -OffsitePath …` tạo task `VideoPortal-Backup` chạy 02:30 hằng ngày bằng `SYSTEM`.

## `restore.ps1` — luôn khôi phục vào database MỚI

```powershell
.\restore.ps1 -DumpFile C:\VideoPortal\backups\videoportal-20261117-142932.dump -AdminUser postgres -DropAfterVerify
```

- Kiểm tra SHA-256 trước; sai thì dừng, không tạo gì.
- Từ chối nếu database đích đã tồn tại hoặc trùng tên database đang chạy.
- Tạo database mới, `pg_restore`, in số dòng từng bảng, kiểm tra không có job trỏ tới video không tồn tại.
- `-DropAfterVerify` xoá **đúng database vừa tạo trong lần chạy đó** (dùng cho diễn tập).

### Diễn tập khôi phục (nên làm hằng tháng)

1. `.\backup.ps1`
2. `.\restore.ps1 -DumpFile <file mới nhất> -AdminUser postgres -DropAfterVerify`
3. So các số `RESTORE_COUNTS` với `.\status.ps1` / `local-jobs` của hệ thống đang chạy.

### Khôi phục thật sau sự cố

1. `.\stop-services.ps1`
2. `.\restore.ps1 -DumpFile <file> -AdminUser postgres -TargetDatabase video_portal_restored` (không dùng `-DropAfterVerify`)
3. Kiểm tra số dòng. Nếu ổn: sửa `POSTGRES_DB=video_portal_restored` trong `config\.env`.
4. Nếu file video cũng mất: chép `storage-objects` từ nơi lưu ngoài VPS về `C:\VideoPortal\storage\objects`.
5. `.\start-services.ps1` rồi `.\status.ps1`; mở vài video để kiểm tra.
6. Database cũ **không bị xoá** bởi quy trình này; chỉ xoá thủ công khi đã chắc chắn.

## Đã kiểm chứng (máy phát triển, PostgreSQL 16.4 portable)

| Việc | Kết quả |
| --- | --- |
| `backup.ps1` trên database có dữ liệu thật từ rehearsal | BACKUP OK trong 1.3 giây |
| `restore.ps1 -AdminUser postgres -DropAfterVerify` | RESTORE OK: videos 3, jobs 2, outputs 4, users 4; database diễn tập đã xoá |
| Test tự động `test_backup_and_restore_scripts_round_trip` | PASS: số dòng sau khôi phục khớp; dump bị sửa → từ chối; khôi phục đè database đang chạy → từ chối; không để lại database thừa |
| Sao chép ngoài máy (`-OffsitePath`, `-IncludeStorage`) | **Chưa chạy** |
| Task Scheduler | **Chưa đăng ký** (chỉ chạy chế độ plan) |

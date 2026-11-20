# Bảo mật trên VPS Windows Server

Bổ sung cho `docs/SECURITY.md` (các nguyên tắc ở đó vẫn áp dụng, trừ phần riêng của GCP). Mục "Đã kiểm chứng" chỉ nói về máy phát triển; trên VPS thật chưa có gì được kiểm chứng.

## Xác thực (Task 10)

**Đánh giá Firebase:** code Phase 03 xác minh ID token bằng Firebase Admin SDK, nhưng chưa từng có project Firebase nào được cấu hình và SDK cần Google credentials (ADC) ngay cả khi chỉ xác minh token. Giữ Firebase đồng nghĩa phải tạo một project Google mới, trái với quyết định không dùng Google Cloud. Vì vậy VPS dùng **tài khoản nội bộ** (`AUTH_PROVIDER=local`). Đường Firebase vẫn còn trong code (`AUTH_PROVIDER=firebase`, mặc định khi không cấu hình) và các test Phase 03 vẫn chạy.

| Yêu cầu | Cách làm | Kiểm chứng |
| --- | --- | --- |
| Băm mật khẩu | `werkzeug.security` scrypt, tối thiểu 12 ký tự | Test: hash bắt đầu bằng `scrypt:` |
| Phiên | Token ngẫu nhiên 256 bit; DB chỉ lưu SHA-256; hết hạn sau `SESSION_HOURS`; đăng xuất/đổi mật khẩu/khoá tài khoản thu hồi phiên | Test |
| Nơi giữ token | Chỉ trong bộ nhớ trang (header `Authorization: Bearer`), không cookie, không localStorage | Như Phase 04 |
| CSRF | Không dùng cookie phiên nên trình duyệt không tự gửi thông tin đăng nhập; không cần CSRF token | Thiết kế |
| Chống dò mật khẩu | Khoá tài khoản 15 phút sau 5 lần sai; 20 lần thử / 5 phút mỗi IP (trong bộ nhớ tiến trình API) | Test |
| Không lộ email tồn tại | Cùng mã lỗi `invalid_credentials`, vẫn băm một lần khi email không có | Test |
| Vai trò | `is_admin` cho `/api/monitor`; Owner/Viewer theo `VideoPermission` | Test |
| Tài khoản mặc định | Không có. `create-user` hỏi mật khẩu qua prompt ẩn, không nhận qua dòng lệnh | Test |

Giới hạn theo IP nằm trong bộ nhớ của một tiến trình: khởi động lại API thì bộ đếm về 0. Việc khoá theo tài khoản nằm trong DB nên không mất.

## Phân quyền

Mọi API đọc/sửa/xoá/phát đều qua `require_auth` rồi `authorized_video` ở backend; người không có quyền nhận 404 (không lộ video có tồn tại). Viewer xem được nhưng không sửa quyền, không xoá. Test `test_backend_checks_every_private_video_api` gọi thẳng từng endpoint với không token / người lạ / viewer / owner.

## Storage riêng tư

- Thư mục storage nằm ngoài `app\static`; ứng dụng từ chối khởi động production nếu `STORAGE_ROOT` nằm trong thư mục mã nguồn. Caddyfile không có `file_server`.
- Tên object phải khớp mẫu `inputs|outputs/[A-Za-z0-9._-]…`; từ chối `..`, `\`, `:`, đường dẫn tuyệt đối, tên thiết bị Windows (`CON`, `NUL`, `COM1`…), tên kết thúc bằng dấu chấm.
- Từ chối đi qua symlink/junction bên trong storage (test tạo junction thật trỏ ra ngoài).
- Ghi file: file tạm → fsync → hard link nguyên tử; object đã có thì trả 409, không ghi đè.
- Kiểm tra dung lượng trống trước khi nhận upload (507 `storage_full`).
- File phát ra chỉ qua ticket ký 120 giây, gắn với đúng object + phiên bản nội dung.

## Worker FFmpeg

- `subprocess` với danh sách tham số, `shell=False`; tên file không đi qua shell.
- ffprobe/FFmpeg chỉ cho phép giao thức `file,pipe` và danh sách định dạng cố định.
- Job Object: trần RAM, affinity 2 CPU, ưu tiên thấp, **tự kill cả cây tiến trình** khi quá thời gian, bị huỷ, hoặc worker chết (đã test bằng cách kill worker thật).
- Không có mạng nào được cấp riêng cho worker; khác với bản Docker (`--network none`), tiến trình native **không bị cô lập mạng**. Đây là điểm yếu hơn so với container; bù lại bằng whitelist giao thức của FFmpeg và tài khoản service không có quyền quản trị.

## Tài khoản service và NTFS

`install-services.ps1` dùng tài khoản ảo `NT SERVICE\VideoPortal-*` (không có mật khẩu để lưu hay lộ) và đặt ACL:

| Thư mục | API | Worker | Caddy |
| --- | --- | --- | --- |
| `app`, `venv`, `config` | Đọc | Đọc | — |
| `storage\objects` | Sửa | Sửa | — |
| `storage\temporary` | — | Sửa | — |
| `tools\ffmpeg` | — | Đọc | — |
| `logs` | Sửa | Sửa | Sửa |
| `caddy`, `tools\caddy`, `config\Caddyfile` | — | — | Sửa / Đọc |

Thư mục gốc bỏ kế thừa quyền; chỉ `Administrators` và `SYSTEM` có toàn quyền; không có `Everyone` hay `Users`. **Chưa kiểm chứng trên Windows thật** (cần quyền admin và cài service).

## Bí mật

- Mật khẩu DB chỉ nằm trong `config\.env`; script đưa SQL qua stdin và mật khẩu qua biến môi trường của tiến trình, không qua dòng lệnh.
- Khoá ký ticket nằm trong `storage\objects\.signing-key`; **không** được sao lưu ra ngoài cùng video (script backup loại trừ file này).
- Log: bộ lọc che `ticket=…`, `Bearer …`, `password/token/secret`. Log truy cập chỉ ghi path, không ghi query string. Caddy xoá `ticket` khỏi URI trong log (đã kiểm chứng trong rehearsal).

## Proxy và header

- Waitress chỉ tin `X-Forwarded-*` từ `127.0.0.1` và xoá header giả do client gửi.
- Caddy thêm HSTS, `X-Frame-Options: DENY`, ẩn header `Server`; ứng dụng đã có CSP, `nosniff`, `no-referrer`, `no-store` từ Phase 04.
- HSTS chỉ có ý nghĩa khi dùng chứng chỉ công khai thật.

## Chưa giải quyết / cần bạn quyết định

1. RDP: nên giới hạn IP nguồn hoặc dùng VPN. Script không đụng tới RDP.
2. Chưa có giới hạn tốc độ cho các API ngoài đăng nhập; với demo nhỏ thì chấp nhận được, khi mở công khai nên thêm ở Caddy.
3. Sao lưu ngoài VPS chưa được cấu hình (cần bạn cung cấp nơi lưu).
4. Windows Update và Defender là trách nhiệm vận hành của bạn; nên thêm ngoại lệ Defender cho `storage\temporary` chỉ khi đo thấy chậm, và sau khi cân nhắc rủi ro.

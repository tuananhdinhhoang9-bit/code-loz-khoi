# Báo cáo thiết kế ngắn

**Đồ án 10 môn Cloud Computing: Video Upload and Processing Portal.** Viết ngày 2026-11-21 cho bản đang chạy trên Azure, region `malaysiawest`. Mọi con số lấy từ `docs/EVIDENCE.md` và `docs/PROGRESS.md`; chỗ nào chưa đo thì ghi rõ là chưa đo. Dòng có chữ "CHƯA CÓ:" là việc còn thiếu, phải sửa lại khi làm xong.

Địa chỉ đang chạy: `https://videoportal-api.bravecoast-ef9b0b40.malaysiawest.azurecontainerapps.io` (hostname mặc định của Azure).

## 1. Bài toán và phạm vi

Người dùng tải lên video ngắn (tối đa 50 MB, 30 giây). Hệ thống giữ file ở nơi riêng tư, chuyển mã trong container thành một file MP4 H.264 tối đa 480p kèm ảnh thu nhỏ JPG và thời lượng, rồi chỉ cho chủ video và người được cấp quyền xem. Đề còn yêu cầu: hàng đợi bền vững có outbox, sự kiện lặp lại chỉ cho một kết quả, số lần thử lại có giới hạn, một buổi diễn tập dừng chuyển mã giữa chừng, giám sát và cảnh báo, hạ tầng viết bằng mã, CI/CD có rollback, ước tính chi phí.

Không làm: nhiều profile chất lượng, CDN, phát trực tiếp, bình luận, tự đăng ký tài khoản, thanh toán.

## 2. Kiến trúc đã triển khai

Toàn bộ 48 tài nguyên do Terraform trong `infra/azure/` tạo ra. Sơ đồ, đường mạng và miền lỗi: `docs/AZURE_ARCHITECTURE.md`.

| Thành phần | Dịch vụ Azure | Cấu hình đang chạy |
| --- | --- | --- |
| Trang web và API | Container Apps, app `videoportal-api` | Flask + Waitress, 0,5 vCPU, 1 GiB, đúng 1 replica; chỉ nhận HTTPS, HTTP bị chuyển hướng (301) |
| Chuyển mã | Container Apps Job `videoportal-transcode` | chạy khi hàng đợi có message (KEDA); mỗi lần chạy xử lý một video rồi thoát; 1 vCPU, 2 GiB; tối đa 1 lần chạy cùng lúc |
| Bảo trì | Container Apps Job `videoportal-maintenance` | 5 phút một lần: thu hồi lease hết hạn, gửi lại sự kiện còn sót, dọn file thừa |
| Cơ sở dữ liệu | Azure Database for PostgreSQL flexible server | bản 18, B1ms, 32 GiB, sao lưu 7 ngày; không có địa chỉ công khai, chỉ tới được từ trong VNet |
| File | Blob Storage, container `media` | riêng tư, bật versioning, tắt account key |
| Hàng đợi | Service Bus Basic, queue `transcode-jobs` | khoá message 5 phút; quá 10 lần giao thì sang dead-letter queue |
| Secret | Key Vault | chỉ giữ mật khẩu database |
| Danh tính | ba managed identity `api`, `worker`, `deploy` | không có khoá hay client secret nào |
| Image | Container Registry Basic | hai image, tag là SHA của commit |
| Log, dashboard, cảnh báo | Log Analytics, workbook "Video Portal", một alert rule | chi tiết ở `docs/AZURE_MONITORING_COST.md` |

Đường đi của một video:

1. Trình duyệt xin chỗ tải lên. API kiểm tra đăng nhập, loại file và kích thước khai báo, rồi trả về một SAS URL sống 120 giây, chỉ tạo được đúng một blob.
2. Trình duyệt `PUT` file thẳng lên Blob Storage; file không đi qua API.
3. Trình duyệt gọi `complete`. API đọc kích thước thật và version ID của blob; trong **một giao dịch** ghi Video, Job (`QUEUED`) và sự kiện outbox; commit xong mới gửi message sang Service Bus.
4. KEDA thấy message và khởi động một lần chạy job. Worker nhận job bằng lease và attempt ID, tải đúng phiên bản blob đã ghi nhận, chạy ffprobe và FFmpeg, ghi kết quả vào thư mục riêng của lần thử, rồi trong một giao dịch ghi hai con trỏ kết quả và đặt `READY`.
5. Khi xem, API kiểm tra quyền rồi mới cấp SAS chỉ đọc 120 giây trỏ vào đúng phiên bản của MP4 và ảnh thu nhỏ.

Ranh giới tin cậy: từ Internet chỉ có hai đường vào là ingress HTTPS của `api` và Blob Storage (chỉ nhận request có SAS hợp lệ). Storage, Service Bus và Key Vault vẫn có endpoint công khai nhưng chỉ nhận danh tính Entra ID. Database không có đường công khai nào. Miền lỗi: một region, một máy chủ database không dự phòng, một replica API.

## 3. Các quyết định chính và đánh đổi

Bản đầy đủ: `docs/DECISIONS.md` (ADR-024 đến ADR-029 cho Azure).

| Quyết định | Vì sao | Đánh đổi | ADR |
| --- | --- | --- | --- |
| Tải lên riêng tư bằng user delegation SAS | File không đi qua API; SAS do managed identity ký, không dùng account key; mỗi URL chỉ tạo một blob và sống 120 giây | SAS không giới hạn được kích thước, nên giới hạn 50 MB chỉ được kiểm tra có thẩm quyền ở bước `complete` (blob quá cỡ bị xoá). Đã thấy thật: file 50.000.001 byte được Blob Storage nhận (201), `complete` trả 413 | 025 |
| Outbox trong cùng giao dịch + Service Bus | Không bao giờ có job mà thiếu sự kiện, hay sự kiện mà thiếu job. API gửi ngay sau commit; job bảo trì gửi lại cái còn sót | Giao ít nhất một lần, nên có message trùng (Service Bus Basic không khử trùng). Worker phải tự chịu được việc đó | 006, 024, 025 |
| Chuyển mã bằng Container Apps Job chạy theo sự kiện, mỗi video một lần chạy | Đúng câu "bounded Container Apps Jobs" của đề; không có gì chạy (và tính tiền) giữa hai video; mỗi lần chạy có giới hạn thời gian | Mỗi video chịu khoảng 25 giây khởi động container. Chỉ chạy một video một lúc: mười clip mất khoảng mười phút | 024 |
| Lease + attempt ID + tối đa 3 lần thử | Chỉ lần thử còn giữ lease mới được công bố kết quả; lần thử cũ sống lại không ghi đè được. Nền tảng không tự thử lại (`replica_retry_limit = 0`) nên số lần thử không bị nhân lên. File sai định dạng hoặc quá dài thì `FAILED` ngay, không thử lại | Khi worker chết không kịp ghi gì, phải chờ lease hết hạn (180 giây) rồi chờ tiếp job bảo trì (tối đa 5 phút) | 013, 024 |
| Idempotency theo phiên bản nguồn và profile | Khoá logic của job là (video, version ID của blob nguồn, profile). Message lặp lại cho job đã xong là thao tác rỗng (`no_op`) | Phải bật versioning; xoá video phải xoá từng phiên bản, việc này cần role `Storage Blob Data Owner` (rộng hơn mong muốn) | 025, 026 |
| Managed identity thay cho khoá | Không có account key, connection string hay client secret trong image, biến môi trường, repo hay log. Mật khẩu database nằm trong Key Vault | Hai role rộng hơn cần thiết (Blob Data Owner trên container, Service Bus Data Owner trên queue để KEDA đếm message). Mật khẩu database đọc được trong file state cục bộ. Ứng dụng nối database bằng tài khoản quản trị của máy chủ | 026 |
| Database chỉ có đường riêng trong VNet | Database không lộ ra Internet | Azure tự tạo load balancer và địa chỉ IP cho environment: thêm khoảng 22 USD/tháng theo giá niêm yết. Không nối được database từ máy cá nhân | 026, 028 |
| Terraform, state cục bộ, apply hai bước | Dựng lại được hạ tầng từ mã; không có ID subscription hay secret trong các file `.tf` | File state (đã gitignore) chứa mật khẩu database. Không có state dùng chung nên chỉ một máy chạy được Terraform. Tenant Entra và DNS nằm ngoài Terraform | 026, 027 |
| GitHub Actions đăng nhập Azure bằng OIDC | Không lưu mật khẩu hay khoá ở GitHub; chỉ nhánh `main` đổi được token. Cũng là cách duy nhất build được image: gói sinh viên chặn `az acr build` và chặn tạo máy ảo | Bốn secret (đều là ID) phải thêm tay; phụ thuộc GitHub | 028 |
| Rollback bằng tag của image | Workflow `rollback` đưa image cũ trở lại, không test, không build, nên `main` hỏng vẫn quay lại được. Dùng chung một script với bước deploy | Tạo revision mới chạy image cũ chứ không bật lại revision cũ. Thay đổi schema phải luôn là thêm, không sửa. Terraform không còn cho biết image nào đang chạy | 029 |

Hai quyết định lệch với gợi ý của đề (nền tảng của API và cách đăng nhập) nằm ở mục 5.

## 4. Kết quả kiểm thử

Tất cả chạy trên Azure ngày 2026-11-21. Bảng chi tiết, giờ UTC và mã lần chạy: `docs/EVIDENCE.md`.

| Kiểm thử | Cách chạy | Kết quả |
| --- | --- | --- |
| Test 1 của thầy: video hợp lệ phát được, đúng profile | `scripts/acceptance_test.py`, mười clip mẫu (1–3 giây, 39–112 KB) | 50/50 PASS: `READY`, thời lượng lệch không quá 350 ms, HTTP Range 206, ffprobe đọc ra MP4 H.264 yuv420p không quá 854x480, ảnh JPEG |
| Test 2: sai định dạng, quá dài, quá lớn bị từ chối gọn | cùng script | 13/13 PASS: 400 `unsupported_content_type`, 413 `upload_too_large` (cả khi khai báo và khi gửi thật), `invalid_media`, `input_too_long`; không trường hợp nào có URL phát |
| Test 3a: sự kiện lặp lại cho một kết quả | cùng script | 2/2 PASS. Ngoài kế hoạch: job bảo trì gửi lại 3 sự kiện, cả 3 message trùng kết thúc `no_op`; 10 video, 10 dòng `READY` |
| Test 3b: không có quyền thì không xem được | cùng script | 11/11 PASS: không token 401; token giả 401; URL blob không có SAS 409, sửa chữ ký 403; người dùng thứ hai 404; cấp quyền thì xem được, thu hồi thì 404 |
| Tổng ba test | | `passed 76, failed 0, skipped 0` |
| Diễn tập ngắt lỗi | `scripts/failure_drill.py`, clip 1080p 29 giây (29,2 MB), dừng lần chạy job bằng `az containerapp job stop` lúc FFmpeg ở 22 % | 6/6 PASS. `RETRYING` sau 0,9 giây; lần thử 2 `READY` sau 60,2 giây kể từ lúc dừng; 9 lần hỏi URL phát trong lúc đó đều 409; hàng đợi và dead-letter queue trống |
| Tải (p95) | `scripts/load_test.py`: 10 người dùng, khởi động 10 giây, đo 60 giây | 3.479 request, 0 lỗi, p50 178,6 ms, **p95 285,9 ms**, p99 317,7 ms, 58 request/giây. Phía máy chủ: p95 thời gian xử lý 186 ms; CPU chạm 0,505 vCPU trên 0,5 được cấp |
| CI/CD | push lên `main`, workflow `ci` (lần chạy `44916112596`) | `test`, `images`, `deploy` đều thành công; khoảng 5 phút từ push tới revision mới khoẻ |
| Rollback | workflow `rollback` (lần chạy `44916720116`) với tag `4a6353e…` | thành công trong 87 giây; revision mới chạy image cũ, `/health` báo `database: ok` |
| Một lượt tải thật qua trang | chủ dự án tải clip 3,3 MB | từ `complete` tới `READY` 38,5 giây (một mẫu), trong đó khoảng 25 giây là khởi động container |
| Test tự động | `pytest` trên máy phát triển và job `test` trên GitHub | 185 passed, 7 skipped (máy phát triển); job `test` thành công trên Linux |
| Giám sát | workbook "Video Portal" (7 ô truy vấn), alert rule `videoportal-transcode-system-failure` | Cả 7 ô có số liệu thật. Cảnh báo đã nổ một lần trong lần diễn tập thứ hai: 3 phút 19 giây sau khi job bị dừng. Email thông báo chưa được xác nhận trong hồ sơ |

## 5. Hạn chế và điểm lệch so với đề

- **Đăng nhập bằng tài khoản nội bộ lưu trong PostgreSQL, không phải Microsoft Entra External ID như đề gợi ý.** External tenant của Entra chưa bao giờ được tạo; tài khoản nội bộ là phương án lùi đã ghi sẵn trong ADR-024 (mật khẩu băm scrypt, khoá sau 5 lần sai, chỉ quản trị viên tạo tài khoản; ADR-018). Mã xác minh OIDC đã viết và đã thử với một nhà cung cấp giả, chưa thử với Entra thật. CHƯA CÓ: sự đồng ý của thầy cho điểm lệch này.
- **API chạy trên Container Apps, không phải App Service** như đề gợi ý. Lý do: API và job dùng chung một nền tảng, một registry, một VNet và một cách cấp quyền (ADR-024).
- **Diễn tập ngắt lỗi trên Azure là dừng êm (SIGTERM):** worker còn kịp ghi lỗi. Trường hợp bị giết hẳn, phục hồi nhờ lease hết hạn, mới chỉ chạy trên máy cục bộ (`RETRYING lease_expired` sau 181 giây). Đường dead-letter và giới hạn ba lần thử chưa được kích hoạt trên Azure; chúng chỉ được kiểm bằng test tự động.
- **Thời gian phục hồi 60 giây có phần may mắn:** job bảo trì chạy 5 phút một lần và lần đó rơi vào 20 giây sau khi dừng. Trường hợp xấu nhất lâu hơn khoảng 5 phút.
- **Kiểm thử tải chỉ chạy một lần,** chỉ gồm các request đọc của API, trên một replica 0,5 vCPU, máy khách đặt ở VPS của nhóm. Không đo tải lên và chuyển mã dưới tải.
- **Mỗi lúc chỉ chuyển mã một video:** mười clip mất khoảng mười phút, clip cuối chờ 560 giây.
- **Tên miền riêng chưa chuyển sang Azure;** trang chạy trên hostname mặc định ở đầu báo cáo.
- **Số chi phí là giá niêm yết.** Ngày đầu Cost Management gần như chưa có dữ liệu (0,0125 USD, chưa có PostgreSQL và Container Apps).
- Nhỏ hơn: không có header `Strict-Transport-Security`; thu hồi quyền chỉ chặn URL mới, URL đã cấp còn sống tới 120 giây; một ô của workbook (nối request với job) chưa có dữ liệu lúc tạo.

## 6. Chi phí

Theo giá niêm yết ở `malaysiawest` ngày 2026-11-21, khi không có video nào: khoảng **67,8 USD/tháng (2,26 USD/ngày)**. Trong đó phần cố định 49,95 (database 21,05; load balancer và IP 21,90; registry 5,00; DNS 0,50; alert 1,50), API luôn bật một replica 15,55, job bảo trì 2,33. Mỗi clip chuyển mã thêm khoảng 0,00095–0,00135 USD. Đây là phép tính trên bảng giá và số đo thật, chưa phải hoá đơn, và chưa trừ các phần miễn phí của Azure for Students (chưa xác nhận có được áp dụng không). Bảng đầy đủ: `docs/AZURE_MONITORING_COST.md`. Cách dọn dẹp: `docs/CLEANUP.md`.

## 7. Hướng phát triển

1. Tạo external tenant của Entra và chuyển `auth_provider` sang `oidc` (mã đã sẵn).
2. Diễn tập giết hẳn worker và đường dead-letter trên Azure; ghi lại lần cảnh báo nổ thật.
3. Tăng `max_executions` của job chuyển mã (ví dụ 3) để hàng đợi ngắn lại, kèm một dòng trong `docs/DECISIONS.md` và một lần đo tải có tải lên.
4. Thu hẹp quyền: role riêng cho ứng dụng trong database, role hẹp hơn cho Blob và Service Bus.
5. Thêm header HSTS; chuyển tên miền riêng; đưa state của Terraform lên nơi dùng chung.
6. So số Cost Management thật với bảng giá niêm yết sau vài ngày chạy.

## 8. Đối chiếu với tiêu chí chấm

| Tiêu chí | Tỉ trọng | Nội dung trong báo cáo và tài liệu |
| --- | --- | --- |
| Kiến trúc và lập luận | 25 % | Mục 2, 3; `docs/AZURE_ARCHITECTURE.md`, `docs/DECISIONS.md` |
| Triển khai và tự động hoá | 20 % | Terraform `infra/azure/`; workflow `ci` và `rollback`; mục 4 (CI/CD, rollback) |
| Bảo mật và tính đúng đắn | 15 % | Mục 3 (SAS, managed identity, database riêng); Test 2, 3b; `docs/SECURITY.md` |
| Độ tin cậy và giám sát | 15 % | Mục 3 (outbox, lease, idempotency); Test 3a, diễn tập; workbook và alert |
| Độ hoàn thiện ứng dụng | 15 % | Test 1; luồng tải lên, xem, chia sẻ, thu hồi, xoá; kịch bản ở `docs/DEMO_SCRIPT.md` |
| Chi phí và trình bày | 10 % | Mục 6; `docs/AZURE_MONITORING_COST.md`, `docs/CLEANUP.md`, `docs/DEMO_SCRIPT.md` |

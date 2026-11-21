# Video Cloud Portal — Codex Starter Pack

Ứng dụng Flask/Jinja + PostgreSQL + FFmpeg cho đề tài số 10 “Video Upload and Processing Portal” (`references/10_video_upload_and_processing_portal.pdf`). Trạng thái chi tiết và bằng chứng kiểm thử: `docs/PROGRESS.md`.

## Bản chính: Azure (đang chạy từ 2026-11-21)

Kho chỉ còn nhánh `main`. Mỗi lần push lên `main`, GitHub Actions chạy test, build image và tự triển khai lên Azure; quay lại bản cũ bằng workflow `rollback`.

| Mục | Ở đâu |
| --- | --- |
| Trang đang chạy | `https://videoportal-api.bravecoast-ef9b0b40.malaysiawest.azurecontainerapps.io` (tên miền riêng: xem `infra/azure/README.md`) |
| Kiến trúc thực tế, luồng mạng, ranh giới bảo mật | `docs/AZURE_ARCHITECTURE.md` |
| Báo cáo thiết kế, kịch bản demo | `docs/DESIGN_REPORT.md`, `docs/DEMO_SCRIPT.md` |
| Bằng chứng kiểm thử trên Azure | `docs/EVIDENCE.md` |
| Hạ tầng (Terraform), CI/CD, rollback | `infra/azure/`, `.github/workflows/`, `deploy/azure/` |
| Giám sát, cảnh báo, chi phí | `docs/AZURE_MONITORING_COST.md` |
| Dọn dẹp tài nguyên | `docs/CLEANUP.md` |
| Script kiểm thử chạy trên bản thật | `scripts/acceptance_test.py`, `scripts/failure_drill.py`, `scripts/load_test.py`, `scripts/smoke_test.py`, `scripts/seed_remote.py` |

Ứng dụng chọn nơi chạy bằng cấu hình (`STORAGE_BACKEND`, `QUEUE_BACKEND`, `AUTH_PROVIDER`): cùng một mã chạy trên Azure, trên máy phát triển (chế độ local) và trên VPS.

**Bản dự phòng trên VPS Windows Server** vẫn chạy tại `https://video.uploadmdm.id.vn` và không liên quan tới Azure. Hai nhánh `vps` và `aws` đã được xoá khỏi GitHub ngày 2026-11-21 theo yêu cầu của chủ dự án; lịch sử của chúng nằm trong file bundle do chủ dự án giữ. AWS đã bỏ từ 2026-11-21; tài liệu và Terraform của AWS, GCP và VPS còn trong kho chỉ là tài liệu lưu trữ.

## Triển khai trên VPS Windows Server (đang chạy; tài liệu lưu trữ)

| Tài liệu | Nội dung |
| --- | --- |
| `docs/WINDOWS_VPS_ARCHITECTURE.md` | Kiến trúc, ánh xạ từ thiết kế GCP cũ, cấu trúc thư mục, tài nguyên |
| `docs/WINDOWS_VPS_SETUP.md` | Phần mềm cần cài, trình tự script, biến cấu hình, cổng và firewall |
| `docs/WINDOWS_VPS_SECURITY.md` | Tài khoản nội bộ, phân quyền, storage riêng tư, tài khoản service, NTFS |
| `docs/WINDOWS_VPS_OPERATIONS.md` | Lệnh vận hành, log, mã lỗi, xử lý sự cố |
| `docs/WINDOWS_VPS_BACKUP.md` | Sao lưu, khôi phục, diễn tập |
| `docs/WINDOWS_VPS_ROLLBACK.md` | Quay lui mã nguồn, cấu hình, dữ liệu |

Script nằm ở `scripts/windows/`. Script nào thay đổi hệ thống cũng **chỉ in kế hoạch** nếu thiếu `-Apply`:

```powershell
.\scripts\windows\preflight.ps1 -AllowNetwork        # chỉ đọc, báo PASS/WARN/FAIL
.\scripts\windows\install-prerequisites.ps1          # thư mục, venv, mẫu cấu hình, tải FFmpeg/Caddy/WinSW
.\scripts\windows\setup-database.ps1                 # role quyền tối thiểu + database + init-db
.\scripts\windows\rehearsal.ps1                      # chạy thử cả hệ thống trên loopback, không cài service
.\scripts\windows\install-services.ps1               # VideoPortal-API / -Worker / -Caddy
.\scripts\windows\start-services.ps1 ; .\scripts\windows\status.ps1
.\scripts\windows\backup.ps1 ; .\scripts\windows\restore.ps1 -DumpFile <file> -DropAfterVerify
```

Chạy thủ công không qua service (máy phát triển Windows, cần PostgreSQL và FFmpeg):

```powershell
.\.venv\Scripts\python.exe -m flask --app app.main init-db
.\.venv\Scripts\python.exe -m flask --app app.main create-user ban@example.com --admin
.\.venv\Scripts\python.exe -m app.serve              # API (Waitress) tại 127.0.0.1:8000
.\.venv\Scripts\python.exe -m app.worker_service     # worker: hàng đợi PostgreSQL + FFmpeg native
$env:RUN_DB_TESTS = '1' ; .\.venv\Scripts\python.exe -m pytest -q
```

Tài liệu và mã GCP cũ (`docs/ARCHITECTURE.md`, `docs/CLOUD_DEPLOY.md`, `docs/COST_MONITORING.md`, `infra/`, `prompts/07–12` bản GCP) được giữ lại với nhãn ARCHIVED để đối chiếu; chưa từng được áp dụng lên GCP.

## Bắt đầu trong VS Code / Codex

1. Giải nén. Mở **chính thư mục này** bằng VS Code/Codex.
2. Đọc `docs/SKILLS_INSTALL.md`, cài 4–5 skill phù hợp (cài trong thư mục này, không cài toàn bộ repository skill).
3. Mở Codex và gửi nội dung `prompts/00-START.md`. Sau đó tiếp tục `01`, `02`, ... theo thứ tự.
4. Sau mỗi giai đoạn, yêu cầu Codex cập nhật `docs/PROGRESS.md`; chỉ sang giai đoạn tiếp theo khi tiêu chí nghiệm thu được kiểm tra.
5. Chỉ tạo và sử dụng `.env` thật trên máy của bạn; file này đã được `.gitignore`. Không ghi secret thật vào chat, Git hay log.

Nếu dùng Codex IDE, có thể dán prompt rất ngắn: **“Thực hiện `prompts/03-AUTH.md`, tuân thủ `AGENTS.md`, chỉ làm phạm vi giai đoạn này.”**

## Tư tưởng thiết kế

- Python Flask + Jinja + CSS/JS thuần; PostgreSQL; FFmpeg (container trên máy dev ở Phase 05–06, tiến trình native trong Job Object trên VPS).
- Đích triển khai hiện tại: VPS Windows Server với Waitress, Caddy, PostgreSQL và FFmpeg chạy native. Thiết kế GCP trước đây (Cloud Run, Cloud SQL, Cloud Storage, Pub/Sub…) đã được lưu trữ, không còn là đích.
- Phải có **outbox + retry + idempotency + failure drill**; đây là yêu cầu môn học, không được bỏ chỉ vì khó.
- Không triển khai dịch vụ trả phí, đăng ký billing, `terraform apply/destroy`, tạo khóa/mật khẩu, hoặc đẩy code lên GitHub thay người dùng nếu không có truy cập thực tế phù hợp. Hỏi rõ trước các thao tác có thể tốn tiền/phá hủy; việc kiểm thử local được phép tự chạy.
- Không đưa thư viện, framework, tính năng ngoài yêu cầu vào chỉ để trông chuyên nghiệp.

## Tài liệu cần xem

| File | Mục đích |
| --- | --- |
| `AGENTS.md` | Quy định dùng chung cho Codex |
| `docs/REQUIREMENTS.md` | Yêu cầu gốc và scope |
| `docs/ARCHITECTURE.md` | Kiến trúc và luồng dữ liệu |
| `docs/DATA_MODEL.md` | Database |
| `docs/API_CONTRACT.md` | API / bảo mật luồng xem |
| `docs/PIPELINE_RELIABILITY.md` | Outbox, queue, retry, chống trùng |
| `docs/SECURITY.md` | Access control, secret, network |
| `docs/PHASES.md` | Thứ tự triển khai, tiêu chí nghiệm thu |
| `docs/TEST_PLAN.md` | Test cases và minh chứng |
| `docs/CLOUD_DEPLOY.md` | Quy tắc triển khai và rollback |
| `docs/COST_MONITORING.md` | Chỉ số và quản lý ngân sách |
| `docs/DELIVERABLES.md` | Checklist nộp bài |
| `docs/PROGRESS.md` | Trạng thái hiện tại, được Codex cập nhật |
| `docs/DECISIONS.md` | Ghi lại quyết định công nghệ |
| `docs/SKILLS_INSTALL.md` | Link nguồn và lệnh cài skill đã kiểm tra |

## Chạy local — Phase 01 (PowerShell)

Cần Python 3.12 và Docker Desktop đang chạy với Linux containers/Compose. Nếu máy báo thiếu WSL, hoàn thành cài đặt WSL2 và khởi động lại theo yêu cầu của Docker Desktop trước khi tiếp tục.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
docker --version
docker compose version
docker info
```

Tạo file `.env` thật tại thư mục gốc nếu chưa có. Các biến cần cấu hình: `POSTGRES_HOST` (local: `127.0.0.1`), `POSTGRES_PORT` (mặc định `5432`), `POSTGRES_DB` và `POSTGRES_USER` (mặc định `video_portal`), `POSTGRES_PASSWORD`. File local đã được chuẩn bị với mật khẩu để trống; tự đặt mật khẩu local trước khi chạy DB, không dán vào chat hoặc commit. Ứng dụng đọc file này, không dùng `.env.example`. Biến môi trường có sẵn được ưu tiên hơn `.env`.

```powershell
docker compose config --quiet
docker compose up -d --wait db
.\.venv\Scripts\python.exe -m pytest -q
$env:RUN_DB_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest -q -m integration
Remove-Item Env:RUN_DB_TESTS
.\.venv\Scripts\python.exe -m flask --app app.main run --debug
```

Mở `http://127.0.0.1:5000/` và `http://127.0.0.1:5000/health`. Health trả `200` chỉ khi truy vấn PostgreSQL thành công; thiếu mật khẩu hoặc DB không truy cập được trả `503`. Test mặc định bỏ qua kiểm thử PostgreSQL thật; chỉ bật `RUN_DB_TESTS=1` khi DB đã sẵn sàng. Test với mock không thay thế kiểm thử DB thật.

Chỉ dùng debug server trên máy local. DB chỉ mở cổng loopback, dữ liệu giữ trong volume `postgres_data`. Dừng bằng `docker compose stop db`; không dùng `down -v` khi cần giữ dữ liệu. Đổi mật khẩu trong `.env` không tự đổi mật khẩu của DB đã được khởi tạo trong volume; không xóa volume để sửa lỗi một cách tự động.

## Phân biệt việc đã làm và chưa làm

Các Phase 01–06 chạy local: Flask/PostgreSQL, xác minh token Firebase bằng SDK, private storage local và worker Docker/FFmpeg có outbox/retry. Firebase thật, GCS, CI/CD và hạ tầng Cloud chưa được nghiệm thu. Xem `docs/PROGRESS.md` để biết bằng chứng và phần BLOCKED.

## Schema và seed local — Phase 02

Cần DB ở trạng thái healthy và `ffmpeg`/`ffprobe` có trong PATH. Chỉ chạy lệnh seed trên DB local dành cho demo.

```powershell
.\.venv\Scripts\python.exe -m app.seed_media --output-dir .local/seed
.\.venv\Scripts\python.exe -m flask --app app.main init-db
.\.venv\Scripts\python.exe -m flask --app app.main seed-db
$env:RUN_DB_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:RUN_DB_TESTS
```

`init-db` chỉ tạo bảng còn thiếu, không drop/reset hay tự migrate bảng cũ. `seed-db` dùng một transaction cho Video/Job/Outbox và permissions; chạy lặp giữ nguyên ID/số dòng. Nếu dữ liệu seed đã bị sửa hoặc xử lý, lệnh dừng và rollback thay vì ghi đè. Dùng DB local riêng khi cần một bộ seed mới; không tự xóa dữ liệu.

Bộ seed có 10 clip tổng hợp 320×180 H.264/AAC, dài 1–3 giây, manifest ghi SHA256/kích thước/thời lượng kỳ vọng và một profile `mp4-480p`. `demo-owner` sở hữu cả 10 clip; `demo-viewer` được gán quyền cho clip số chẵn (5 clip). Đây là UID fixture, chưa phải tài khoản đăng nhập. Thư mục `.local/` được gitignore; tái tạo media bằng lệnh trên, không đưa video phát sinh vào Git.

Job mới seed ở trạng thái QUEUED, chưa có OutputObject. Sau khi chạy local-process, trạng thái thay đổi theo xử lý thật; không chạy seed-db để ghi đè dữ liệu đã xử lý. Giá trị `local-sha256:<hash>` chỉ là phiên bản nội dung fixture local, không phải generation GCS; tích hợp storage phải lấy generation thật. FFmpeg cùng phiên bản tạo lại cùng hash trong kiểm thử; không bảo đảm bitstream giống nhau giữa các phiên bản FFmpeg.

Kiểm thử DB tạo một schema tên `test_phase02_<UUID>` riêng cho mỗi test, rồi chỉ dọn schema vừa tạo; không drop bảng dữ liệu demo trong `public`. Chạy test cần quyền tạo schema trên PostgreSQL local. Không dùng cấu hình DB production để chạy test này.

Nếu Windows từ chối bind cổng 5432, đặt `POSTGRES_PORT` trong `.env` sang cổng local còn trống (máy hiện tại dùng `55432`), rồi chạy lại `docker compose up -d --wait db`. Không dừng dịch vụ khác hoặc xóa volume để giải quyết xung đột cổng.


## Xác thực — Phase 03

Server dùng Firebase Admin SDK chính thức. Đặt FIREBASE_PROJECT_ID trong .env và dùng Application Default Credentials / workload identity hợp lệ khi kết nối Firebase thật; không tạo service-account JSON key. Chưa cấu hình thì API riêng tư trả 503, thiếu/sai/hết hạn token trả 401. Gửi Firebase ID token bằng Authorization: Bearer; không gửi UID thay token. /api/me trả danh tính đã xác minh; /api/videos/<UUID> chỉ cho Owner hoặc Viewer có VideoPermission. Người không được phép nhận 404, không có object path/URL.

Verifier tùy chỉnh chỉ cho TESTING=True. Runtime từ chối FIREBASE_AUTH_EMULATOR_HOST để không vô tình bật đường bỏ qua chữ ký. SDK kiểm tra chữ ký, issuer, audience và expiry; hiện dùng verify_id_token mặc định, chưa kiểm tra thu hồi token theo từng request (token đã thu hồi có thể dùng đến expiry). Việc thu hồi VideoPermission vẫn được kiểm tra lại trên mỗi API call. Chưa có Firebase project/demo login thật trong môi trường này.


## Portal riêng tư — Phase 04

Chạy Flask bằng lệnh local ở trên rồi mở trang chủ. Đăng nhập bằng email/mật khẩu của tài khoản Firebase đã được cấp. Trình duyệt gửi mật khẩu trực tiếp qua HTTPS tới Firebase REST API; server chỉ nhận và xác minh ID token. Token chỉ nằm trong bộ nhớ trang, không localStorage/sessionStorage/cookie; tải lại trang hoặc hết hạn thì đăng nhập lại. Không có tài khoản demo giả ở runtime.

Cấu hình riêng trong .env: FIREBASE_PROJECT_ID và FIREBASE_WEB_API_KEY cùng project, cùng ADC/workload identity hợp lệ cho server. Web API key là cấu hình client công khai do Firebase thiết kế, không phải service-account credential; endpoint /api/auth/config chỉ trả web key và request_id. Không ghi mật khẩu/token/service-account key vào source hoặc log. Cần provider Email/Password và demo accounts đã được quản trị viên thiết lập; bước tạo Cloud/project/account chưa được thực hiện trong task này.

Storage hiện là LocalStorage thay được bằng GCS adapter sau này: file/metadata và khóa ký ở .local/objects, ngoài static. URL ký có TTL 120 giây, ràng buộc đúng operation/path/content type/size hoặc generation. PUT chỉ ghi một lần, giới hạn byte thực; complete kiểm tra metadata thực và commit Video/Job/Outbox cùng transaction. Không có URL công khai cho file source. Khi lỗi upload khiến object thiếu metadata, tạo lượt upload mới; chưa có tác vụ dọn orphan tự động. Giữ bí mật thư mục .local và khóa ký; đây không phải cơ chế bảo vệ trước người có quyền đọc ổ đĩa máy local.

Danh sách trả tối đa 100 video được phép xem. Chọn video để xem trạng thái, cấp/thu hồi quyền theo Firebase UID (chỉ Owner), hoặc yêu cầu phát/thumbnail. Chỉ trả URL khi cả MP4 và JPG đã được xuất bản đầy đủ và khớp version. URL đã cấp còn hiệu lực đến TTL kể cả sau khi thu hồi quyền; quyền thu hồi ngăn cấp URL mới. URL ký được che trong access log Werkzeug; không bật log request/query/body ở reverse proxy khác.

Validation Phase 04 kiểm tra title, MIME allowlist và size thực <=50 MB. Extension/MIME không chứng minh nội dung hợp lệ: FFprobe kiểm tra codec/duration/dimensions trong worker Phase 05 (chưa có). Hiện upload hợp lệ được QUEUED, không có tiến độ giả và không tự READY. Các READY/output trong test là fixture hợp đồng storage, không phải bằng chứng transcode. K_SERVICE (Cloud Run) bị từ chối khi chỉ có local storage; không deploy bản local này lên Cloud.

Kiểm tra: RUN_DB_TESTS=1 chạy toàn bộ pytest; API tests dùng verifier giả chỉ trong TESTING=True, thêm test SDK thật với chữ ký RSA. Browser QA dùng test-only app/schema và mock riêng lời gọi Firebase provider, kiểm thử API/upload/storage/PostgreSQL thật; không thay thế đăng nhập Firebase hay GCS production.


## FFmpeg container — Phase 05

Bộ chuyển đổi độc lập chỉ nhận file local, không nhận URL hoặc credentials. Profile duy nhất: MP4 H.264/yuv420p, AAC nếu có audio, tối đa 854x480, 30 fps; không kéo giãn video dọc, JPG lấy từ MP4 đã kiểm tra. File input <=50,000,000 bytes, <=30 giây; một video stream, tối đa một audio stream; kích thước 2–4096 mỗi cạnh, <=8,847,360 pixel, <=60 fps và pixel vuông. Container chỉ cho demuxer MOV/MP4/WebM/Matroska, codec allowlist trong worker/transcode.py. Pixel không vuông bị từ chối rõ ràng thay vì làm sai tỉ lệ.

```powershell
docker build -t video-worker:phase05 -f worker/Dockerfile .
$env:RUN_DB_TESTS='1'
$env:RUN_DOCKER_TESTS='1'
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:RUN_DB_TESTS
Remove-Item Env:RUN_DOCKER_TESTS
```

Test Docker mount input readonly và một thư mục attempt trống để output; chạy non-root, network none, filesystem readonly, 1 CPU, 512 MB RAM, 64 pids và tmpfs 32 MB. ffprobe timeout 10 giây, encode 90 giây, thumbnail 15 giây; file output có trần 50 MB. Worker chỉ ghi metadata.json sau khi MP4 + JPG được xác minh; không tự publish DB READY trong Phase 05. Lỗi có mã gọn, không in file content/credentials. Thư mục output phải trống: không tự ghi đè kết quả lần trước.

Các test host chạy FFmpeg thật; test Docker chỉ bật khi RUN_DOCKER_TESTS=1 và image đã build. Không dùng kết quả SKIP để đánh dấu gate container PASS. Con số duration_ms của metadata là độ dài video đầu ra; processing duration của job được ghi riêng ở giai đoạn reliability.

## Hàng đợi và phục hồi local — Phase 06

Cần PostgreSQL healthy, image video-worker:phase05 đã build và FFmpeg/ffprobe host để xác minh output độc lập. Runtime đọc .env thật; không cần fake login để chạy worker.

```powershell
.\.venv\Scripts\python.exe -m flask --app app.main local-process --limit 10
.\.venv\Scripts\python.exe -m flask --app app.main local-jobs
# Chỉ khi chủ động xử lý một job FAILED; thay UUID bằng ID thật từ local-jobs:
.\.venv\Scripts\python.exe -m flask --app app.main retry-job <JOB_UUID>
```

Mỗi local-process chỉ chạy một vòng bounded, tối đa 10 message. Chạy lại sau thời gian retry (5/10 giây); cần tiếp tục gọi lệnh này để reconcile lease hết hạn, không có daemon tự chạy. Lease PROCESSING là 180 giây; Docker timeout 150 giây. Worker bị dừng hoặc máy khởi động lại được phục hồi khi vòng sau reconcile lease hết hạn. Tối đa 3 attempt tự động/job, tối đa 5 lần publish/dispatch mỗi vòng retry; hết giới hạn hoặc media hỏng chuyển FAILED. retry-job là thao tác operator mở một campaign tối đa 3 attempt mới, không reset READY.

Queue file bền vững nằm dưới .local/queue; fake broker chỉ ở tests. Output private nằm ở outputs/jobUUID/attemptUUID; chỉ pointer của attempt thắng được commit cùng READY sau khi cả MP4/JPG được kiểm tra. File của attempt chết chưa có pointer không được cấp URL. Scratch/orphan được giữ private để điều tra; chưa có tự động dọn, cần theo dõi dung lượng local. Giới hạn encode/attempt không thay thế quota ổ đĩa tổng.

APP_ENV khác local hoặc Cloud Run K_SERVICE sẽ chặn khởi động với adapter hiện tại; custom token verifier chỉ được phép khi TESTING=True. Không dùng queue/storage local hoặc fake authentication cho production. Firebase/GCS/PubSub/Cloud Run thật cần tích hợp và nghiệm thu Phase 08. Test kill Docker local không thay thế failure drill Cloud Run Phase 09.

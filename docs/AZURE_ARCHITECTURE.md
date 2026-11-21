# Kiến trúc trên Azure (mục tiêu triển khai từ 2026-11-21)

**Trạng thái: THIẾT KẾ + ADAPTER TRONG CODE (Phase 07, 2026-11-21).** Adapter Blob Storage, Service Bus, đăng nhập OIDC, chế độ worker chạy một vòng và lệnh `maintain` đã viết và kiểm thử trên máy bằng fake, bằng SDK thật với lớp vận chuyển giả, và bằng một nhà cung cấp OIDC giả trong trình duyệt; **ứng dụng chưa gọi Azure lần nào, chưa có tài nguyên nào, image chưa build lần nào**. Hạ tầng đã viết bằng Terraform trong `infra/azure/` và qua `terraform validate` (Phase 08, 2026-11-21), đã `plan` trên subscription thật (32 tài nguyên cho bước nền, 35 cho cấu hình đầy đủ), nhưng **chưa `apply`**. Mọi mục về hạ tầng dưới đây là kế hoạch cho đến khi `docs/PROGRESS.md` ghi PASS kèm bằng chứng thật. Quyết định: ADR-024, ADR-025 trong `docs/DECISIONS.md`.

Lý do đổi: chủ dự án quyết định bỏ AWS và chỉ làm Azure (2026-11-21). Đề bài (`references/…pdf`, trang 1–2) cho chọn một trong AWS / Azure / GCP. Dòng Azure trong bảng gợi ý của đề: *App Service API; Azure Database for PostgreSQL; Blob Storage; Service Bus; Functions or Container Apps workers. Use bounded Container Apps Jobs for conversion.* Về danh tính: *Use … Entra External ID on Azure … or justify another OIDC provider. … put secrets in … Key Vault.*

Phần AWS (ADR-021/022/023, `docs/AWS_ARCHITECTURE.md`, `infra/aws/`, các prompt AWS) là tài liệu lưu trữ; mã adapter AWS và `deploy/aws/` đã được gỡ khỏi `main` ở Phase 07; nhánh `aws` trên GitHub giữ nguyên bản AWS cuối cùng. Trên AWS chỉ từng tạo một chứng chỉ ACM (miễn phí), chưa xoá. Bản VPS vẫn chạy nguyên trạng và không bị sửa trong lúc chuyển.

## Sơ đồ (dự kiến)

```text
Trình duyệt ──HTTPS──> Container Apps: app "api" (ingress ngoài, chỉ HTTPS; container Flask + Waitress)
     │                      │ managed identity "api": cấp SAS, gửi message, đọc secret
     │                      ▼
     │        Azure Database for PostgreSQL flexible server
     │        (private access: subnet riêng trong VNet, không có địa chỉ public)
     │                      ▲
     │                      │ claim job (lease + attempt ID, như hiện tại)
     │        Container Apps Job "transcode" (event-driven, FFmpeg trong container)
     │          có message thì mới chạy; mỗi lần chạy xử lý một job rồi thoát; có replica timeout
     │                      │                 ▲ KEDA đếm message trong queue
     │                      ▼                 │
     └────SAS URL────> Blob Storage riêng tư      Service Bus queue ──quá số lần giao──> dead-letter queue
        (upload / phát / thumbnail)                       ▲
        inputs/   outputs/<job>/<attempt>/                │ relay outbox
                                                          │
        Container Apps Job "maintenance" (theo lịch): reconcile lease hết hạn, relay outbox còn sót, dọn dẹp

Microsoft Entra External ID: đăng nhập; API xác minh ID token qua JWKS.
Key Vault: mật khẩu DB.   Log Analytics + Azure Monitor: log JSON, dashboard, 1 alert → email.
Container Registry: image api và worker.   Terraform: `infra/azure/`.   GitHub Actions: test, build, deploy, rollback.
```

## Ánh xạ từ code hiện có

| Hiện tại (local / VPS) | Azure | Việc phải làm trong code (Phase 07) |
| --- | --- | --- |
| Waitress sau Caddy (`app/serve.py`) | Container `api` trên Container Apps, ingress ngoài | `deploy/azure/Dockerfile` (target `api`); tin `X-Forwarded-*` từ ingress (`TRUSTED_PROXY=*`); log ra stdout |
| PostgreSQL trên VPS | Azure Database for PostgreSQL flexible server, private access | Không đổi model; `init-db` chạy một lần bằng một lần chạy job; mật khẩu lấy từ Key Vault |
| Thư mục NTFS + ticket ký (`app/storage.py`) | Blob Storage riêng tư, bật versioning | Adapter mới cùng giao diện `upload_target/read_url/head/write/delete/download`. `source_generation` = version ID của blob nguồn |
| Bảng `queue_messages` (`app/queue_pg.py`) | Service Bus queue + dead-letter queue có sẵn | Broker mới cùng giao diện `publish/receive/ack/dead_letter/extend`; heartbeat gia hạn lock của message |
| Worker native chạy liên tục (`app/worker_service.py`) | Container Apps Job `transcode`, event-driven | Thêm chế độ "chạy một vòng rồi thoát": reconcile → relay → nhận một message → một job → thoát |
| Vòng lặp reconcile/relay/cleanup trong worker | Container Apps Job `maintenance` theo lịch + API relay ngay sau khi commit | Các hàm `reconcile`, `relay`, `cleanup_all` đã có; thêm một lệnh CLI gọi chúng một vòng rồi thoát; API gọi relay sau `complete`, lỗi thì để job theo lịch lo |
| Tài khoản nội bộ (`app/auth_local.py`) | Microsoft Entra External ID | Bộ xác minh OIDC chung `app/auth_oidc.py` giữ lại (issuer, audience, JWKS); trang đăng nhập đổi sang chuyển hướng authorization code + PKCE; `admin` lấy từ app role |
| File `.env` + NTFS ACL | Key Vault + biến môi trường của container | Không đọc file `.env` trong container |
| Log file xoay vòng + `healthcheck.ps1` | Log Analytics, dashboard, alert | `LOG_DIR` để trống → log JSON ra stderr (đã hỗ trợ) |
| Script PowerShell plan/`-Apply` | Terraform `infra/azure/` | Viết mới ở Phase 08 |

**Giữ nguyên:** model dữ liệu, outbox giao dịch, khoá logic `(video, source_generation, profile)`, lease + attempt UUID, tối đa 3 lần thử, chỉ công bố khi MP4 và JPG đã kiểm tra, `worker/transcode.py`, giao diện, toàn bộ test của chế độ local. Chế độ `local` (thư mục + hàng đợi PostgreSQL + tài khoản nội bộ) vẫn là mặc định để phát triển, chạy test và chạy trên VPS.

**Đã gỡ ở Phase 07:** `app/storage_s3.py`, `app/queue_sqs.py`, nhánh Cognito và form POST của S3 trong `portal.js`, `boto3` trong `requirements.txt`, `tests/test_aws_adapters.py`, `deploy/aws/`, job `images` của AWS trong CI. Bản AWS đầy đủ còn ở nhánh `aws`.

## Cấu hình của container (Phase 07)

Image build từ `deploy/azure/Dockerfile` (target `api` và `worker`) đã đặt sẵn `APP_ENV=production`, `STORAGE_BACKEND=blob`, `QUEUE_BACKEND=servicebus`, `AUTH_PROVIDER=oidc`, `DISPATCH_SECONDS=300`, `WORK_ROOT`. Container Apps phải cấp thêm:

| Biến | Nguồn | Ghi chú |
| --- | --- | --- |
| `AZURE_CLIENT_ID` | Terraform | Client ID của user-assigned managed identity; SDK dùng nó để chọn identity |
| `AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_CONTAINER` | Terraform | Tài khoản bật versioning, tắt truy cập công khai và tắt account key; CORS cho origin của trang (PUT, GET, HEAD; header `x-ms-blob-type`, `x-ms-blob-content-type`, `content-type`) |
| `SERVICEBUS_NAMESPACE`, `SERVICEBUS_QUEUE` | Terraform | Tên namespace (không kèm `.servicebus.windows.net`); queue đặt lock 5 phút và `MaxDeliveryCount` |
| `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_JWKS_URL`, `OIDC_AUTHORIZE_URL`, `OIDC_TOKEN_URL`, `OIDC_LOGOUT_URL` (tuỳ chọn) | Tài liệu OpenID configuration của external tenant | Đều là giá trị công khai, bắt buộc `https`. App registration kiểu SPA, redirect URI là địa chỉ gốc của trang (`https://<host>/`), có app role `admin` |
| `OIDC_EMAIL_CLAIM`, `OIDC_ADMIN_ROLE` | Tuỳ chọn | Mặc định `email` và `admin` |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` | Terraform | Tên máy chủ trong private DNS zone |
| `POSTGRES_PASSWORD` | Key Vault reference | Không nằm trong image, Terraform output hay log |
| `MAX_UPLOAD_BYTES`, `FFMPEG_THREADS`, `TRANSCODE_TIMEOUT_SECONDS` | Tuỳ chọn | Mặc định 50 MB, 1 luồng, 90 giây |

Lệnh của từng thành phần: `api` chạy `python -m app.serve`; job `transcode` chạy image `worker` với lệnh mặc định `python -m app.worker_service --once`; job `maintenance` chạy image `api` với lệnh `flask --app app.main maintain`.

Quyền cần cho hai identity, suy ra từ code và **chưa được kiểm chứng bằng role assignment thật** — `api`: lấy user delegation key (Storage Blob Delegator ở mức storage account), đọc/ghi/xoá blob và xoá phiên bản trong container (SAS chỉ có hiệu lực trong phạm vi quyền của identity ký nó), Service Bus Data Sender, Key Vault Secrets User. `worker` (dùng cho cả hai job): đọc `inputs/`, ghi và xoá trong `outputs/`, xoá phiên bản, Service Bus Data Sender + Data Receiver, Key Vault Secrets User.

`scripts/smoke_test.py` và `scripts/seed_remote.py` không tự đăng nhập OIDC được (cần trình duyệt): người chạy đăng nhập trên trang rồi đưa ID token vào biến môi trường `PORTAL_ID_TOKEN`.

## Các lựa chọn thiết kế và đánh đổi

1. **API chạy trên Container Apps, không phải App Service** (đề gợi ý "App Service API"). Lý do: API và job chuyển mã dùng chung một nền tảng, một registry, một VNet và một cách cấp quyền; app co về 0 replica khi không ai dùng nên không tốn tiền lúc nghỉ; chứng chỉ cho tên miền riêng miễn phí. Đánh đổi: lệch chữ với gợi ý của đề; request đầu tiên sau khi nghỉ phải chờ container khởi động (chưa đo). Nếu thầy yêu cầu đúng App Service thì image `api` chạy được trên App Service for Containers mà không đổi code.
2. **Chuyển mã bằng Container Apps Job chạy theo sự kiện**, đúng câu "Use bounded Container Apps Jobs for conversion" của đề. KEDA đếm message trong queue; có message thì nền tảng khởi động một lần chạy, lần chạy đó xử lý một job rồi thoát. Giới hạn: tối đa 1 lần chạy đồng thời, `replica timeout` lớn hơn `TRANSCODE_TIMEOUT_SECONDS`, `replica retry limit = 0` (thử lại do lease trong DB quyết định, tối đa 3 lần, không để nền tảng nhân thêm). Thời hạn chờ worker nhận job sau khi event được gửi là `DISPATCH_SECONDS`; image Azure đặt 300 giây thay cho 30 giây của worker chạy liên tục, vì lần chạy job còn phải chờ KEDA và chờ container khởi động. Đánh đổi: phải thêm chế độ "một vòng rồi thoát" cho worker và một job theo lịch; mỗi clip chịu thêm thời gian khởi động container và chu kỳ thăm dò của KEDA (mặc định 30 giây). Thiết kế AWS cũ dùng một worker chạy liên tục; trên Azure cách đó vừa lệch đề vừa tốn tiền cả khi không có video.
3. **Ai đẩy outbox sang queue.** API gọi relay ngay sau khi giao dịch `complete` đã commit (lỗi thì chỉ ghi log). Job `maintenance` chạy theo lịch (dự kiến 5 phút một lần) làm lại việc đó cho các event còn sót, thu hồi lease hết hạn và dọn dẹp. Như vậy không có tiến trình nào chạy liên tục. Giao dịch nghiệp vụ và event vẫn commit cùng nhau; relay luôn xảy ra sau commit.
4. **Upload bằng user delegation SAS**: trình duyệt `PUT` thẳng lên Blob Storage với header `x-ms-blob-type: BlockBlob`. SAS được ký bằng managed identity của `api`, không dùng account key; chỉ có quyền tạo đúng một blob, sống 120 giây. **SAS không có tham số giới hạn kích thước** (khác presigned POST của S3), nên giới hạn được kiểm tra ở trình duyệt trước khi gửi và kiểm tra lại có thẩm quyền ở bước `complete` (đọc kích thước thật của blob; quá giới hạn thì xoá blob và từ chối). Rủi ro còn lại: người đã đăng nhập có thể đẩy một blob lớn; nó bị xoá khi họ gọi `complete`, còn nếu họ không gọi thì nằm đó tới lần dọn dẹp upload bỏ dở (24 giờ). Một lần `Put Blob` tối đa 5.000 MiB.
5. **Blob versioning bật**: mỗi lần ghi trả về `x-ms-version-id`; đó là `source_generation`. URL phát video và thumbnail là SAS chỉ đọc trỏ vào đúng phiên bản. Xoá video phải xoá mọi phiên bản (xoá blob hiện tại không xoá phiên bản cũ). Trình duyệt gọi thẳng Blob Storage nên dịch vụ Blob cần luật CORS cho đúng origin của trang, và CSP của trang phải cho host của storage account ở `connect-src`, `media-src`, `img-src`.
6. **Service Bus bậc Basic**, một queue. Lock của message tối đa 5 phút nên heartbeat của worker gia hạn lock trong lúc job chạy. Quá `MaxDeliveryCount` (mặc định 10) thì message tự sang dead-letter queue; message hỏng được worker chủ động đưa sang đó kèm lý do. Xác thực bằng managed identity (role Data Sender / Data Receiver), tắt xác thực bằng khoá.
7. **Database chỉ có đường riêng.** PostgreSQL flexible server tạo với private access: một subnet uỷ quyền cho `Microsoft.DBforPostgreSQL/flexibleServers` và một private DNS zone. Môi trường Container Apps nằm trong cùng VNet (subnet riêng, tối thiểu `/27`, uỷ quyền cho `Microsoft.App/environments`). Database không có địa chỉ public; chỉ `api` và hai job tới được. Đánh đổi: không nối được DB từ máy cá nhân; `init-db` và seed phải chạy bằng job trong VNet.
8. **Đăng nhập bằng Microsoft Entra External ID** (đề nêu đích danh). Trang chuyển hướng sang trang đăng nhập của Entra theo authorization code + PKCE rồi nhận ID token; API xác minh chữ ký, issuer và audience bằng bộ xác minh OIDC đã có. Không dùng native authentication: tài liệu ghi rõ SPA dùng native authentication cần proxy hoặc luật CORS ở biên. Trang kiểm tra `state` và `nonce`; token chỉ nằm trong bộ nhớ của trang như trước. Danh tính là e-mail trong ID token, nên tenant phải bắt xác minh e-mail khi đăng ký (API không tự kiểm chứng được điều đó; nếu token có `email_verified` thì nó phải là `true`). Đánh đổi so với hiện tại: người dùng rời trang để đăng nhập; tải lại trang là phải bấm đăng nhập lại; phải tạo "external tenant", việc này cần quyền Tenant Creator trên subscription. **Nếu tài khoản sinh viên không tạo được external tenant**, phương án lùi là giữ tài khoản nội bộ (`AUTH_PROVIDER=local`) và ghi rõ đây là lệch đề cần thầy đồng ý, không lặng lẽ thay thế.
9. **Danh tính và secret.** Hai user-assigned managed identity: `api` (cấp SAS, đọc/xoá blob, gửi message, đọc secret) và `worker` (đọc `inputs/`, ghi `outputs/`, nhận và gửi message, đọc secret). Mật khẩu DB sinh ngẫu nhiên, nằm trong Key Vault, vào container qua Key Vault reference. Không có account key, connection string hay client secret nào trong image, biến môi trường thường, Terraform output hay log.
10. **Thu hồi quyền**: như hiện tại, chỉ chặn URL mới; SAS đã cấp sống tới khi hết hạn (120 giây).
11. **Dữ liệu trên VPS không được chuyển sang.** Database Azure bắt đầu trống, nạp bằng seed 10 clip chuẩn.

## Đã đối chiếu với tài liệu Microsoft Learn (đọc ngày 2026-11-21)

| Điều | Nguồn |
| --- | --- |
| Job có ba kiểu kích hoạt: thủ công, theo lịch (cron 5 trường, giờ UTC), theo sự kiện (KEDA); chu kỳ thăm dò mặc định 30 giây; có `replica timeout` và `replica retry limit` (đặt 0 để không thử lại) | `learn.microsoft.com/azure/container-apps/jobs` |
| Luật scale cho Service Bus hỗ trợ managed identity (trang không nói riêng cho job) | `…/container-apps/scale-app` |
| Gói Consumption: mỗi tháng, mỗi subscription miễn phí 180.000 vCPU-giây, 360.000 GiB-giây, 2 triệu request; co về 0 replica thì không tính tiền; job tính theo giá active, không có giá idle | `…/container-apps/billing` |
| Chứng chỉ managed cho tên miền riêng miễn phí; tên miền con cần bản ghi CNAME trỏ thẳng về hostname của app và bản ghi TXT `asuid` | `…/container-apps/custom-domains-managed-certificates` |
| VNet riêng: subnet tối thiểu `/27` và phải uỷ quyền cho `Microsoft.App/environments` (môi trường workload profiles) | `…/container-apps/custom-virtual-networks` |
| Secret của Container Apps có thể là Key Vault reference đọc bằng managed identity (role Key Vault Secrets User) | `…/container-apps/manage-secrets` |
| Lock của message: mặc định 1 phút, tối đa 5 phút, gia hạn được; hết lock thì message được giao lại; `MaxDeliveryCount` mặc định 10 rồi sang dead-letter queue; ứng dụng tự dead-letter kèm lý do được | `…/service-bus-messaging/message-transfers-locks-settlement`, `…/service-bus-dead-letter-queues` |
| Service Bus có role Data Sender / Data Receiver / Data Owner và tắt được xác thực bằng khoá | `…/service-bus-messaging/service-bus-managed-service-identity` |
| User delegation SAS: cần quyền `generateUserDelegationKey` (có trong role Storage Blob Delegator); khoá sống tối đa 7 ngày; `sr=b` cho một blob, `sr=bv` cho một phiên bản; bảng tham số không có tham số nào giới hạn kích thước | `learn.microsoft.com/rest/api/storageservices/create-user-delegation-sas` |
| Versioning: mỗi lần ghi trả về header `x-ms-version-id`; xoá blob hiện tại vẫn giữ các phiên bản cũ; xoá một phiên bản cần quyền `deleteBlobVersion` | `…/storage/blobs/versioning-overview` |
| `Put Blob` cần header `x-ms-blob-type`; tối đa 5.000 MiB một lần | `…/rest/api/storageservices/put-blob` |
| CORS đặt theo từng dịch vụ lưu trữ (origin, method, header) | `…/rest/api/storageservices/cross-origin-resource-sharing--cors--support-for-the-azure-storage-services` |
| External tenant cần một subscription và role Tenant Creator; SPA dùng authorization code + PKCE được; SPA dùng native authentication cần proxy/CORS ở biên | `learn.microsoft.com/entra/external-id/customers/quickstart-tenant-setup`, `…/entra/identity-platform/concept-native-authentication` |
| PostgreSQL flexible server có bản 18 (bản phụ 18.6); private access cần subnet uỷ quyền (tối thiểu `/28`) và private DNS zone kết thúc bằng `.postgres.database.azure.com`; SKU nhỏ nhất B1ms = 1 vCore, 2 GiB | `…/azure/postgresql/flexible-server/concepts-supported-versions`, `…/concepts-networking-private`, `…/concepts-compute` |
| Azure for Students: 100 USD credit, không cần thẻ, hạn một năm | `learn.microsoft.com/azure/education-hub/about-azure-for-students` |

### Đối chiếu thêm ở Phase 08 (đọc ngày 2026-11-21)

| Điều | Nguồn |
| --- | --- |
| Dừng một lần chạy job: `az containerapp job stop --job-execution-name …`; xem các lần chạy: `az containerapp job execution list` | `learn.microsoft.com/cli/azure/containerapp/job` |
| Terraform `azurerm_container_app_job`: luật scale có `identity_id`; secret nhận `key_vault_secret_id` + `identity`; registry nhận `identity`; có `replica_timeout_in_seconds`, `replica_retry_limit` | tài liệu provider azurerm (`container_app_job`) |
| KEDA `azure-servicebus`: khi dùng identity thì bắt buộc `namespace`; `messageCount` mặc định 5. Trang không nêu role RBAC cần có | `keda.sh/docs/latest/scalers/azure-service-bus` |
| Mỗi app được cấp một FQDN mặc định; HTTPS kết thúc ở ingress (TLS 1.2/1.3); HTTP tự chuyển sang HTTPS; request hết hạn sau 240 giây | `…/container-apps/ingress-overview` |
| Kiểu mạng của environment không đổi được sau khi tạo | `…/container-apps/networking` |
| Phí quản lý chỉ áp dụng khi có profile Dedicated, hoặc khi dùng private endpoint / planned maintenance của environment | `…/container-apps/billing` |
| Kéo image từ registry bằng managed identity cần role AcrPull | `…/container-apps/managed-identity-image-pull` |
| Service Bus Basic: "queues only", message tối đa 256 KB; không có topic, session, transaction, duplicate detection | `…/service-bus-messaging/service-bus-premium-messaging`, trang giá Service Bus |
| External tenant: authority dạng `https://<tên tenant>.ciamlogin.com/`; redirect URI kiểu Single-page application; app phải gắn với một user flow | `…/entra/external-id/customers/tutorial-single-page-app-vanillajs-prepare-app` |
| `email` là optional claim với tài khoản trong tenant (phải bật trong app registration); không có claim `email_verified`; app role nằm trong claim `roles` | `…/entra/identity-platform/id-token-claims-reference`, `…/optional-claims-reference`, `…/external-id/customers/how-to-use-app-roles-customers` |
| External ID miễn phí cho 50.000 người dùng hoạt động hằng tháng đầu tiên | `…/entra/external-id/customers/faq-customers` |
| SAS: quyền Create = "Write a new blob…", quyền Write = "Create or write content…"; trang không nói Create có ghi đè được blob đã có hay không | `…/rest/api/storageservices/create-service-sas` |
| Lưu trữ của PostgreSQL flexible server chỉ tăng được, không giảm được; subnet đã uỷ quyền không chứa được loại tài nguyên khác | `…/postgresql/flexible-server/concepts-storage`, `…/concepts-networking-private` |

Hệ quả cho cấu hình: phải bật optional claim `email` cho ID token trong app registration (hoặc đặt `OIDC_EMAIL_CLAIM=preferred_username`); vì token của Entra không có `email_verified`, việc e-mail đã được xác minh hoàn toàn dựa vào user flow của tenant.

## Chưa đối chiếu được (phải kiểm tra trước khi viết code hoặc `plan`)

- Bậc Basic của Service Bus có dead-letter queue, peek-lock và xác thực Entra hay không (tài liệu chỉ ghi "queues only").
- Luật scale Service Bus bằng managed identity chạy được cho **job** hay không (Terraform có trường này; lệnh CLI tương ứng còn ghi "Preview"), và identity đó cần role nào. Nếu không chạy được thì phải dùng connection string trong Key Vault và ghi là lệch.
- Chứng chỉ của hostname mặc định có được trình duyệt tin ngay không; giới hạn kích thước request của ingress (file video không đi qua ingress, chỉ JSON).
- Giá trị `iss` thật trong ID token của external tenant và địa chỉ OpenID configuration (lấy từ chính tenant khi đã tạo).
- Request của trình duyệt kèm SAS có đi qua luật CORS như request thường không.
- SAS chỉ có quyền `c` (create) có thật sự không ghi đè được blob đã tồn tại không (mã nguồn dựa vào điều này để một URL tải lên chỉ dùng được một lần).
- Managed identity cần đúng những role nào để SAS do nó ký có quyền tạo/đọc blob và để xoá được từng phiên bản.
- Flexible server có dừng tạm được để tiết kiệm không và dừng được bao lâu; có đổi được private access sang public sau khi tạo không.
- Database PostgreSQL có thật sự được tính vào phần miễn phí của Azure for Students không (xem mục Chi phí).

## Việc chưa quyết (cần thông tin từ chủ dự án)

| Việc | Vì sao cần | Chốt ở |
| --- | --- | --- |
| ~~Loại tài khoản Azure~~ | **Đã đọc từ tài khoản 2026-11-21:** một subscription tên "Azure for Students", trạng thái Enabled; người đăng nhập có role Owner. Số dư credit chưa xem (không có lệnh chỉ đọc đơn giản cho việc này; xem trong cổng Azure) | — |
| ~~Region~~ | **Chọn 2026-11-21: `malaysiawest`** (đề xuất dùng cho `plan`; chủ dự án xác nhận trước `apply`). Policy "Allowed resource deployment regions" của subscription chỉ cho phép `malaysiawest`, `indonesiacentral`, `japaneast`, `japanwest`, `centralindia`; Singapore (`southeastasia`) không được phép. Cả năm region đều có mọi loại tài nguyên của thiết kế; `malaysiawest` gần Việt Nam nhất, có PostgreSQL 18 và SKU B1ms, giá PostgreSQL thấp hơn Japan East. Đánh đổi: region mới, có thể thiếu tính năng chỉ lộ ra lúc `apply`; phương án lùi là `japaneast`. Độ trễ từ Việt Nam chưa đo | — |
| ~~Quyền tạo external tenant và app registration~~ | **Đã đọc 2026-11-21:** chính sách của tenant cho người dùng tạo tenant và tạo app (`allowedToCreateTenants`, `allowedToCreateApps` đều `true`). Việc tạo external tenant thật thì chưa thử | Thử ở Phase 09 || ~~Tên miền~~ | **Đã chốt 2026-11-21: chuyển hẳn `video.uploadmdm.id.vn` sang Azure** (chủ dự án chọn; đề xuất là dùng hostname mặc định trước). Bản Azure được kiểm thử trên hostname mặc định, rồi mới đổi DNS; từ lúc đổi, bản VPS mất địa chỉ công khai và không có giai đoạn chạy song song trên tên này. Trình tự: `infra/azure/README.md` | — |
| ~~Cách cấp quyền cho Terraform và GitHub Actions~~ | **Đã chốt 2026-11-21:** Terraform dùng phiên `az login` của chủ dự án (Azure CLI bản ZIP trong `.tools\azcli`), subscription qua biến môi trường `ARM_SUBSCRIPTION_ID`. GitHub Actions sẽ dùng federated credential (OIDC), thêm ở Phase 12 | — |
| Chứng chỉ ACM còn lại trên AWS | Miễn phí nhưng là tài nguyên thật; xoá cần chủ dự án đăng nhập AWS | Khi chủ dự án muốn |
| Ngân sách và thời gian giữ tài nguyên | PostgreSQL và registry tính tiền theo giờ/ngày kể cả khi không dùng | Trước Phase 09 |

## Tài khoản Azure đã kiểm tra (2026-11-21, chỉ đọc, sau khi chủ dự án tự chạy `az login`)

- Một subscription "Azure for Students", Enabled; role của người đăng nhập trên subscription: Owner. Chưa có resource group nào.
- Policy "Allowed resource deployment regions": `indonesiacentral`, `centralindia`, `japanwest`, `malaysiawest`, `japaneast`.
- Các resource provider cần dùng (`Microsoft.App`, `DBforPostgreSQL`, `ServiceBus`, `Storage`, `KeyVault`, `ContainerRegistry`, `OperationalInsights`, `Network`, `ManagedIdentity`) đều **chưa đăng ký**; phải đăng ký một lần trước `apply` (lệnh ở `infra/azure/README.md`). Terraform được cấu hình để không tự đăng ký.
- PostgreSQL flexible server ở `malaysiawest`, `indonesiacentral`, `japaneast`: có SKU `Standard_B1ms` và các bản 11–18.
- Số subscription, số tenant, tên và e-mail của người dùng cố ý không ghi vào repo.

## Chi phí (ước tính sơ bộ, chưa phải hoá đơn)

Đơn giá bán lẻ lấy từ Azure Retail Prices API (`prices.azure.com/api/retail/prices`) ngày 2026-11-21, region `malaysiawest`, USD, chưa thuế. Một tháng tính 730 giờ.

| Hạng mục | Giả định | Đơn giá | USD/tháng |
| --- | --- | --- | --- |
| PostgreSQL flexible server B1ms | chạy liên tục | 0,0234 / giờ | 17,08 |
| Lưu trữ PostgreSQL | 32 GiB | 0,1242 / GiB-tháng | 3,97 |
| Container Registry Basic | 1 registry | 0,1666 / ngày | 5,07 |
| Private DNS zone | 1 zone | 0,50 / tháng | 0,50 |
| Load balancer Standard của environment | Azure tự tạo trong resource group `ME_…` vì environment nằm trong VNet riêng; đang có 2 luật | 0,025 / giờ (giá "Global" trong bảng giá) | 18,25 |
| Địa chỉ IP public Standard của environment | 1 địa chỉ | 0,005 / giờ | 3,65 |
| **Cộng phần cố định** | | | **≈ 49** (khoảng 1,6 USD/ngày) |
| Container Apps `api` | 0,5 vCPU, 1 GiB, co về 0 khi nghỉ | 0,000028 / vCPU-giây; 0,000004 / GiB-giây | theo thời gian có người dùng |
| Job `transcode` | 1 vCPU, 2 GiB, giả định 60 giây mỗi clip | như trên | ≈ 0,0022 mỗi clip |
| Job `maintenance` | 0,25 vCPU, 0,5 GiB, 5 phút một lần, giả định 15 giây mỗi lần | như trên | ≈ 1,2 |
| Service Bus Basic | vài nghìn thao tác | 0,05 / triệu thao tác | ≈ 0 |
| Blob Storage Hot LRS | vài GB | 0,018 / GB-tháng | ≈ 0,1 |
| Log Analytics | dưới 5 GB/tháng | 5 GB đầu miễn phí (giá sau đó ở region này chưa tra) | 0 |
| Lưu lượng ra Internet | dưới 100 GB/tháng | 100 GB đầu miễn phí (giá sau đó ở region này chưa tra) | 0 |

**Phần miễn phí của Azure for Students.** Trang `azure.microsoft.com/free/students` liệt kê cho PostgreSQL: 12 tháng, mỗi tháng 750 giờ flexible server Burstable B1MS, 32 GB lưu trữ và 32 GB sao lưu. Thiết kế dùng đúng cỡ đó (một máy chủ B1ms chạy cả tháng là tối đa 744 giờ, 32 GiB). Nếu ưu đãi áp dụng cho subscription này thì hai dòng PostgreSQL bằng 0 trong 12 tháng và phần cố định còn khoảng 27,5 USD/tháng. Load balancer và địa chỉ IP là hai khoản chỉ thấy được sau `apply` ngày 2026-11-21 (bản ước tính trước đó thiếu chúng); chúng được suy ra từ tài nguyên có thật và bảng giá, chưa đối chiếu với hoá đơn. **Chưa xác nhận** ưu đãi được áp dụng tự động hay cần thao tác nào, và có áp dụng ở `malaysiawest` không; phải xem Cost Management sau vài ngày đầu. Ghi chú riêng: ưu đãi "Apply offer"/bậc Basic khoảng 5 USD/tháng mà cổng Azure quảng cáo là của **Azure SQL Database** (lõi SQL Server), ứng dụng này không dùng được vì mã nguồn viết cho PostgreSQL.

Ba dòng Container Apps chưa trừ phần miễn phí hằng tháng (180.000 vCPU-giây, 360.000 GiB-giây, 2 triệu request); với tải demo thì nhiều khả năng nằm trọn trong phần miễn phí, nhưng điều đó **chưa đo**. Nếu giữ `api` luôn có 1 replica để tránh chờ khởi động: thêm khoảng 15,8 USD/tháng theo giá idle (trước phần miễn phí).

Chưa tính và chưa biết: sao lưu PostgreSQL ngoài phần kèm theo, Key Vault (0,03 USD / 10.000 thao tác ở Singapore; chưa tra ở region này), luật alert, thuế. Bảng giá của `malaysiawest` có ba meter cấp environment của Container Apps, mỗi cái 0,117 USD/giờ: "Environment Management Hour", "Environment Planned Maintenance Hour", "Environment Private Endpoint". Tài liệu billing nói phí quản lý chỉ áp dụng khi có profile Dedicated hoặc khi dùng private endpoint / planned maintenance của environment; thiết kế này không dùng thứ nào trong đó. Vẫn phải xem Cost Management sau ngày đầu, vì nếu một meter chạy liên tục thì đó là khoảng 85 USD/tháng. Thời lượng 60 giây mỗi clip và 15 giây mỗi lần `maintenance` là giả định, sẽ thay bằng số đo ở Phase 11. Credit của Azure for Students là 100 USD (theo tài liệu; số dư thật chưa xem): hết credit thì subscription và mọi dịch vụ bị vô hiệu hoá.
## Miền lỗi

Một region. PostgreSQL một máy chủ, không dự phòng theo zone: mất máy chủ là mất dịch vụ cho tới khi khôi phục từ bản sao lưu. Replica của `api` chết thì Container Apps dựng lại. Lần chạy job chết giữa chừng thì lock của message hết hạn, message được giao lại và sinh lần chạy mới; lease hết hạn được `reconcile` thu hồi, job thử lại tối đa 3 lần rồi FAILED. Service Bus, Blob Storage và Entra là dịch vụ theo region do Azure vận hành.

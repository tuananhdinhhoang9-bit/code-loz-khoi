# Kiến trúc trên Azure (mục tiêu triển khai từ 2026-11-21)

**Trạng thái: CHỈ LÀ THIẾT KẾ (2026-11-21).** Chưa có tài khoản Azure nào được kiểm tra, chưa có tài nguyên Azure nào, chưa có dòng mã Azure nào trong `app/`, chưa có `infra/azure/`. Mọi mục dưới đây là kế hoạch cho đến khi `docs/PROGRESS.md` ghi PASS kèm bằng chứng thật. Quyết định: ADR-024 trong `docs/DECISIONS.md`.

Lý do đổi: chủ dự án quyết định bỏ AWS và chỉ làm Azure (2026-11-21). Đề bài (`references/…pdf`, trang 1–2) cho chọn một trong AWS / Azure / GCP. Dòng Azure trong bảng gợi ý của đề: *App Service API; Azure Database for PostgreSQL; Blob Storage; Service Bus; Functions or Container Apps workers. Use bounded Container Apps Jobs for conversion.* Về danh tính: *Use … Entra External ID on Azure … or justify another OIDC provider. … put secrets in … Key Vault.*

Phần AWS (ADR-021/022/023, `docs/AWS_ARCHITECTURE.md`, `infra/aws/`, `deploy/aws/`, các prompt AWS) là tài liệu lưu trữ; nhánh `aws` trên GitHub giữ nguyên bản AWS cuối cùng. Trên AWS chỉ từng tạo một chứng chỉ ACM (miễn phí), chưa xoá. Bản VPS vẫn chạy nguyên trạng và không bị sửa trong lúc chuyển.

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
| Waitress sau Caddy (`app/serve.py`) | Container `api` trên Container Apps, ingress ngoài | Dockerfile (dùng lại từ `deploy/aws/Dockerfile`); tin `X-Forwarded-*` từ ingress (`TRUSTED_PROXY` đã có); log ra stdout |
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

**Gỡ bỏ ở Phase 07, khi phần Azure tương ứng đã qua test:** `app/storage_s3.py`, `app/queue_sqs.py`, nhánh Cognito và form POST của S3 trong `portal.js`, `boto3` trong `requirements.txt`, `tests/test_aws_adapters.py`. Cho tới lúc đó mã AWS vẫn nằm trong `app/` và không được gọi khi cấu hình là `local`/`postgres`.

## Các lựa chọn thiết kế và đánh đổi

1. **API chạy trên Container Apps, không phải App Service** (đề gợi ý "App Service API"). Lý do: API và job chuyển mã dùng chung một nền tảng, một registry, một VNet và một cách cấp quyền; app co về 0 replica khi không ai dùng nên không tốn tiền lúc nghỉ; chứng chỉ cho tên miền riêng miễn phí. Đánh đổi: lệch chữ với gợi ý của đề; request đầu tiên sau khi nghỉ phải chờ container khởi động (chưa đo). Nếu thầy yêu cầu đúng App Service thì image `api` chạy được trên App Service for Containers mà không đổi code.
2. **Chuyển mã bằng Container Apps Job chạy theo sự kiện**, đúng câu "Use bounded Container Apps Jobs for conversion" của đề. KEDA đếm message trong queue; có message thì nền tảng khởi động một lần chạy, lần chạy đó xử lý một job rồi thoát. Giới hạn: tối đa 1 lần chạy đồng thời, `replica timeout` lớn hơn `TRANSCODE_TIMEOUT_SECONDS`, `replica retry limit = 0` (thử lại do lease trong DB quyết định, tối đa 3 lần, không để nền tảng nhân thêm). Đánh đổi: phải thêm chế độ "một vòng rồi thoát" cho worker và một job theo lịch; mỗi clip chịu thêm thời gian khởi động container và chu kỳ thăm dò của KEDA (mặc định 30 giây). Thiết kế AWS cũ dùng một worker chạy liên tục; trên Azure cách đó vừa lệch đề vừa tốn tiền cả khi không có video.
3. **Ai đẩy outbox sang queue.** API gọi relay ngay sau khi giao dịch `complete` đã commit (lỗi thì chỉ ghi log). Job `maintenance` chạy theo lịch (dự kiến 5 phút một lần) làm lại việc đó cho các event còn sót, thu hồi lease hết hạn và dọn dẹp. Như vậy không có tiến trình nào chạy liên tục. Giao dịch nghiệp vụ và event vẫn commit cùng nhau; relay luôn xảy ra sau commit.
4. **Upload bằng user delegation SAS**: trình duyệt `PUT` thẳng lên Blob Storage với header `x-ms-blob-type: BlockBlob`. SAS được ký bằng managed identity của `api`, không dùng account key; chỉ có quyền tạo đúng một blob, sống 120 giây. **SAS không có tham số giới hạn kích thước** (khác presigned POST của S3), nên giới hạn được kiểm tra ở trình duyệt trước khi gửi và kiểm tra lại có thẩm quyền ở bước `complete` (đọc kích thước thật của blob; quá giới hạn thì xoá blob và từ chối). Rủi ro còn lại: người đã đăng nhập có thể đẩy một blob lớn tồn tại trong vài giây trước khi bị xoá; một lần `Put Blob` tối đa 5.000 MiB.
5. **Blob versioning bật**: mỗi lần ghi trả về `x-ms-version-id`; đó là `source_generation`. URL phát video và thumbnail là SAS chỉ đọc trỏ vào đúng phiên bản. Xoá video phải xoá mọi phiên bản (xoá blob hiện tại không xoá phiên bản cũ). Trình duyệt gọi thẳng Blob Storage nên dịch vụ Blob cần luật CORS cho đúng origin của trang, và CSP của trang phải cho host của storage account ở `connect-src`, `media-src`, `img-src`.
6. **Service Bus bậc Basic**, một queue. Lock của message tối đa 5 phút nên heartbeat của worker gia hạn lock trong lúc job chạy. Quá `MaxDeliveryCount` (mặc định 10) thì message tự sang dead-letter queue; message hỏng được worker chủ động đưa sang đó kèm lý do. Xác thực bằng managed identity (role Data Sender / Data Receiver), tắt xác thực bằng khoá.
7. **Database chỉ có đường riêng.** PostgreSQL flexible server tạo với private access: một subnet uỷ quyền cho `Microsoft.DBforPostgreSQL/flexibleServers` và một private DNS zone. Môi trường Container Apps nằm trong cùng VNet (subnet riêng, tối thiểu `/27`, uỷ quyền cho `Microsoft.App/environments`). Database không có địa chỉ public; chỉ `api` và hai job tới được. Đánh đổi: không nối được DB từ máy cá nhân; `init-db` và seed phải chạy bằng job trong VNet.
8. **Đăng nhập bằng Microsoft Entra External ID** (đề nêu đích danh). Trang chuyển hướng sang trang đăng nhập của Entra theo authorization code + PKCE rồi nhận ID token; API xác minh chữ ký, issuer và audience bằng bộ xác minh OIDC đã có. Không dùng native authentication: tài liệu ghi rõ SPA dùng native authentication cần proxy hoặc luật CORS ở biên. Đánh đổi so với hiện tại: người dùng rời trang để đăng nhập; phải tạo "external tenant", việc này cần quyền Tenant Creator trên subscription. **Nếu tài khoản sinh viên không tạo được external tenant**, phương án lùi là giữ tài khoản nội bộ (`AUTH_PROVIDER=local`) và ghi rõ đây là lệch đề cần thầy đồng ý, không lặng lẽ thay thế.
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

## Chưa đối chiếu được (phải kiểm tra trước khi viết code hoặc `plan`)

- Bậc Basic của Service Bus có đủ queue, peek-lock, dead-letter và xác thực Entra hay không (các trang đã đọc không ghi rõ theo bậc).
- Luật scale Service Bus bằng managed identity có dùng được cho **job** theo sự kiện không; nếu không thì phải dùng connection string trong Key Vault và ghi là lệch.
- Lệnh dừng một lần chạy job giữa chừng (dự kiến `az containerapp job stop`); cần cho diễn tập sự cố.
- App có ingress ngoài có sẵn hostname `*.azurecontainerapps.io` kèm chứng chỉ hợp lệ hay không; giới hạn thời gian và kích thước request của ingress.
- Issuer và địa chỉ OpenID configuration của external tenant; claim e-mail trong ID token của tài khoản e-mail + mật khẩu; tên claim của app role.
- Request của trình duyệt kèm SAS có đi qua luật CORS như request thường không.
- Số người dùng miễn phí của External ID (trang giá chỉ ghi "có bậc miễn phí").
- Flexible server có dừng tạm được để tiết kiệm không và dừng được bao lâu; có đổi được private access sang public sau khi tạo không.
- Dung lượng lưu trữ tối thiểu của flexible server (bảng chi phí dưới đây giả định 32 GiB).

## Việc chưa quyết (cần thông tin từ chủ dự án)

| Việc | Vì sao cần | Chốt ở |
| --- | --- | --- |
| Loại tài khoản Azure | Azure for Students, dùng thử hay trả tiền quyết định credit, dịch vụ được dùng và quyền tạo external tenant | Phase 08 |
| Region | Dự kiến `southeastasia` (Singapore) vì gần Việt Nam; subscription sinh viên có thể bị giới hạn region | Phase 08 |
| Quyền tạo external tenant và app registration | Thiếu quyền thì phải dùng phương án lùi ở mục 8 | Phase 08 |
| Tên miền | Chứng chỉ managed cần CNAME trỏ thẳng về app, nên **không thử trước được trên `video.uploadmdm.id.vn` khi tên đó còn trỏ về VPS**. Lựa chọn: dùng hostname mặc định của Azure, hoặc một tên miền con mới, hoặc chuyển hẳn tên cũ (lúc đó bản VPS mất địa chỉ) | Trước Phase 09 |
| Cách cấp quyền cho Terraform và GitHub Actions | Máy này chưa có Azure CLI; không dùng client secret dài hạn | Phase 08 |
| Chứng chỉ ACM còn lại trên AWS | Miễn phí nhưng là tài nguyên thật; xoá cần chủ dự án đăng nhập AWS | Khi chủ dự án muốn |
| Ngân sách và thời gian giữ tài nguyên | PostgreSQL và registry tính tiền theo giờ/ngày kể cả khi không dùng | Trước Phase 09 |

## Chi phí (ước tính sơ bộ, chưa phải hoá đơn)

Đơn giá bán lẻ lấy từ Azure Retail Prices API (`prices.azure.com/api/retail/prices`) ngày 2026-11-21, region `southeastasia`, USD, chưa thuế. Một tháng tính 730 giờ.

| Hạng mục | Giả định | Đơn giá | USD/tháng |
| --- | --- | --- | --- |
| PostgreSQL flexible server B1ms | chạy liên tục | 0,026 / giờ | 18,98 |
| Lưu trữ PostgreSQL | 32 GiB | 0,138 / GiB-tháng | 4,42 |
| Container Registry Basic | 1 registry | 0,1666 / ngày | 5,07 |
| Private DNS zone | 1 zone | 0,50 / tháng | 0,50 |
| **Cộng phần cố định** | | | **≈ 29** |
| Container Apps `api` | 0,5 vCPU, 1 GiB, co về 0 khi nghỉ | 0,000034 / vCPU-giây; 0,000004 / GiB-giây | theo thời gian có người dùng |
| Job `transcode` | 1 vCPU, 2 GiB, giả định 60 giây mỗi clip | như trên | ≈ 0,0025 mỗi clip |
| Job `maintenance` | 0,25 vCPU, 0,5 GiB, 5 phút một lần, giả định 15 giây mỗi lần | như trên | ≈ 1,4 |
| Service Bus Basic | vài nghìn thao tác | 0,05 / triệu thao tác | ≈ 0 |
| Blob Storage Hot LRS | vài GB | 0,02 / GB-tháng | ≈ 0,1 |
| Log Analytics | dưới 5 GB/tháng | 5 GB đầu miễn phí, sau đó 2,99 / GB | 0 |
| Lưu lượng ra Internet | dưới 100 GB/tháng | 100 GB đầu miễn phí, sau đó 0,12 / GB | 0 |

Ba dòng Container Apps chưa trừ phần miễn phí hằng tháng (180.000 vCPU-giây, 360.000 GiB-giây, 2 triệu request); với tải demo thì nhiều khả năng nằm trọn trong phần miễn phí, nhưng điều đó **chưa đo**. Nếu giữ `api` luôn có 1 replica để tránh chờ khởi động: thêm khoảng 15,8 USD/tháng theo giá idle (trước phần miễn phí).

Chưa tính và chưa biết: sao lưu PostgreSQL, Key Vault (0,03 USD / 10.000 thao tác), luật alert, thuế. Bảng giá có một meter "Container Apps Environment Management Hour" 0,10 USD/giờ mà **chưa rõ áp dụng khi nào**; phải làm rõ trước khi `apply`, vì nếu tính liên tục thì đó là khoảng 73 USD/tháng. Thời lượng 60 giây mỗi clip và 15 giây mỗi lần `maintenance` là giả định, sẽ thay bằng số đo ở Phase 11. Với 100 USD credit của Azure for Students (chưa xác nhận tài khoản thuộc loại này), phần cố định 29 USD/tháng đủ cho khoảng ba tháng chạy liên tục.

## Miền lỗi

Một region. PostgreSQL một máy chủ, không dự phòng theo zone: mất máy chủ là mất dịch vụ cho tới khi khôi phục từ bản sao lưu. Replica của `api` chết thì Container Apps dựng lại. Lần chạy job chết giữa chừng thì lock của message hết hạn, message được giao lại và sinh lần chạy mới; lease hết hạn được `reconcile` thu hồi, job thử lại tối đa 3 lần rồi FAILED. Service Bus, Blob Storage và Entra là dịch vụ theo region do Azure vận hành.

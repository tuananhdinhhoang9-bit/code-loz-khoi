# Terraform cho Azure (Phase 08)

**Trạng thái (2026-11-21): ĐÃ `apply` toàn bộ trên subscription Azure for Students của chủ dự án, region `malaysiawest`: Terraform quản lý 48 tài nguyên (nền, app `api`, hai job, identity và quyền cho GitHub Actions, workbook và cảnh báo). Trang chạy tại hostname mặc định của Azure Container Apps; đăng nhập, tải lên, chuyển mã, phát lại, diễn tập lỗi, load test, deploy và rollback qua GitHub Actions đều đã chạy thật (`docs/EVIDENCE.md`). Đăng nhập đang dùng tài khoản nội bộ (`auth_provider = "local"`), chưa phải Entra External ID. Tên miền riêng chưa được chuyển sang Azure.**

## Tạo ra những gì (40 khối `resource`)

| File | Tài nguyên |
| --- | --- |
| `versions.tf` | Provider, hậu tố ngẫu nhiên cho các tên phải duy nhất toàn Azure, resource group |
| `network.tf` | VNet, subnet `apps` (Container Apps) và `db` (PostgreSQL), private DNS zone cho database |
| `data.tf` | PostgreSQL flexible server không có địa chỉ public; storage account bật versioning, tắt truy cập công khai và account key, CORS; container `media`; luật tự xoá phiên bản blob cũ; Service Bus Basic + queue `transcode-jobs`; Key Vault giữ mật khẩu DB |
| `identity.tf` | Hai managed identity (`api`, `worker`) và các role assignment của chúng |
| `apps.tf` | Container Registry, Log Analytics, Container Apps environment trong VNet; app `api`; job `transcode` (chạy khi có message) và job `maintenance` (theo lịch) |
| `github.tf` | Identity `deploy` cho GitHub Actions: federated credential của nhánh `main`, `AcrPush` trên registry, và từ Phase 12 các quyền đổi image của app và hai job (chỉ tạo khi đặt `github_repository`) |

Số tài nguyên thật: 32 ở bước nền, thêm 3 của `github.tf` (đã apply), thêm 3 nữa (app và hai job) khi `deploy_apps = true`.

Không nằm trong Terraform này, phải làm tay và ghi lại: external tenant của Microsoft Entra External ID và app registration (thuộc tenant khác, cần quyền Tenant Creator); bản ghi DNS của tên miền (DNS nằm ngoài Azure); gắn tên miền riêng và chứng chỉ vào app (làm lúc chuyển DNS); quyền cho GitHub Actions (Phase 12); dashboard và alert (Phase 11).

## Chuẩn bị

Mọi lệnh chạy từ thư mục gốc của repo, trong PowerShell. Azure CLI nằm ở `.tools\azcli` (không cài vào hệ thống).

```powershell
# 1. Chủ dự án tự đăng nhập (không ai khác nhập mật khẩu thay). Lệnh in ra một mã và một địa chỉ để mở trên trình duyệt.
& .\.tools\azcli\bin\az.cmd login --use-device-code

# 2. Chọn subscription cho Terraform bằng biến môi trường, không ghi ID vào file nào.
$env:ARM_SUBSCRIPTION_ID = & .\.tools\azcli\bin\az.cmd account show --query id -o tsv

# 3. Kiểm tra chỉ đọc trước khi plan: tên subscription, region được phép, resource provider đã đăng ký.
#    Câu --query có dấu ngoặc phải gọi thẳng python của Azure CLI: az.cmd đi qua cmd.exe và làm hỏng dấu ngoặc.
function Invoke-Az { & .\.tools\azcli\python.exe -IBm azure.cli @args }
Invoke-Az account show --query name -o tsv
Invoke-Az policy assignment list --query '[].{name:displayName, locations:parameters.listOfAllowedLocations.value}' -o json
Invoke-Az provider list --query '[].{ns:namespace, state:registrationState}' -o table

# Terraform gọi lệnh `az` qua PATH:
$env:PATH = "$PWD\.tools\azcli\bin;" + $env:PATH
```

Kết quả đọc ngày 2026-11-21: subscription "Azure for Students"; region được phép là `malaysiawest`, `indonesiacentral`, `japaneast`, `japanwest`, `centralindia` (Singapore không được phép); các resource provider cần dùng đều chưa đăng ký. `location` mặc định là `malaysiawest`; phương án lùi là `japaneast`.

Trước lần `apply` đầu tiên phải đăng ký resource provider một lần (miễn phí, nhưng là thay đổi trên subscription nên chỉ chạy khi chủ dự án đồng ý):

```powershell
foreach ($ns in "Microsoft.App","Microsoft.DBforPostgreSQL","Microsoft.ServiceBus","Microsoft.Storage","Microsoft.KeyVault","Microsoft.ContainerRegistry","Microsoft.OperationalInsights","Microsoft.Network","Microsoft.ManagedIdentity") { & .\.tools\azcli\bin\az.cmd provider register --namespace $ns }
```

```powershell
# 4. Plan (không tạo gì, không tốn tiền).
Copy-Item infra\azure\terraform.tfvars.example infra\azure\terraform.tfvars   # rồi sửa giá trị
& .\.tools\terraform\terraform.exe -chdir=infra/azure plan -out=terraform.tfplan
```

## Triển khai theo hai bước (Phase 09, chỉ khi chủ dự án đồng ý từng bước tốn tiền)

App và job không tạo được khi image chưa có trong registry, nên:

1. `deploy_apps = false` → `apply`: tạo nền (mạng, database, storage, queue, vault, registry, environment). Từ lúc này PostgreSQL và registry tính tiền theo giờ/ngày.
2. Build và đẩy hai image với cùng một tag bằng **GitHub Actions** (job `images` trong `.github/workflows/ci.yml`, chạy trên nhánh `main`, tag là commit SHA). Đây là cách duy nhất còn lại, đã thử ngày 2026-11-21:
   - `az acr build`: region `malaysiawest` không có ACR Tasks; ở `japaneast` thì Azure trả `TasksOperationsNotAllowed` cho subscription sinh viên.
   - Máy ảo Linux dùng tạm để chạy Docker: mọi cỡ nhỏ đã thử đều bị từ chối (`SkuNotAvailable` hoặc `QuotaExceeded`) ở `malaysiawest`, `japaneast`, `centralindia`.
   - GitHub Actions đăng nhập Azure bằng OIDC qua identity `videoportal-deploy` (chỉ nhận token của nhánh `main`; danh sách quyền ở mục CI/CD bên dưới). Chủ dự án thêm bốn secret vào kho GitHub: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_REGISTRY`; giá trị nằm trong file `.env.github` ở thư mục gốc (không được commit). **Job này chưa chạy thành công lần nào.**
3. Điền `image_tag`, đặt `deploy_apps = true` → `apply`: tạo app `api` và hai job.
4. Tạo bảng: chạy một lần job `maintenance` với lệnh ghi đè `flask --app app.main init-db` (`az containerapp job start`; đã chạy thành công ngày 2026-11-21).
5. Kiểm thử trên địa chỉ mặc định (`default_url`) trước khi đụng tới DNS.

## Tên miền riêng: `azure.uploadmdm.id.vn` (đã gắn 2026-11-22)

Chủ dự án đổi quyết định ngày 2026-11-21 (ADR-030): bản Azure dùng tên mới `azure.uploadmdm.id.vn`, bản VPS giữ `video.uploadmdm.id.vn` và không bị đụng tới, để VPS làm bản dự phòng. Hostname mặc định `*.azurecontainerapps.io` vẫn dùng được song song.

1. `domain_name = "azure.uploadmdm.id.vn"` trong `terraform.tfvars`, rồi `apply`: chỉ đổi origin trong CORS của Blob Storage (và danh sách redirect URI cho OIDC).
2. Chủ dự án thêm hai bản ghi DNS: CNAME `azure` trỏ về hostname mặc định của app, và TXT `asuid.azure` chứa mã xác minh của app (`az containerapp show --query properties.customDomainVerificationId`).
3. Gắn tên miền và xin chứng chỉ miễn phí do Azure quản lý (việc này làm bằng CLI, không nằm trong Terraform; `terraform plan` sau đó vẫn báo `No changes`):

```powershell
az containerapp hostname add --hostname azure.uploadmdm.id.vn --name videoportal-api --resource-group videoportal-rg
az containerapp hostname bind --hostname azure.uploadmdm.id.vn --name videoportal-api --resource-group videoportal-rg --environment videoportal-env --validation-method CNAME
```

Gỡ ra: `az containerapp hostname delete --hostname azure.uploadmdm.id.vn --name videoportal-api --resource-group videoportal-rg`, xoá hai bản ghi DNS. `terraform destroy` xoá app nên cũng xoá luôn tên miền gắn và chứng chỉ.

## CI/CD và rollback (Phase 12, ADR-029)

Sau lần `apply` đầu tiên, image đang chạy do GitHub Actions quyết định, không phải `image_tag` trong `terraform.tfvars` (Terraform bỏ qua thay đổi của thuộc tính `image`).

- Mỗi lần push lên `main`: workflow `ci` chạy test, build hai image theo SHA của commit, rồi `deploy/azure/deploy.sh` đổi image của app `api` và hai job, chờ revision mới khoẻ. Không khoẻ sau 5 phút thì script tự đưa image cũ trở lại và báo lỗi.
- Quay lại bản cũ: GitHub > Actions > `rollback` > Run workflow, nhập SHA đầy đủ của commit cần quay về. Không test, không build.
- Xem image đang chạy:

```powershell
az containerapp show --name videoportal-api --resource-group videoportal-rg --query "properties.template.containers[0].image" -o tsv
```

Identity `deploy` chỉ có: `AcrPush` trên registry, `Container Apps Contributor` trên app `api` và environment, `Container Apps Jobs Contributor` trên hai job, `Managed Identity Operator` trên hai identity `api` và `worker`.
## Chi phí và dọn dẹp

Giá niêm yết khi không có video nào: khoảng 67,8 USD/tháng, tức khoảng 2,26 USD/ngày, ở `malaysiawest`; trong đó khoảng 50 USD là phần cố định (PostgreSQL B1ms + 32 GiB, registry Basic, private DNS zone, cảnh báo, cộng load balancer và địa chỉ IP mà Azure tự tạo cho environment trong VNet), còn lại là bản `api` luôn bật và job bảo trì. Bảng đầy đủ, ngày đọc giá và số thật từ Cost Management: `docs/AZURE_MONITORING_COST.md`. Hướng dẫn dọn dẹp từng bước: `docs/CLEANUP.md`.

Dọn dẹp sau demo: `terraform destroy` xoá mọi thứ ở đây, **kể cả database và toàn bộ video**. Key Vault đã xoá vẫn được Azure giữ 7 ngày trừ khi đặt `allow_destroy_data = true` trước khi destroy. Sau đó kiểm tra resource group đã trống và xem trang Cost Management.

## Chưa kiểm chứng (phải xem lại ở lần `plan`/`apply` đầu tiên)

- Subscription sinh viên có thật sự cho tạo từng tài nguyên này ở `malaysiawest` không. Đã đọc được: region nằm trong danh sách cho phép, mọi loại tài nguyên có ở region, PostgreSQL có B1ms và bản 18. Hạn mức và giới hạn riêng của gói sinh viên thì chưa biết.
- Role của identity: `Storage Blob Data Owner` ở mức container có đủ để SAS do `api` ký hoạt động và để xoá phiên bản; `Azure Service Bus Data Owner` ở mức queue có đúng là thứ KEDA cần để đếm message (tài liệu KEDA không nêu role).
- Luật scale bằng managed identity cho **job** (Terraform có trường `identity_id`; lệnh CLI tương ứng còn ghi "Preview").
- Bậc Basic của Service Bus có dead-letter queue và xác thực Entra (tài liệu đã đọc chỉ ghi "queues only").
- Meter "Environment Management Hour" 0,10 USD/giờ trong bảng giá: tài liệu billing nói phí quản lý chỉ áp dụng khi có profile Dedicated hoặc dùng private endpoint/planned maintenance của environment; thiết kế này không dùng thứ nào trong đó, nhưng phải xem Cost Management sau ngày đầu.
- Kết nối tới PostgreSQL dùng TLS do máy chủ yêu cầu nhưng ứng dụng không kiểm tra chứng chỉ của máy chủ (`sslmode` mặc định của libpq); đường đi nằm trọn trong VNet.

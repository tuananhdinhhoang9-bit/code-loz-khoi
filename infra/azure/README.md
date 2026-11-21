# Terraform cho Azure (Phase 08)

**Trạng thái (2026-11-21): đã `fmt`, `init`, `validate` và `plan` trên subscription Azure for Students của chủ dự án (azurerm 4.81.0, random 3.9.1, Terraform 1.17.2): `Plan: 32 to add` với `deploy_apps = false`, `Plan: 35 to add` với `deploy_apps = true`. CHƯA `apply`: chưa có tài nguyên nào. `plan` không gọi tới từng dịch vụ, nên hạn mức và giới hạn của gói sinh viên chỉ lộ ra khi `apply`.** Thiết kế và lý do: `docs/AZURE_ARCHITECTURE.md`, ADR-024 đến ADR-026.

## Tạo ra những gì (32 khối `resource`)

| File | Tài nguyên |
| --- | --- |
| `versions.tf` | Provider, hậu tố ngẫu nhiên cho các tên phải duy nhất toàn Azure, resource group |
| `network.tf` | VNet, subnet `apps` (Container Apps) và `db` (PostgreSQL), private DNS zone cho database |
| `data.tf` | PostgreSQL flexible server không có địa chỉ public; storage account bật versioning, tắt truy cập công khai và account key, CORS; container `media`; luật tự xoá phiên bản blob cũ; Service Bus Basic + queue `transcode-jobs`; Key Vault giữ mật khẩu DB |
| `identity.tf` | Hai managed identity (`api`, `worker`) và các role assignment của chúng |
| `apps.tf` | Container Registry, Log Analytics, Container Apps environment trong VNet; app `api`; job `transcode` (chạy khi có message) và job `maintenance` (theo lịch) |

Theo `plan`: với `deploy_apps = false` là 32 tài nguyên, với `true` là 35 (một số khối tạo ra hai role assignment, ba khối chỉ có khi `deploy_apps = true`).

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
2. Build và đẩy hai image với cùng một tag. Máy này không có Docker; hai cách, **chưa cách nào được thử**:
   - `az acr build` (build ngay trong registry): `az acr build --registry <tên registry> --image video-portal-api:<tag> --file deploy/azure/Dockerfile --target api .` và tương tự với `--target worker`. Chưa biết subscription sinh viên có được dùng ACR Tasks không.
   - GitHub Actions (Phase 12).
3. Điền `image_tag`, đặt `deploy_apps = true` → `apply`: tạo app `api` và hai job.
4. Tạo bảng: chạy một lần job `maintenance` với lệnh ghi đè `flask --app app.main init-db` (`az containerapp job start`; cú pháp ghi đè lệnh chưa được thử).
5. Kiểm thử trên địa chỉ mặc định (`default_url`) trước khi đụng tới DNS.

## Chuyển `video.uploadmdm.id.vn` sang Azure (chủ dự án đã chọn 2026-11-21; làm ở Phase 09)

Chứng chỉ miễn phí của Container Apps chỉ cấp được khi tên miền đã trỏ về app, nên **không có giai đoạn chạy song song trên tên này**: từ lúc đổi DNS, bản VPS mất địa chỉ công khai, và trang trên Azure báo lỗi chứng chỉ cho tới khi chứng chỉ cấp xong (thời gian chưa đo).

1. Đặt `domain_name = "video.uploadmdm.id.vn"` trong `terraform.tfvars` và `apply` (chỉ thêm origin vào CORS và danh sách redirect URI).
2. Thêm redirect URI mới vào app registration.
3. Ghi lại bản ghi A hiện tại (IP của VPS) để quay lui, hạ TTL xuống thấp.
4. Thêm bản ghi TXT `asuid.video` (mã xác minh do Azure cấp), rồi đổi bản ghi `video` thành CNAME trỏ về hostname mặc định của app.
5. Gắn tên miền và xin chứng chỉ: `az containerapp hostname add` rồi `az containerapp hostname bind --validation-method CNAME` (chưa thử).
6. Quay lui: đổi bản ghi `video` về bản ghi A cũ. Service trên VPS không bị sửa trong suốt quá trình.

## Chi phí và dọn dẹp

Phần cố định ước tính khoảng 27 USD/tháng ở `malaysiawest` (PostgreSQL B1ms + 32 GiB, registry Basic, private DNS zone); bảng và nguồn giá ở `docs/AZURE_ARCHITECTURE.md`. Gói Azure for Students liệt kê 750 giờ PostgreSQL B1ms và 32 GB mỗi tháng trong 12 tháng là miễn phí; nếu áp dụng cho subscription này thì phần cố định còn khoảng 5,6 USD/tháng, nhưng điều đó chưa xác nhận. Credit 100 USD theo tài liệu; số dư thật chưa xem. Hết credit thì mọi dịch vụ bị vô hiệu hoá. Ngân sách cảnh báo không phải trần chi tiêu.

Dọn dẹp sau demo: `terraform destroy` xoá mọi thứ ở đây, **kể cả database và toàn bộ video**. Key Vault đã xoá vẫn được Azure giữ 7 ngày trừ khi đặt `allow_destroy_data = true` trước khi destroy. Sau đó kiểm tra resource group đã trống và xem trang Cost Management.

## Chưa kiểm chứng (phải xem lại ở lần `plan`/`apply` đầu tiên)

- Subscription sinh viên có thật sự cho tạo từng tài nguyên này ở `malaysiawest` không. Đã đọc được: region nằm trong danh sách cho phép, mọi loại tài nguyên có ở region, PostgreSQL có B1ms và bản 18. Hạn mức và giới hạn riêng của gói sinh viên thì chưa biết.
- Role của identity: `Storage Blob Data Owner` ở mức container có đủ để SAS do `api` ký hoạt động và để xoá phiên bản; `Azure Service Bus Data Owner` ở mức queue có đúng là thứ KEDA cần để đếm message (tài liệu KEDA không nêu role).
- Luật scale bằng managed identity cho **job** (Terraform có trường `identity_id`; lệnh CLI tương ứng còn ghi "Preview").
- Bậc Basic của Service Bus có dead-letter queue và xác thực Entra (tài liệu đã đọc chỉ ghi "queues only").
- Meter "Environment Management Hour" 0,10 USD/giờ trong bảng giá: tài liệu billing nói phí quản lý chỉ áp dụng khi có profile Dedicated hoặc dùng private endpoint/planned maintenance của environment; thiết kế này không dùng thứ nào trong đó, nhưng phải xem Cost Management sau ngày đầu.
- Kết nối tới PostgreSQL dùng TLS do máy chủ yêu cầu nhưng ứng dụng không kiểm tra chứng chỉ của máy chủ (`sslmode` mặc định của libpq); đường đi nằm trọn trong VNet.

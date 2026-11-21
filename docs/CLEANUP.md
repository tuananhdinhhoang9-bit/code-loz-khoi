# Dọn dẹp tài nguyên sau khi chấm

Viết ngày 2026-11-21 cho bản Azure ở `malaysiawest`. **CHƯA CHẠY: chưa có lệnh nào trong tài liệu này được thực hiện; tài nguyên vẫn đang chạy và đang tính tiền.** Lệnh và tên biến lấy từ `infra/azure/README.md` và `infra/azure/variables.tf`. Khi làm thật, ghi kết quả vào `docs/PROGRESS.md`.

Quy tắc của dự án: `terraform destroy` và mọi thao tác xoá dữ liệu chỉ chạy khi **chủ dự án đồng ý rõ ràng**. `terraform plan` thì chạy tự do.

## Phạm vi

| Hệ thống | Tài liệu này có đụng tới không |
| --- | --- |
| Bản Azure: resource group `videoportal-rg` (48 tài nguyên do Terraform quản lý) và resource group do Azure tự tạo cho environment (`ME_videoportal-env_…`) | Có |
| Tồn dư từ lần thử AWS: một chứng chỉ ACM | Không tự xoá; cần chủ dự án quyết định (mục 6) |
| Bản Windows VPS (`C:\VideoPortal`, các service `VideoPortal-API`, `VideoPortal-Worker`, `VideoPortal-Caddy`) | **Không.** Đây là hệ thống riêng (mục 7) |

## 1. Chọn một trong hai hướng

| | Giữ trang chạy, giảm tiền | Xoá toàn bộ |
| --- | --- | --- |
| Khi nào | Còn phải cho thầy xem lại, chưa chấm xong | Đã chấm xong |
| Còn tốn | khoảng 52 USD/tháng (khoảng 1,7 USD/ngày) theo giá niêm yết | 0, sau khi kiểm tra ở mục 5 |
| Mất gì | Lần mở trang đầu tiên sau khi nghỉ phải chờ container khởi động (thời gian chưa đo) | Database, toàn bộ video, log, image trong registry; không khôi phục được |
| Làm theo | mục 2 | mục 3, 4, 5 |

Con số 52 USD là phép tính từ bảng giá niêm yết trong `docs/AZURE_MONITORING_COST.md` (67,8 trừ 15,55 của replica luôn bật), chưa phải hoá đơn.

## 2. Giữ trang chạy rẻ hơn: `api_min_replicas = 0`

App `api` co về 0 replica khi không ai dùng. Database, registry, load balancer, địa chỉ IP và job bảo trì (5 phút một lần) **vẫn tính tiền**: đây không phải là dọn dẹp.

1. Trong `infra/azure/terraform.tfvars` (file đã gitignore), đặt:
   ```hcl
   api_min_replicas = 0
   ```
2. Đăng nhập và xem trước (ba lệnh đầu giống mục 3, bước 2):
   ```powershell
   & .\.tools\terraform\terraform.exe -chdir=infra/azure plan
   ```
   Kết quả mong đợi: chỉ app `api` thay đổi. Image đang chạy không bị đổi, vì Terraform bỏ qua thuộc tính `image` (ADR-029).
3. Khi chủ dự án đồng ý: `& .\.tools\terraform\terraform.exe -chdir=infra/azure apply`.
4. Kiểm tra: mở trang, lần đầu sẽ chậm hơn; `/health` phải trả `database: ok`.

Trước một buổi trình bày khác, đặt lại `api_min_replicas = 1` theo cùng cách.

## 3. Xoá toàn bộ bản Azure

Trước khi xoá:

- [ ] Chủ dự án xác nhận đã chấm xong và đồng ý xoá.
- [ ] Đã lưu những gì muốn giữ làm bằng chứng. Sau khi xoá sẽ không còn workbook, log trong Log Analytics, lịch sử lần chạy job, image trong registry (workflow `rollback` không dùng được nữa) và số liệu chưa chép ra. Lịch sử chi phí trong Cost Management thuộc về subscription, không thuộc resource group.
- [ ] Không có video nào đang xử lý.

Các bước, chạy trong PowerShell tại thư mục gốc của repo:

1. Trong `infra/azure/terraform.tfvars`, thêm dòng dưới đây và **không đổi dòng nào khác**:
   ```hcl
   allow_destroy_data = true
   ```
   Biến này cho Terraform xoá hẳn Key Vault ngay. Nếu để `false`, Azure giữ vault đã xoá thêm 7 ngày. Database và Blob Storage thì luôn mất khi destroy, dù biến này là gì.
2. Chủ dự án tự đăng nhập, chọn subscription bằng biến môi trường, đưa `az` vào PATH:
   ```powershell
   & .\.tools\azcli\bin\az.cmd login --use-device-code
   $env:ARM_SUBSCRIPTION_ID = & .\.tools\azcli\bin\az.cmd account show --query id -o tsv
   $env:PATH = "$PWD\.tools\azcli\bin;" + $env:PATH
   ```
3. Xem trước những gì sẽ bị xoá (không thay đổi gì):
   ```powershell
   & .\.tools\terraform\terraform.exe -chdir=infra/azure plan -destroy
   ```
   Mong đợi dòng `Plan: 0 to add, 0 to change, 48 to destroy` (48 là tổng ghi trong `docs/PROGRESS.md` ngày 2026-11-21; nếu khác, đọc danh sách trước khi đi tiếp).
4. Xoá:
   ```powershell
   & .\.tools\terraform\terraform.exe -chdir=infra/azure destroy
   ```
   Terraform in lại danh sách và chờ gõ `yes`. Lúc tạo, riêng database mất khoảng 5 phút và environment gần 4 phút; thời gian xoá chưa đo.
5. Nếu lệnh dừng giữa chừng vì lỗi: đọc lỗi, rồi chạy lại đúng lệnh `destroy`; Terraform chỉ xoá phần còn lại. **Không xoá file `infra/azure/terraform.tfstate`** khi tài nguyên còn tồn tại: đó là bản ghi duy nhất về những gì đã tạo.

## 4. Những thứ `terraform destroy` không xoá

| Thứ còn lại | Ở đâu | Có tính tiền không | Việc cần làm |
| --- | --- | --- | --- |
| Resource provider đã đăng ký: chín cái của bước nền và hai cái của Azure Monitor (`Microsoft.Insights`, `Microsoft.AlertsManagement`) | Subscription | Không (việc đăng ký miễn phí) | Không bắt buộc. Muốn gỡ: `az provider unregister --namespace Microsoft.Insights`, tương tự cho từng cái. Terraform được cấu hình để không tự đăng ký và không tự gỡ |
| Bốn secret của kho GitHub: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_REGISTRY` | GitHub > Settings > Secrets and variables > Actions | Không | Xoá tay. Chúng là ID, không phải mật khẩu, nhưng nếu để lại thì mỗi lần push lên `main` job `images` sẽ thử đăng nhập vào một identity không còn tồn tại và báo lỗi. Khi không có secret, job `images` và `deploy` chỉ ghi một thông báo rồi kết thúc (theo `.github/workflows/ci.yml`; chưa thử sau khi xoá) |
| Federated credential của GitHub | Thuộc identity `videoportal-deploy` | — | **Không còn lại:** nó là tài nguyên con của identity và bị xoá cùng identity trong bước destroy. Kiểm tra ở mục 5 |
| Bản ghi DNS của tên miền | Nhà đăng ký tên miền | — | **Không có gì để sửa:** tên miền riêng chưa bao giờ được chuyển sang Azure, vẫn trỏ về VPS. Không đụng vào DNS trong lần dọn dẹp này |
| External tenant của Entra | — | — | Chưa bao giờ được tạo, nên không có gì để xoá |
| Key Vault đã xoá mềm | Subscription | — | Chỉ còn nếu quên bước 1 của mục 3. Azure giữ 7 ngày rồi tự xoá; trong thời gian đó tên vault bị giữ chỗ. Xem bằng lệnh ở mục 5 |
| File trên máy: `infra/azure/terraform.tfstate`, `terraform.tfstate.backup`, `terraform.tfplan`, `terraform.tfvars`, `.env.github` | Máy đang chạy Terraform | Không | Đều đã gitignore. File state cũ còn chứa mật khẩu của database đã xoá và file tfvars chứa địa chỉ nhận cảnh báo: giữ tới khi kiểm tra xong mục 5, sau đó chủ dự án quyết định xoá hay giữ. Không bao giờ commit |
| Các nhánh `main`, `vps`, `aws` và lịch sử Actions trên GitHub | GitHub | Không | Giữ làm mã nguồn nộp bài |

## 5. Kiểm tra không còn gì tính tiền

Ngay sau khi destroy xong (các lệnh chỉ đọc):

```powershell
& .\.tools\azcli\bin\az.cmd group list -o table
& .\.tools\azcli\bin\az.cmd resource list -o table
& .\.tools\azcli\bin\az.cmd keyvault list-deleted -o table
```

- `group list`: không còn `videoportal-rg` và không còn nhóm nào tên bắt đầu bằng `ME_videoportal-env_`. Trước dự án, subscription không có resource group nào. Nếu thấy nhóm lạ, xem bên trong trước, đừng xoá vội.
- `resource list`: danh sách trống. Dòng nào còn lại là thứ còn có thể tính tiền; identity `videoportal-deploy` cũng không được còn ở đây.
- `keyvault list-deleted`: trống nếu đã đặt `allow_destroy_data = true`.

Ngày hôm sau (dữ liệu chi phí trễ 8–24 giờ):

- Azure Portal > **Cost Management > Cost analysis**, phạm vi là subscription, xem theo ngày và nhóm theo dịch vụ. Mong đợi: ngày destroy còn một phần chi phí, các ngày sau bằng 0.
- Xem số dư credit của Azure for Students trong cổng Azure và ghi lại vào `docs/PROGRESS.md`.

Chưa xác nhận xong thì chưa được ghi là "đã dọn dẹp".

## 6. Tồn dư từ lần thử AWS: cần chủ dự án quyết định

Mục tiêu AWS đã bị bỏ ngày 2026-11-21, nhưng còn **một tài nguyên thật**: một chứng chỉ ACM cho tên miền của dự án ở region `ap-southeast-2`, không gắn vào dịch vụ nào. Nó được ghi trong file `infra/aws/terraform.tfstate` (đã gitignore; không xoá file này khi chứng chỉ còn tồn tại).

- Chi phí: theo hiểu biết lúc tạo thì chứng chỉ ACM công khai không tính tiền; điều này chưa được tra lại trong bảng giá.
- Việc này **tách khỏi** dọn dẹp Azure. Không ai chạy Terraform hay lệnh AWS nào với nó khi chủ dự án chưa yêu cầu (quy định trong `AGENTS.md`).
- Chủ dự án chọn: giữ nguyên, hoặc xoá. Xoá cần chính chủ dự án đăng nhập AWS. Sau khi chứng chỉ đã xoá, bản ghi CNAME dùng để xác minh nó ở nhà đăng ký tên miền cũng xoá được; khi sửa DNS chỉ xoá đúng dòng đó. `docs/PROGRESS.md` ghi lại một lần bản ghi `video` của trang VPS bị mất khi sửa DNS.

## 7. Bản Windows VPS: không đụng tới

Bản VPS là một hệ thống riêng, đang chạy và đang giữ tên miền của dự án. Dọn dẹp Azure **không** dừng service nào, không đổi tường lửa, không đổi DNS và không xoá dữ liệu nào trên VPS. `terraform destroy` trong `infra/azure` không tác động tới nó, dù thư mục repo nằm trên cùng máy. Mọi thay đổi với VPS cần một yêu cầu riêng của chủ dự án.

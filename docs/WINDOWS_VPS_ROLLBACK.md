# Quay lui (rollback)

Phase 07 chưa cài gì lên VPS, nên chưa có gì để quay lui ở đó. Tài liệu này dành cho Phase 08 trở đi.

## Nguyên tắc

- Quay lui **mã nguồn** và quay lui **dữ liệu** là hai việc khác nhau. Mã nguồn quay lui bằng Git; dữ liệu chỉ quay lui bằng bản sao lưu.
- Thay đổi schema của dự án chỉ là **thêm** (bảng mới, cột mới qua `init-db`). Mã nguồn cũ vẫn chạy được trên schema mới, nên quay lui mã nguồn không cần đụng database.
- Không script nào xoá dữ liệu khi quay lui. Việc xoá luôn là thao tác thủ công, có chủ đích.

## Quay lui một bản cập nhật ứng dụng

```powershell
cd C:\VideoPortal\app
git log --oneline -5                      # ghi lại commit đang chạy và commit muốn quay về
.\scripts\windows\stop-services.ps1
git checkout <commit-tot-truoc-do>
C:\VideoPortal\venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\windows\start-services.ps1
.\scripts\windows\status.ps1
```

Không chạy `init-db` khi quay lui (không cần, và nó không gỡ gì). Ghi lại commit đã quay về vào `docs/EVIDENCE.md` cùng thời điểm và kết quả `status.ps1`.

## Quay lui cấu hình

Trước khi sửa `config\.env` hoặc `Caddyfile`, sao chép bản cũ thành `.env.bak-<ngày>`. Quay lui = chép lại rồi `restart-services.ps1`. Caddyfile sai cú pháp thì Caddy không khởi động: kiểm tra trước bằng `caddy validate --config C:\VideoPortal\config\Caddyfile --adapter caddyfile`.

## Quay lui dữ liệu

Xem `docs/WINDOWS_VPS_BACKUP.md`, mục "Khôi phục thật sau sự cố": khôi phục vào database mới, kiểm tra, rồi đổi `POSTGRES_DB`. Database cũ được giữ lại, nên bước này tự nó có thể quay lui bằng cách đổi `POSTGRES_DB` về tên cũ.

## Gỡ cài đặt service (quay về trạng thái trước Phase 08)

Chỉ làm khi đã được duyệt; dữ liệu trong `storage`, `backups`, `config` và database **không** bị đụng tới:

```powershell
.\stop-services.ps1
foreach ($name in 'VideoPortal-Caddy','VideoPortal-Worker','VideoPortal-API') { & "C:\VideoPortal\services\$name.exe" uninstall }
Unregister-ScheduledTask -TaskName 'VideoPortal-Backup','VideoPortal-HealthCheck' -Confirm:$false
Remove-NetFirewallRule -DisplayName 'VideoPortal HTTP(S)'      # nếu đã tạo
```

PostgreSQL, Python, FFmpeg và thư mục `C:\VideoPortal` được giữ nguyên. Xoá database, role hay thư mục là quyết định riêng, làm thủ công sau khi đã có bản sao lưu ngoài VPS.

## Quay lui quyết định kiến trúc

| Thành phần mới | Cách quay về hành vi cũ | Mất gì |
| --- | --- | --- |
| Tài khoản nội bộ | `AUTH_PROVIDER=firebase` + cấu hình Firebase | Cần project Firebase và Google credentials |
| Hàng đợi PostgreSQL + worker native | Trên máy dev: `flask local-process` (file queue + Docker) vẫn dùng được | Không dùng cho production |
| Giới hạn 200 MB | `MAX_UPLOAD_BYTES=50000000` | — |
| Hạ tầng GCP | `infra/` (Terraform, đã `validate` và `plan`, chưa `apply`) còn nguyên | Phải viết adapter GCS/PubSub (chưa từng có) |

## Chưa kiểm chứng

Toàn bộ quy trình ở trang này chưa được chạy trên VPS thật. Bằng chứng quay lui thật (commit trước/sau, thời điểm, `status.ps1`) phải được ghi ở Phase 08 trở đi.

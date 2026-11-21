# Giám sát, cảnh báo và chi phí trên Azure (Phase 11)

Viết ngày 2026-11-21 cho bản đang chạy ở `malaysiawest`. Mọi con số đều ghi rõ là **đo thật**, **giá niêm yết** hay **ước tính**. Bằng chứng theo ngày giờ nằm ở `docs/EVIDENCE.md`.

## Dashboard

Workbook **Video Portal** của Azure Monitor (Azure Portal > Monitor > Workbooks, hoặc Log Analytics workspace `videoportal-logs` > Workbooks). Tạo bằng `infra/azure/monitoring.tf`; không có agent hay dịch vụ nào thêm, mọi ô đọc log JSON mà `api` và hai job đã ghi vào Log Analytics (chậm khoảng 1–3 phút).

| Ô | Nguồn | Loại số liệu |
| --- | --- | --- |
| Job chuyển mã theo kết quả, mỗi giờ | dòng `worker_outcome` của job | đo thật |
| Tổng hợp các clip đã READY: p50/p95 thời gian xử lý, p50/p95 thời gian chờ, tổng dung lượng kết quả | dòng `PROCESSING` (`queue_age_seconds`) và `READY` (`processing_seconds`, `output_bytes`) | đo thật |
| Egress ước tính | dung lượng kết quả x 3 lượt xem giả định | ước tính |
| Chi phí tính toán mỗi clip | (25 giây khởi động + thời gian xử lý) x giá niêm yết của 1 vCPU và 2 GiB | ước tính, chưa trừ phần miễn phí |
| Lỗi và lần thử lại | dòng `RETRYING`/`FAILED` kèm `job_id`, `attempt_id`, tên lần chạy job | đo thật |
| Nối request với job | dòng `QUEUED` của `api` (`request_id`, `video_id`, `job_id`) ghép với trạng thái cuối của job | đo thật |
| API: request, lỗi 5xx, 4xx, p95 thời gian xử lý mỗi 5 phút | access log `app.access` | đo thật |
| Job bảo trì: những lần có việc phải làm | dòng `maintenance` | đo thật |

Trang `/api/monitor` trong portal chỉ là bảng đếm cho quản trị viên; nó không thay cho workbook này.

## Tra một sự cố qua các ID

1. Người dùng báo lỗi kèm `request_id` (có trong mọi câu trả lời JSON của API).
2. Ô "Nối request với job": `request_id` -> `video_id` -> `job_id`.
3. Ô "Lỗi và lần thử lại": `job_id` -> từng `attempt_id`, mã lỗi và tên lần chạy job (`videoportal-transcode-xxxxx`).
4. Log hệ thống của Container Apps (`ContainerAppSystemLogs_CL`) theo tên lần chạy: KEDA quyết định gì, kéo image mất bao lâu, container kết thúc vì sao.

Log không chứa mật khẩu, token, SAS hay nội dung video: formatter che `password|token|secret` và `Bearer …`; SDK của Azure chỉ ghi từ mức WARNING; đường dẫn request chỉ có ID.

## Cảnh báo

| Mục | Giá trị |
| --- | --- |
| Tên | `videoportal-transcode-system-failure` (scheduled query rule, mức 2) |
| Điều kiện | Trong 5 phút có ít nhất một dòng: job chuyển mã ghi `"status": "RETRYING"`, **hoặc** job bảo trì ghi `"recovered"` lớn hơn 0 |
| Vì sao điều kiện này | `RETRYING` chỉ xảy ra với lỗi hệ thống (worker bị dừng, lỗi storage/queue). File sai định dạng hay quá dài đi thẳng tới `FAILED`, nên người dùng tải file sai không làm cảnh báo nổ. `recovered > 0` bắt trường hợp worker chết không kịp ghi gì |
| Chu kỳ đánh giá / cửa sổ | 5 phút / 5 phút |
| Độ trễ dự kiến | 3–10 phút sau sự cố: log tới Log Analytics chậm 1–3 phút, cộng tối đa 5 phút tới lần đánh giá kế tiếp, cộng thời gian gửi email |
| Độ trễ đo được | Xem `docs/EVIDENCE.md` (ghi sau lần diễn tập có cảnh báo) |
| Hành động | Email tới chủ dự án qua action group `videoportal-ops`; tự đóng khi điều kiện hết đúng |
| Việc làm đầu tiên | Mở workbook, ô "Lỗi và lần thử lại", lấy `job_id`; kiểm tra lần thử sau đã `READY` chưa; kiểm tra hàng đợi và dead-letter queue trống. Cùng một job hỏng 3 lần thì thành `FAILED` và phải tải lại |

Cảnh báo ngân sách (budget alert) của Azure, nếu đặt, **chỉ gửi thông báo, không chặn chi tiêu**. Thứ thật sự dừng tiền là xoá tài nguyên (`terraform destroy`) hoặc giảm cấu hình.

## Chi phí hằng tháng theo tải (giá niêm yết, chưa phải hoá đơn)

Giá đọc từ Azure Retail Prices API (`https://prices.azure.com/api/retail/prices`) ngày 2026-11-21 cho `malaysiawest`, USD, chưa thuế. Tháng tính 730 giờ.

| Hạng mục | Cấu hình đang chạy | Giá | USD/tháng |
| --- | --- | --- | --- |
| PostgreSQL flexible server | B1ms, chạy 24/7 | 0,0234/giờ | 17,08 |
| Lưu trữ PostgreSQL (gồm backup 7 ngày trong mức cấp phát) | 32 GiB | 0,1242/GiB | 3,97 |
| Container Registry | Basic | 0,1666/ngày | 5,00 |
| Load balancer của environment (Azure tự tạo vì dùng VNet) | Standard, 2 rule | 0,025/giờ | 18,25 |
| Địa chỉ IP công khai của environment | Standard | 0,005/giờ | 3,65 |
| Private DNS zone | 1 zone | 0,5/tháng | 0,50 |
| Cảnh báo log | 1 rule, 5 phút | 1,5/tháng | 1,50 |
| **Cố định** | | | **49,95** |
| API luôn bật 1 bản (`api_min_replicas = 1`) | 0,5 vCPU + 1 GiB, giá lúc rảnh 0,000004/vCPU-giây và 0,000004/GiB-giây | 0,000006/giây | 15,55 |
| Job bảo trì | 0,25 vCPU + 0,5 GiB, 8.640 lần x khoảng 30 giây | 0,000009/giây | 2,33 |
| **Tổng khi không có video nào** | | | **khoảng 67,8 (2,26/ngày)** |

Phần thay đổi theo tải:

| Hạng mục | Cách tính | Ví dụ |
| --- | --- | --- |
| Chuyển mã | (25 giây khởi động + thời gian xử lý) x (1 vCPU x 0,000028 + 2 GiB x 0,000004) | Đo được: clip mẫu 1–3 giây khoảng 0,00095 USD; clip 1080p 29 giây (xử lý 12,6 giây) khoảng 0,00135 USD. 100 clip/tháng khoảng 0,10–0,14 USD |
| Request của API | 0,468 USD/triệu request | 10.000 request khoảng 0,005 USD |
| Blob Storage | theo GB lưu và số thao tác | 12 clip hiện có: 4,3 MB kết quả; không đáng kể |
| Service Bus Basic | theo triệu thao tác | không đáng kể |
| Log Analytics | 2,691 USD/GB sau phần miễn phí hằng tháng | hôm nay khoảng vài MB |
| Egress tới trình duyệt | dung lượng kết quả x số lượt xem | 12 clip x 3 lượt khoảng 13 MB; không đáng kể |

Chưa tính và chưa kiểm chứng: phần miễn phí hằng tháng của Container Apps, 750 giờ PostgreSQL B1ms miễn phí mà trang Azure for Students nêu, và 5 GB log miễn phí. Nếu các phần này được áp dụng thì số thật thấp hơn bảng trên; chỉ Cost Management mới trả lời được.

### Số thật từ Cost Management

Đọc ngày 2026-11-21 khoảng 15:12 UTC (API `Microsoft.CostManagement/query`, ActualCost, từ đầu tháng): tổng **0,0125 USD** — Container Registry 0,0073; Virtual Network 0,0050; Key Vault, Azure DNS, Storage, Service Bus dưới 0,0001; Load Balancer và Bandwidth 0. **Con số này chưa đầy đủ**: dữ liệu chi phí trễ 8–24 giờ, tài nguyên mới tạo trong ngày, và PostgreSQL, Container Apps, Log Analytics chưa xuất hiện. Phải đọc lại từ 2026-11-22 rồi so với bảng giá niêm yết.

### Giữ credit qua buổi thuyết trình

- Ở mức niêm yết khoảng 2,26 USD/ngày: 4 ngày khoảng 9 USD, 11 ngày khoảng 25 USD, trong khi credit là 100 USD.
- Sau buổi demo: đặt `api_min_replicas = 0` (tiết kiệm khoảng 15,5 USD/tháng, đổi lại lần mở trang đầu chậm vài giây).
- Sau khi chấm xong: `terraform destroy` (hướng dẫn ở `infra/azure/README.md`), rồi kiểm tra không còn resource group nào của dự án.

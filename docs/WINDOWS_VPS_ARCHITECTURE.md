# Kiến trúc trên VPS Windows Server (thay thế kiến trúc GCP)

> **ARCHIVED (2026-11-20): VPS Windows không còn là mục tiêu triển khai.** Mục tiêu mới là AWS, xem `docs/AWS_ARCHITECTURE.md` (ADR-021). Bản VPS vẫn đang chạy và tài liệu này còn đúng với nó; giữ lại để đối chiếu và làm chế độ local.

**Trạng thái:** thiết kế + mã nguồn + kiểm thử trên máy phát triển Windows 11 (Phase 07). Chưa cài lên VPS thật; xem `docs/PROGRESS.md` để biết phần nào đã kiểm chứng.

Từ 2026-11-17 dự án **không dùng Google Cloud**. Tài liệu GCP cũ (`docs/ARCHITECTURE.md`, `docs/CLOUD_DEPLOY.md`, `docs/COST_MONITORING.md`, thư mục `infra/`) được giữ lại để đối chiếu, đã đánh dấu ARCHIVED.

## Sơ đồ

```text
Internet ──443/80──> Caddy (VideoPortal-Caddy)            chỉ cổng này lộ ra ngoài
                        │ reverse proxy, HTTPS, giới hạn body 201 MB
                        ▼
            Waitress 127.0.0.1:8000 (VideoPortal-API)     Flask: API + giao diện
                        │                    │
        PostgreSQL 127.0.0.1:5432            │ đọc/ghi file riêng tư
        (service có sẵn của Windows)         ▼
          videos, jobs, outbox,        C:\VideoPortal\storage\objects
          queue_messages, users          inputs\   (video gốc)
                        ▲                outputs\  (MP4 + JPG đã xử lý)
                        │ claim job (SKIP LOCKED + lease)
            Worker (VideoPortal-Worker)  ──> python -m worker.transcode ──> ffmpeg.exe
              reconcile → relay outbox → nhận 1 message → 1 job FFmpeg
              thư mục tạm: C:\VideoPortal\storage\temporary
```

## Thành phần và ánh xạ từ kiến trúc cũ

| Trước đây (GCP, chưa từng triển khai) | Bây giờ (VPS Windows) | Mã nguồn |
| --- | --- | --- |
| Cloud Run service `video-api` | Waitress sau Caddy, service `VideoPortal-API` | `app/serve.py`, `app/main.py` |
| Cloud SQL | PostgreSQL cài trực tiếp trên Windows, chỉ nghe localhost | `scripts/windows/setup-database.ps1` |
| Cloud Storage + signed URL | Thư mục NTFS riêng tư + ticket ký 120 giây (đã có từ Phase 04) | `app/storage.py` |
| Pub/Sub + dead-letter | Bảng `queue_messages` trong PostgreSQL | `app/queue_pg.py` |
| Cloud Scheduler + relay + dispatcher | Gộp vào vòng lặp của worker | `app/worker_service.py` |
| Cloud Run Job + Docker | Tiến trình con trong Windows Job Object | `app/worker_native.py`, `worker/transcode.py` |
| Firebase Auth | Tài khoản nội bộ trong PostgreSQL (Firebase còn là lựa chọn phụ) | `app/auth_local.py`, `app/auth.py` |
| Secret Manager | File `config\.env` được khoá bằng NTFS ACL | `.env.example` |
| Cloud Monitoring | Log JSON xoay vòng + health check định kỳ + `/api/monitor` | `app/logs.py`, `scripts/windows/healthcheck.ps1` |
| Terraform | Script PowerShell có chế độ plan/`-Apply` | `scripts/windows/` |

## Giữ nguyên từ Phase 01–06

Flask/Jinja/JS thuần; mô hình dữ liệu 6 bảng gốc; outbox giao dịch (job + event cùng một transaction); khoá logic `(video, source_generation, profile)`; lease + attempt UUID chống ghi trùng; tối đa 3 lần thử với backoff 5/10 giây; output chỉ được công bố khi cả MP4 và JPG đã kiểm tra và ghi DB trong một transaction; ticket ký cho upload/phát; Range playback; `worker/transcode.py` (ffprobe + FFmpeg, một profile H.264/AAC 480p). Toàn bộ 86 test cũ vẫn chạy.

## Cấu trúc thư mục

Đề xuất ban đầu có `storage\source`, `processed`, `thumbnails`. Mã nguồn từ Phase 04–06 đã dùng `inputs/` và `outputs/<job>/<attempt>/` nên giữ nguyên để không phá phần đã kiểm thử:

```text
C:\VideoPortal
  app\          mã nguồn (git clone / giải nén)
  venv\         môi trường Python
  config\       .env, Caddyfile            (chỉ Administrators + tài khoản service đọc)
  logs\         api.log, worker.log, *-error.log, caddy-access.log, health.log, services\
  storage\
    objects\inputs\<video>\<hex>                       video gốc      (= "source")
    objects\outputs\<job>\<attempt>\video.mp4          đã xử lý       (= "processed")
    objects\outputs\<job>\<attempt>\thumbnail.jpg      ảnh thu nhỏ    (= "thumbnails")
    temporary\<job>\<attempt>\                         thư mục tạm của worker
  backups\      bản dump PostgreSQL (cần thêm bản sao ngoài VPS)
  services\     file WinSW (.exe + .xml)
  tools\        ffmpeg, caddy, winsw
  caddy\        dữ liệu chứng chỉ của Caddy
```

Mọi đường dẫn lấy từ biến môi trường (`STORAGE_ROOT`, `WORK_ROOT`, `LOG_DIR`); code dùng `pathlib`. Ở `APP_ENV=production` ứng dụng từ chối khởi động nếu `STORAGE_ROOT`/`WORK_ROOT` không tuyệt đối hoặc nằm trong thư mục mã nguồn.

## Luồng xử lý một video

1. Trình duyệt `POST /api/videos` → server kiểm tra kích thước, loại file, dung lượng đĩa còn trống → trả ticket upload.
2. `PUT /local-storage/upload?ticket=…` → ghi file tạm, fsync, hard-link nguyên tử (không ghi đè) → metadata SHA-256.
3. `POST …/complete` → một transaction: `Video=QUEUED` + `TranscodeJob` + `OutboxEvent`.
4. Worker: `reconcile` (lease hết hạn → RETRYING/QUEUED) → khi hàng đợi trống thì `relay` 1 event sang `queue_messages` → `receive` (SKIP LOCKED, ẩn 300 giây) → `claim_job` (lease 180 giây + attempt UUID).
5. Worker chép nguồn vào thư mục tạm, chạy `python -m worker.transcode --progress` trong Job Object (giới hạn RAM, 2 CPU, tự kill khi worker chết). Mỗi 3 giây heartbeat gia hạn lease và ghi `progress_percent`.
6. Xong: ghi 2 object vào `outputs/`, rồi một transaction thêm 2 `OutputObject` + `READY`. Sau đó mới ack message.
7. Người xem có quyền gọi `/playback` → ticket 120 giây → `/local-storage/read` phục vụ file có Range.

## Miền lỗi (failure domain)

Một máy, một ổ đĩa, một PostgreSQL: mất VPS là mất dịch vụ cho tới khi khôi phục từ bản sao lưu ngoài VPS. Đây là đánh đổi có chủ đích cho chi phí 0đ; xem `docs/WINDOWS_VPS_BACKUP.md` và `docs/WINDOWS_VPS_ROLLBACK.md`.

## Tài nguyên (3 vCPU, 4 GB RAM)

| Thành phần | Giới hạn cấu hình | Đo trên máy dev (không phải VPS) |
| --- | --- | --- |
| API (Waitress) | 6 luồng, pool DB 4+2 | ~100–130 MB |
| Worker (Python) | 1 job mỗi lúc (advisory lock + vòng lặp tuần tự) | ~125 MB |
| FFmpeg | `FFMPEG_THREADS=2`, affinity 2 CPU, Job Object 1536 MB, ưu tiên thấp | ~113 MB, trung bình 1.8 nhân |
| PostgreSQL | role giới hạn 20 kết nối; gợi ý `max_connections=30`, `shared_buffers=512MB` | ~146 MB (cấu hình mặc định) |
| Caddy | — | ~49 MB |

Số đo: clip 30 giây 1280×720 (19.9 MB) xử lý 14.3 giây trên máy dev 8 nhân logic với giới hạn 2 CPU. Chưa đo trên VPS; không suy ra hiệu năng VPS từ số này.

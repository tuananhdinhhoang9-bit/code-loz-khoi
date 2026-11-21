# Video Portal trên Azure: một file, hai image (build từ thư mục gốc của repo).
#   docker build -f deploy/azure/Dockerfile --target api    -t video-portal-api .
#   docker build -f deploy/azure/Dockerfile --target worker -t video-portal-worker .
# Không có secret nào trong image: mật khẩu DB do Container Apps nạp từ Key Vault, quyền Azure lấy từ managed identity.
# CHƯA BUILD LẦN NÀO (máy phát triển không có Docker); lần build đầu thuộc Phase 09/12.

FROM python:3.12-slim-bookworm AS base
# DISPATCH_SECONDS: job chuyển mã chỉ khởi động sau khi KEDA thấy message và container kéo xong image.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    APP_ENV=production STORAGE_BACKEND=blob QUEUE_BACKEND=servicebus AUTH_PROVIDER=oidc \
    DISPATCH_SECONDS=300 WORK_ROOT=/var/videoportal/work
WORKDIR /srv/videoportal
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home portal \
    && mkdir -p /var/videoportal/work \
    && chown portal /var/videoportal/work
COPY app app
COPY worker worker

# API: Waitress sau ingress của Container Apps (đường duy nhất vào cổng 8000).
# Job "maintenance" theo lịch dùng chính image này với lệnh: flask --app app.main maintain
FROM base AS api
ENV BIND_HOST=0.0.0.0 BIND_PORT=8000 TRUSTED_PROXY=*
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "app.serve"]

# Worker: cùng mã nguồn, thêm FFmpeg. Mỗi lần chạy của Container Apps Job xử lý tối đa một video rồi thoát.
FROM base AS worker
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
USER 10001:10001
CMD ["python", "-m", "app.worker_service", "--once"]

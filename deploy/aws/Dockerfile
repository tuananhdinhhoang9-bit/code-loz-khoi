# Video Portal trên AWS: một file, hai image (build từ thư mục gốc của repo).
#   docker build -f deploy/aws/Dockerfile --target api    -t video-portal-api .
#   docker build -f deploy/aws/Dockerfile --target worker -t video-portal-worker .
# Không có secret nào trong image: mật khẩu DB do ECS nạp từ Secrets Manager, quyền AWS lấy từ task role.

FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    APP_ENV=production STORAGE_BACKEND=s3 QUEUE_BACKEND=sqs AUTH_PROVIDER=cognito \
    WORK_ROOT=/var/videoportal/work
WORKDIR /srv/videoportal
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home portal \
    && mkdir -p /var/videoportal/work \
    && chown portal /var/videoportal/work
COPY app app
COPY worker worker

# API: Waitress sau Application Load Balancer. Security group chỉ cho ALB gọi vào cổng 8000.
FROM base AS api
ENV BIND_HOST=0.0.0.0 BIND_PORT=8000 TRUSTED_PROXY=*
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "app.serve"]

# Worker: cùng mã nguồn, thêm FFmpeg. Mỗi task xử lý một video mỗi lúc.
FROM base AS worker
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
USER 10001:10001
CMD ["python", "-m", "app.worker_service"]

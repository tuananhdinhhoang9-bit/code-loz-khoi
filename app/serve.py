"""API production: Waitress chỉ nghe trên loopback, phía trước là Caddy (HTTPS).

Chạy: python -m app.serve
"""

import os
import sys

from waitress import serve

from app.logs import configure_logging
from app.main import create_app, env_int


def main():
    app = create_app()
    configure_logging(app.config.get("LOG_DIR"), "api")
    host = os.getenv("BIND_HOST", "127.0.0.1")
    port = env_int("BIND_PORT", 8000, 1, 65535)
    serve(
        app, host=host, port=port,
        threads=env_int("WAITRESS_THREADS", 6, 1, 32),
        connection_limit=100,
        channel_timeout=env_int("UPLOAD_TIMEOUT_SECONDS", 300, 30, 3600),
        max_request_body_size=app.config["MAX_CONTENT_LENGTH"],
        ident=None,
        # Chỉ tin X-Forwarded-* từ proxy phía trước; header do client tự gửi bị xoá. Mặc định là Caddy trên cùng máy.
        # Trên Azure Container Apps đặt TRUSTED_PROXY=*: ingress không có IP cố định và là đường duy nhất vào container.
        trusted_proxy=os.getenv("TRUSTED_PROXY", "127.0.0.1"), trusted_proxy_count=1,
        trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto", "x-forwarded-host"},
        clear_untrusted_proxy_headers=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

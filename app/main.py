import json
import os
import logging
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.storage import blob_origin

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OIDC_SETTINGS = ["OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_JWKS_URL", "OIDC_AUTHORIZE_URL", "OIDC_TOKEN_URL"]
access_log = logging.getLogger("app.access")


def env_int(name, default, low, high):
    try:
        value = int(os.getenv(name, default))
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def env_path(name):
    value = os.getenv(name, "").strip()
    return Path(value) if value else None


def load_settings():
    """Đọc cấu hình từ biến môi trường; file .env chỉ bổ sung biến còn thiếu."""
    env_file = os.getenv("VIDEO_PORTAL_ENV_FILE", "").strip()
    if env_file:
        if not Path(env_file).is_file():
            raise ValueError("VIDEO_PORTAL_ENV_FILE does not point to a file")
        # File cấu hình được chỉ định rõ luôn thắng, kể cả khi lệnh `flask` đã tự nạp một .env khác trong thư mục hiện tại.
        load_dotenv(Path(env_file), override=True)
    else:
        load_dotenv(PROJECT_ROOT / ".env")
    password = os.getenv("POSTGRES_PASSWORD")
    database_url = None
    if password:
        database_url = URL.create(
            "postgresql+psycopg",
            username=os.getenv("POSTGRES_USER", "video_portal"),
            password=password,
            host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "video_portal"),
        )
    settings = {
        "DATABASE_URL": database_url,
        "FIREBASE_PROJECT_ID": os.getenv("FIREBASE_PROJECT_ID", ""),
        "FIREBASE_WEB_API_KEY": os.getenv("FIREBASE_WEB_API_KEY", ""),
        "AUTH_PROVIDER": os.getenv("AUTH_PROVIDER", "firebase").strip().lower(),
        # Azure (ADR-024). Không có khoá hay connection string nào ở đây: SDK lấy quyền từ managed identity.
        "STORAGE_BACKEND": os.getenv("STORAGE_BACKEND", "local").strip().lower(),
        "QUEUE_BACKEND": os.getenv("QUEUE_BACKEND", "postgres").strip().lower(),
        "AZURE_STORAGE_ACCOUNT": os.getenv("AZURE_STORAGE_ACCOUNT", "").strip(),
        "AZURE_STORAGE_CONTAINER": os.getenv("AZURE_STORAGE_CONTAINER", "").strip(),
        "SERVICEBUS_NAMESPACE": os.getenv("SERVICEBUS_NAMESPACE", "").strip(),
        "SERVICEBUS_QUEUE": os.getenv("SERVICEBUS_QUEUE", "").strip(),
        # OIDC (Microsoft Entra External ID): các giá trị lấy từ tài liệu OpenID configuration của tenant, đều công khai.
        **{name: os.getenv(name, "").strip() for name in OIDC_SETTINGS + ["OIDC_LOGOUT_URL"]},
        "OIDC_EMAIL_CLAIM": os.getenv("OIDC_EMAIL_CLAIM", "email").strip(),
        "OIDC_ADMIN_ROLE": os.getenv("OIDC_ADMIN_ROLE", "admin").strip(),
        "MAX_UPLOAD_BYTES": env_int("MAX_UPLOAD_BYTES", 50_000_000, 1, 2_000_000_000),
        "MIN_FREE_BYTES": env_int("MIN_FREE_BYTES", 500_000_000, 0, 10**13),
        "DB_POOL_SIZE": env_int("DB_POOL_SIZE", 4, 1, 20),
        "DB_MAX_OVERFLOW": env_int("DB_MAX_OVERFLOW", 2, 0, 20),
        "SESSION_HOURS": env_int("SESSION_HOURS", 12, 1, 168),
        "LOG_DIR": env_path("LOG_DIR"),
    }
    for name in ["STORAGE_ROOT", "WORK_ROOT"]:
        if env_path(name):
            settings[name] = env_path(name)
    return settings


def https_url(value):
    """URL công khai của nhà cung cấp đăng nhập: chỉ https, không kèm tài khoản, không có ký tự phá được header CSP."""
    parts = urlsplit(value) if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9:/?&=._~%+-]+", value) else None
    return bool(parts and parts.scheme == "https" and parts.hostname and "@" not in parts.netloc)


def check_runtime(app):
    """Chặn cấu hình nguy hiểm trước khi nhận request thật."""
    if os.getenv("K_SERVICE"):
        raise ValueError("Local storage is not a cloud storage implementation")
    environment = os.getenv("APP_ENV", "local")
    if environment not in {"local", "production"}:
        raise ValueError("APP_ENV must be local or production")
    provider = app.config.get("AUTH_PROVIDER", "firebase")
    storage_backend = app.config.get("STORAGE_BACKEND", "local")
    queue_backend = app.config.get("QUEUE_BACKEND", "postgres")
    if provider not in {"firebase", "local", "oidc"}:
        raise ValueError("AUTH_PROVIDER must be firebase, local or oidc")
    if storage_backend not in {"local", "blob"}:
        raise ValueError("STORAGE_BACKEND must be local or blob")
    if queue_backend not in {"postgres", "servicebus"}:
        raise ValueError("QUEUE_BACKEND must be postgres or servicebus")
    # Các tên này được ghép vào URL và header CSP nên chỉ nhận đúng dạng tên tài nguyên của Azure.
    patterns = {}
    if storage_backend == "blob":
        patterns |= {"AZURE_STORAGE_ACCOUNT": r"[a-z0-9]{3,24}", "AZURE_STORAGE_CONTAINER": r"[a-z0-9]([a-z0-9]|-(?!-)){1,61}[a-z0-9]"}
    if queue_backend == "servicebus":
        patterns |= {"SERVICEBUS_NAMESPACE": r"[a-z][a-z0-9-]{4,48}[a-z0-9]", "SERVICEBUS_QUEUE": r"[a-z0-9][a-z0-9._-]{0,62}"}
    for name, pattern in patterns.items():
        if not re.fullmatch(pattern, app.config.get(name) or ""):
            raise ValueError(f"{name} is missing or is not a valid Azure resource name")
    if provider == "oidc":
        if not app.config.get("OIDC_CLIENT_ID") or not https_url(app.config.get("OIDC_ISSUER")):
            raise ValueError("OIDC_ISSUER and OIDC_CLIENT_ID are required by AUTH_PROVIDER=oidc")
        for name in ["OIDC_JWKS_URL", "OIDC_AUTHORIZE_URL", "OIDC_TOKEN_URL"] + (["OIDC_LOGOUT_URL"] if app.config.get("OIDC_LOGOUT_URL") else []):
            if not https_url(app.config.get(name)):
                raise ValueError(f"{name} must be an https URL")
    if environment == "production":
        # Với Blob Storage, thư mục storage local không được dùng; thư mục tạm của worker vẫn phải riêng tư.
        for name in ["WORK_ROOT"] + (["STORAGE_ROOT"] if storage_backend == "local" else []):
            root = app.config.get(name)
            if not root or not Path(root).is_absolute():
                raise ValueError(f"Production needs an absolute {name}; local storage defaults are for development only")
            # Dữ liệu riêng tư không được nằm trong thư mục mã nguồn/static.
            if Path(root).resolve().is_relative_to(PROJECT_ROOT):
                raise ValueError(f"{name} must be outside the application directory")


def content_security_policy(config):
    """CSP của trang: chỉ cho gọi tới chính máy chủ, nhà cung cấp đăng nhập và (nếu dùng Blob Storage) đúng storage account."""
    connect, media = ["'self'"], ["'self'"]
    if config["AUTH_PROVIDER"] == "firebase":
        connect.append("https://identitytoolkit.googleapis.com")
    if config["AUTH_PROVIDER"] == "oidc" and https_url(config.get("OIDC_TOKEN_URL")):
        # Trang đổi mã đăng nhập lấy ID token bằng fetch tới token endpoint; chuyển hướng đăng nhập không cần CSP.
        connect.append("https://" + urlsplit(config["OIDC_TOKEN_URL"]).netloc)
    if config["STORAGE_BACKEND"] == "blob":
        origin = blob_origin(config.get("AZURE_STORAGE_ACCOUNT"))
        connect.append(origin)
        media.append(origin)
    policy = f"default-src 'self'; connect-src {' '.join(connect)}; "
    if len(media) > 1:
        policy += f"media-src {' '.join(media)}; img-src {' '.join(media)}; "
    return policy + "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"


def create_app(test_config=None):
    app = Flask(__name__)
    if test_config is None:
        app.config.update(load_settings())
    else:
        app.config.update(test_config)

    if app.config.get("TOKEN_VERIFIER") is not None and not app.testing:
        raise ValueError("Custom token verifiers are allowed only in tests")
    if os.getenv("FIREBASE_AUTH_EMULATOR_HOST") and not app.testing:
        raise ValueError("Auth emulator bypass is not allowed in runtime")
    if not app.testing:
        check_runtime(app)
    app.config.setdefault("STORAGE_ROOT", PROJECT_ROOT / ".local" / "objects")
    app.config.setdefault("WORK_ROOT", Path(app.config["STORAGE_ROOT"]).parent / "work")
    app.config.setdefault("AUTH_PROVIDER", "firebase")
    app.config.setdefault("STORAGE_BACKEND", "local")
    app.config.setdefault("QUEUE_BACKEND", "postgres")
    app.config.setdefault("MAX_UPLOAD_BYTES", 50_000_000)
    app.config.setdefault("MIN_FREE_BYTES", 0)
    app.config.setdefault("SESSION_HOURS", 12)
    # Thêm 1 MB cho header/khung HTTP; giới hạn thật của file do storage kiểm tra theo từng byte.
    app.config["MAX_CONTENT_LENGTH"] = app.config["MAX_UPLOAD_BYTES"] + 1_000_000

    engine = None
    if app.config.get("DATABASE_URL"):
        engine = create_engine(
            app.config["DATABASE_URL"],
            pool_pre_ping=True,
            pool_size=app.config.get("DB_POOL_SIZE", 4),
            max_overflow=app.config.get("DB_MAX_OVERFLOW", 2),
            pool_timeout=10,
            connect_args={"connect_timeout": 3},
            hide_parameters=True,
        )
    app.extensions["db_engine"] = engine

    from app.db_cli import register_commands
    register_commands(app)
    from app.pipeline_cli import register_pipeline_commands
    register_pipeline_commands(app)
    from app.admin_cli import register_admin_commands
    register_admin_commands(app)

    from app.auth import register_auth_routes
    register_auth_routes(app)
    from app.accounts import register_account_routes
    register_account_routes(app)
    from app.videos import register_video_routes
    from app.storage import RedactStorageTickets, StorageUnavailable
    register_video_routes(app)
    csp = content_security_policy(app.config)
    logger = logging.getLogger("werkzeug")
    if not any(isinstance(item, RedactStorageTickets) for item in logger.filters):
        logger.addFilter(RedactStorageTickets())

    @app.errorhandler(HTTPException)
    def http_error(error):
        if request.path.startswith(("/api/", "/local-storage/")):
            return jsonify(error=error.description, request_id=g.request_id), error.code
        return error

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        app.logger.warning("Database request failed request_id=%s", g.request_id)
        return jsonify(error="database_unavailable", request_id=g.request_id), 503

    @app.errorhandler(StorageUnavailable)
    def storage_error(error):
        app.logger.warning("Storage request failed request_id=%s", g.request_id)
        return jsonify(error="storage_unavailable", request_id=g.request_id), 503

    @app.before_request
    def assign_request_id():
        g.request_id = str(uuid4())
        g.started = time.monotonic()

    @app.after_request
    def response_headers(response):
        response.headers["X-Request-ID"] = g.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = csp
        # Chỉ ghi path, không ghi query string: ticket của signed URL không bao giờ vào log.
        access_log.info(json.dumps({
            "event": "request", "method": request.method, "path": request.path,
            "status": response.status_code, "ms": round((time.monotonic() - g.started) * 1000),
            "request_id": g.request_id, "uid": (g.get("user") or {}).get("uid"),
        }))
        return response

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/api/config")
    def public_config():
        return jsonify(auth_provider=app.config["AUTH_PROVIDER"], max_upload_bytes=app.config["MAX_UPLOAD_BYTES"], request_id=g.request_id)

    @app.get("/health")
    def health():
        db = app.extensions["db_engine"]
        if db is not None:
            try:
                with db.connect() as connection:
                    ready = connection.execute(text("SELECT 1")).scalar_one() == 1
                if ready:
                    return jsonify(status="ok", database="ok", request_id=g.request_id)
            except SQLAlchemyError:
                # Không ghi exception vì chuỗi kết nối có thể chứa thông tin bí mật.
                app.logger.warning("Database health check failed request_id=%s", g.request_id)
        return jsonify(
            status="unavailable", database="unavailable", request_id=g.request_id
        ), 503

    return app

from functools import wraps
from threading import Lock

import firebase_admin
from firebase_admin import auth
from google.auth.exceptions import DefaultCredentialsError, TransportError
from flask import abort, current_app, g, request
from sqlalchemy.orm import Session

from app.auth_local import LoginError, allow_address, login, logout, verify_local_token
from app.auth_oidc import verify_oidc_token
from app.models import Video, VideoPermission

firebase_lock = Lock()


def verify_firebase_token(token):
    project = current_app.config.get("FIREBASE_PROJECT_ID")
    if not project:
        abort(503, description="auth_not_configured")
    name = "video-portal-" + project
    with firebase_lock:
        try:
            firebase_app = firebase_admin.get_app(name)
        except ValueError:
            firebase_app = firebase_admin.initialize_app(options={"projectId": project}, name=name)
    return auth.verify_id_token(token, app=firebase_app)


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        parts = header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer" or len(parts[1]) > 8192:
            abort(401, description="authentication_required")
        verifier = current_app.config.get("TOKEN_VERIFIER")
        if verifier is None:
            provider = current_app.config.get("AUTH_PROVIDER")
            verifier = {"local": verify_local_token, "oidc": verify_oidc_token}.get(provider, verify_firebase_token)
        try:
            claims = verifier(parts[1])
        except (auth.InvalidIdTokenError, ValueError):
            abort(401, description="invalid_or_expired_token")
        except LookupError:
            abort(503, description="database_unavailable")
        except (auth.CertificateFetchError, DefaultCredentialsError, TransportError):
            abort(503, description="auth_temporarily_unavailable")
        uid = claims.get("uid")
        if not isinstance(uid, str) or not 0 < len(uid) <= 128:
            abort(401, description="invalid_identity")
        g.user = {"uid": uid, "admin": claims.get("admin") is True}
        g.token = parts[1]
        return view(*args, **kwargs)
    return wrapped


def db_session():
    engine = current_app.extensions["db_engine"]
    if engine is None:
        abort(503, description="database_unavailable")
    return Session(engine)


def authorized_video(session, video_id, owner_only=False):
    video = session.get(Video, video_id)
    if video is None:
        abort(404, description="video_not_found")
    if video.owner_uid == g.user["uid"]:
        return video
    if not owner_only and session.get(VideoPermission, (video_id, g.user["uid"])):
        return video
    abort(404, description="video_not_found")


def video_data(video):
    return {"id": str(video.id), "title": video.title, "owner_uid": video.owner_uid, "status": video.status,
            "size_bytes": video.size_bytes, "created_at": video.created_at.isoformat()}


def register_auth_routes(app):
    @app.post("/api/auth/login")
    def local_login():
        if app.config.get("AUTH_PROVIDER") != "local":
            abort(404, description="not_found")
        if not allow_address(request.remote_addr):
            abort(429, description="too_many_attempts")
        if not request.is_json or (request.content_length or 0) > 4096:
            abort(400, description="json_required")
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            abort(400, description="json_object_required")
        engine = app.extensions["db_engine"]
        if engine is None:
            abort(503, description="database_unavailable")
        try:
            token, seconds = login(engine, data.get("email"), data.get("password"), app.config["SESSION_HOURS"])
        except LoginError as error:
            abort(error.status, description=error.code)
        return {"token": token, "expires_in": seconds, "request_id": g.request_id}

    @app.post("/api/auth/logout")
    @require_auth
    def local_logout():
        if app.config.get("AUTH_PROVIDER") == "local" and app.config.get("TOKEN_VERIFIER") is None:
            logout(app.extensions["db_engine"], g.token)
        return {"status": "signed_out", "request_id": g.request_id}

    @app.get("/api/auth/config")
    def auth_config():
        if app.config.get("AUTH_PROVIDER") == "local":
            return {"provider": "local", "request_id": g.request_id}
        if app.config.get("AUTH_PROVIDER") == "oidc":
            # Địa chỉ đăng nhập và client ID là thông tin công khai của ứng dụng (public client, không có client secret).
            names = ["OIDC_CLIENT_ID", "OIDC_AUTHORIZE_URL", "OIDC_TOKEN_URL"]
            if not all(app.config.get(name) for name in names + ["OIDC_ISSUER", "OIDC_JWKS_URL"]):
                abort(503, description="auth_not_configured")
            return {"provider": "oidc", "client_id": app.config["OIDC_CLIENT_ID"], "authorize_url": app.config["OIDC_AUTHORIZE_URL"],
                    "token_url": app.config["OIDC_TOKEN_URL"], "logout_url": app.config.get("OIDC_LOGOUT_URL") or None, "request_id": g.request_id}
        key = app.config.get("FIREBASE_WEB_API_KEY")
        if not key or not app.config.get("FIREBASE_PROJECT_ID"):
            abort(503, description="auth_not_configured")
        return {"api_key": key, "request_id": g.request_id}

    @app.get("/api/me")
    @require_auth
    def me():
        return {**g.user, "request_id": g.request_id}

    @app.get("/api/videos/<uuid:video_id>")
    @require_auth
    def video_metadata(video_id):
        with db_session() as session:
            video = authorized_video(session, video_id)
            return {"video": video_data(video), "request_id": g.request_id}

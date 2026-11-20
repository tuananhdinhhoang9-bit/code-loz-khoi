"""API quản lý tài khoản nội bộ: admin tạo/khoá/đặt lại mật khẩu, người dùng tự đổi mật khẩu.

Chỉ hoạt động khi AUTH_PROVIDER=local. Quyền admin luôn được kiểm tra ở backend.
"""

from flask import abort, g, request

from app import auth_local
from app.auth import require_auth


def register_account_routes(app):
    def local_engine():
        if app.config.get("AUTH_PROVIDER") != "local":
            abort(404, description="not_found")
        engine = app.extensions["db_engine"]
        if engine is None:
            abort(503, description="database_unavailable")
        return engine

    def admin_engine():
        engine = local_engine()
        if not g.user["admin"]:
            abort(403, description="admin_required")
        return engine

    def body():
        if not request.is_json or (request.content_length or 0) > 4096:
            abort(400, description="json_required")
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            abort(400, description="json_object_required")
        return data

    def valid_email(value):
        try:
            return auth_local.normalize_uid(value)
        except ValueError:
            abort(400, description="invalid_email")

    def valid_password(value):
        try:
            auth_local.check_password_rules(value)
        except ValueError:
            abort(400, description="weak_password")
        return value

    @app.get("/api/users")
    @require_auth
    def list_users():
        return {"users": auth_local.list_users(admin_engine()), "request_id": g.request_id}

    @app.post("/api/users")
    @require_auth
    def create_user():
        engine = admin_engine()
        data = body()
        email, password = valid_email(data.get("email")), valid_password(data.get("password"))
        try:
            uid = auth_local.create_user(engine, email, password, data.get("admin") is True)
        except ValueError:
            abort(409, description="user_exists")
        return {"uid": uid, "request_id": g.request_id}, 201

    @app.post("/api/users/password")
    @require_auth
    def reset_password():
        engine = admin_engine()
        data = body()
        email, password = valid_email(data.get("email")), valid_password(data.get("password"))
        try:
            auth_local.set_password(engine, email, password)
        except ValueError:
            abort(404, description="user_not_found")
        return {"status": "password_changed", "request_id": g.request_id}

    @app.post("/api/users/active")
    @require_auth
    def set_active():
        engine = admin_engine()
        data = body()
        email, active = valid_email(data.get("email")), data.get("active")
        if not isinstance(active, bool):
            abort(400, description="invalid_active")
        # Admin không tự khoá chính mình, tránh trường hợp không còn ai đăng nhập quản trị được.
        if email == g.user["uid"] and not active:
            abort(400, description="cannot_disable_self")
        try:
            auth_local.set_active(engine, email, active)
        except ValueError:
            abort(404, description="user_not_found")
        return {"status": "enabled" if active else "disabled", "request_id": g.request_id}

    @app.post("/api/auth/password")
    @require_auth
    def change_own_password():
        engine = local_engine()
        data = body()
        new = valid_password(data.get("new_password"))
        try:
            auth_local.change_password(engine, g.user["uid"], data.get("current_password"), new)
        except auth_local.LoginError as error:
            abort(error.status, description=error.code)
        except ValueError:
            abort(400, description="password_not_changed")
        return {"status": "password_changed", "request_id": g.request_id}

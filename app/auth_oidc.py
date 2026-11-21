"""Xác minh ID token OIDC (Microsoft Entra External ID) bằng khoá công khai (JWKS) của nhà cung cấp."""

from threading import Lock

import jwt
from flask import abort, current_app
from jwt.exceptions import PyJWKClientConnectionError, PyJWTError

clients = {}
clients_lock = Lock()


def jwks_client(url):
    # PyJWKClient tự nhớ bộ khoá; mỗi địa chỉ JWKS chỉ cần một client cho cả tiến trình.
    with clients_lock:
        if url not in clients:
            clients[url] = jwt.PyJWKClient(url, timeout=5)
        return clients[url]


def verify_oidc_token(token):
    config = current_app.config
    issuer, audience, jwks_url = config.get("OIDC_ISSUER"), config.get("OIDC_CLIENT_ID"), config.get("OIDC_JWKS_URL")
    if not issuer or not audience or not jwks_url:
        abort(503, description="auth_not_configured")
    try:
        key = jwks_client(jwks_url).get_signing_key_from_jwt(token).key
        # Chỉ nhận RS256: token tự ký bằng HS256 hoặc "none" bị từ chối. `aud` phải là chính ứng dụng này,
        # nên access token cấp cho API khác không dùng làm danh tính được.
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=audience, issuer=issuer,
                            options={"require": ["exp", "iat", "iss", "aud"]})
    except PyJWKClientConnectionError:
        abort(503, description="auth_temporarily_unavailable")
    except PyJWTError:
        raise ValueError("invalid token") from None
    # Danh tính trong hệ thống là e-mail (quyền xem video được cấp theo e-mail).
    # Tenant phải bắt xác minh e-mail khi đăng ký; nếu token có `email_verified` thì nó phải là true.
    email = claims.get(config.get("OIDC_EMAIL_CLAIM") or "email")
    if not isinstance(email, str) or "@" not in email or claims.get("email_verified", True) is not True:
        raise ValueError("invalid token")
    roles = claims.get("roles")
    admin_role = config.get("OIDC_ADMIN_ROLE") or "admin"
    return {"uid": email.strip().lower(), "admin": isinstance(roles, list) and admin_role in roles}

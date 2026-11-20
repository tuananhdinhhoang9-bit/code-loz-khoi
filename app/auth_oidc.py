"""Xác minh ID token OIDC của Amazon Cognito bằng khoá công khai (JWKS) của user pool."""

from threading import Lock

import jwt
from flask import abort, current_app
from jwt.exceptions import PyJWKClientConnectionError, PyJWTError

clients = {}
clients_lock = Lock()


def jwks_client(issuer):
    # PyJWKClient tự nhớ bộ khoá; mỗi issuer chỉ cần một client cho cả tiến trình.
    with clients_lock:
        if issuer not in clients:
            clients[issuer] = jwt.PyJWKClient(issuer + "/.well-known/jwks.json", timeout=5)
        return clients[issuer]


def verify_oidc_token(token):
    issuer = current_app.config.get("OIDC_ISSUER")
    audience = current_app.config.get("OIDC_CLIENT_ID")
    if not issuer or not audience:
        abort(503, description="auth_not_configured")
    try:
        key = jwks_client(issuer).get_signing_key_from_jwt(token).key
        # Chỉ nhận RS256: token tự ký bằng HS256 hoặc "none" bị từ chối.
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=audience, issuer=issuer,
                            options={"require": ["exp", "iat", "iss", "aud"]})
    except PyJWKClientConnectionError:
        abort(503, description="auth_temporarily_unavailable")
    except PyJWTError:
        raise ValueError("invalid token") from None
    # Access token của Cognito không được dùng làm danh tính; email phải do Cognito xác nhận.
    email = claims.get("email")
    if claims.get("token_use") != "id" or claims.get("email_verified") is not True or not isinstance(email, str):
        raise ValueError("invalid token")
    groups = claims.get("cognito:groups")
    admin_group = current_app.config.get("OIDC_ADMIN_GROUP", "admin")
    return {"uid": email.strip().lower(), "admin": isinstance(groups, list) and admin_group in groups}

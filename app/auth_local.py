"""Tài khoản nội bộ lưu trong PostgreSQL (AUTH_PROVIDER=local), không phụ thuộc dịch vụ ngoài."""

from collections import deque
from datetime import timedelta
import hashlib
import re
import secrets
from threading import Lock
import time

from flask import current_app
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import AuthSession, User

MAX_FAILURES = 5
LOCK_MINUTES = 15
MIN_PASSWORD = 12
IP_ATTEMPTS = 20
IP_WINDOW_SECONDS = 300
EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,62}")
ip_lock = Lock()
ip_attempts = {}
dummy_hash = None


class LoginError(Exception):
    def __init__(self, code, status):
        super().__init__(code)
        self.code = code
        self.status = status


def normalize_uid(email):
    uid = email.strip().lower() if isinstance(email, str) else ""
    if not EMAIL.fullmatch(uid):
        raise ValueError("Email is not valid")
    return uid


def check_password_rules(password):
    if not isinstance(password, str) or not MIN_PASSWORD <= len(password) <= 256:
        raise ValueError(f"Password must have {MIN_PASSWORD} to 256 characters")


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(engine, email, password, admin=False):
    uid = normalize_uid(email)
    check_password_rules(password)
    with Session(engine) as session, session.begin():
        if session.get(User, uid) is not None:
            raise ValueError("User already exists")
        session.add(User(uid=uid, password_hash=generate_password_hash(password, method="scrypt"), is_admin=admin))
    return uid


def set_password(engine, email, password):
    uid = normalize_uid(email)
    check_password_rules(password)
    with Session(engine) as session, session.begin():
        user = session.get(User, uid, with_for_update=True)
        if user is None:
            raise ValueError("User does not exist")
        user.password_hash = generate_password_hash(password, method="scrypt")
        user.failed_logins, user.locked_until = 0, None
        # Đổi mật khẩu thì mọi phiên cũ phải mất hiệu lực.
        session.execute(delete(AuthSession).where(AuthSession.uid == uid))


def set_active(engine, email, active):
    uid = normalize_uid(email)
    with Session(engine) as session, session.begin():
        user = session.get(User, uid, with_for_update=True)
        if user is None:
            raise ValueError("User does not exist")
        user.is_active = active
        if not active:
            session.execute(delete(AuthSession).where(AuthSession.uid == uid))


def list_users(engine):
    with Session(engine) as session:
        now = session.scalar(select(func.clock_timestamp()))
        users = session.scalars(select(User).order_by(User.created_at)).all()
        return [{"uid": user.uid, "admin": user.is_admin, "active": user.is_active,
                 "locked": bool(user.locked_until and user.locked_until > now),
                 "created_at": user.created_at.isoformat()} for user in users]


def change_password(engine, uid, current, new):
    """Người dùng tự đổi mật khẩu: phải biết mật khẩu hiện tại; mọi phiên cũ bị thu hồi."""
    check_password_rules(new)
    with Session(engine) as session:
        user = session.get(User, uid)
        known = user.password_hash if user else None
    if known is None or not isinstance(current, str) or len(current) > 256 or not check_password_hash(known, current):
        raise LoginError("invalid_credentials", 401)
    set_password(engine, uid, new)


def allow_address(address, now=None):
    """Giới hạn số lần thử đăng nhập theo IP trong bộ nhớ của tiến trình API."""
    now = now or time.monotonic()
    with ip_lock:
        if len(ip_attempts) > 10_000:
            ip_attempts.clear()
        attempts = ip_attempts.setdefault(address or "unknown", deque())
        while attempts and attempts[0] <= now - IP_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= IP_ATTEMPTS:
            return False
        attempts.append(now)
        return True


def login(engine, email, password, hours=12):
    global dummy_hash
    try:
        uid = normalize_uid(email)
    except ValueError:
        raise LoginError("invalid_credentials", 401) from None
    if not isinstance(password, str) or len(password) > 256:
        raise LoginError("invalid_credentials", 401)
    token = None
    with Session(engine) as session, session.begin():
        now = session.scalar(select(func.clock_timestamp()))
        user = session.get(User, uid, with_for_update=True)
        if user is None:
            # Vẫn băm một lần để thời gian phản hồi không tiết lộ email nào tồn tại.
            dummy_hash = dummy_hash or generate_password_hash(secrets.token_urlsafe(16), method="scrypt")
            check_password_hash(dummy_hash, password)
            code = "invalid_credentials"
        elif user.locked_until and user.locked_until > now:
            code = "too_many_attempts"
        elif user.is_active and check_password_hash(user.password_hash, password):
            code = None
            user.failed_logins, user.locked_until = 0, None
            token = secrets.token_urlsafe(32)
            session.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
            session.add(AuthSession(token_hash=token_hash(token), uid=uid, created_at=now, expires_at=now + timedelta(hours=hours)))
        else:
            code = "invalid_credentials"
            user.failed_logins += 1
            if user.failed_logins >= MAX_FAILURES:
                user.failed_logins = 0
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
    # Ra khỏi transaction rồi mới báo lỗi để bộ đếm đăng nhập sai được commit.
    if code:
        raise LoginError(code, 429 if code == "too_many_attempts" else 401)
    return token, hours * 3600


def verify_local_token(token):
    engine = current_app.extensions["db_engine"]
    if engine is None:
        raise LookupError("database_unavailable")
    with Session(engine) as session:
        row = session.execute(
            select(User.uid, User.is_admin).join(AuthSession, AuthSession.uid == User.uid)
            .where(AuthSession.token_hash == token_hash(token), AuthSession.expires_at > func.clock_timestamp(), User.is_active.is_(True))
        ).first()
    if row is None:
        raise ValueError("invalid session")
    return {"uid": row.uid, "admin": row.is_admin}


def logout(engine, token):
    with Session(engine) as session, session.begin():
        session.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token)))

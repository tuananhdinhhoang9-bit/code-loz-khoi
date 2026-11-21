"""Client HTTP nhỏ dùng chung cho smoke_test.py và seed_remote.py (chỉ dùng thư viện chuẩn).

Biết đăng nhập theo hai kiểu của portal (tài khoản nội bộ, hoặc ID token OIDC lấy sẵn) và gửi file theo đúng
cách máy chủ yêu cầu: PUT lên portal (storage local) hoặc PUT lên URL có SAS của Azure Blob Storage.
"""

import json
import os
import re
import socket
import ssl
import urllib.error
import urllib.request


class Client:
    def __init__(self, base_url, insecure=False):
        self.base = base_url.rstrip("/")
        self.context = ssl._create_unverified_context() if insecure else None
        self.token = ""

    def call(self, method, path, body=None, headers=None, auth=True, raw=False):
        url = path if path.startswith("http") else self.base + path
        headers = dict(headers or {})
        if auth and self.token:
            headers["Authorization"] = "Bearer " + self.token
        if body is not None and not isinstance(body, bytes):
            body = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=600, context=self.context)
        except urllib.error.HTTPError as error:
            response = error
        data = response.read()
        if raw:
            return response.status, data, response.headers
        try:
            return response.status, json.loads(data), response.headers
        except ValueError:
            return response.status, {}, response.headers


def resolve_host(mapping):
    """`ten-mien=IP`: kết nối tới IP đó nhưng vẫn dùng đúng tên miền cho TLS và header Host.

    Dùng để kiểm thử một bản triển khai mới trước khi đổi DNS của tên miền.
    """
    host, address = mapping.split("=", 1)
    original = socket.getaddrinfo

    def lookup(name, *args, **kwargs):
        return original(address if name == host else name, *args, **kwargs)

    socket.getaddrinfo = lookup


def sign_in(client, email, password):
    """Trả token để gửi kèm `Authorization: Bearer`, hoặc None nếu email/mật khẩu bị từ chối."""
    status, config, _ = client.call("GET", "/api/auth/config", auth=False)
    if status != 200:
        raise RuntimeError(f"/api/auth/config returned HTTP {status}")
    if config.get("provider") == "local":
        status, session, _ = client.call("POST", "/api/auth/login", {"email": email, "password": password}, auth=False)
        return session.get("token") if status == 200 else None
    if config.get("provider") == "oidc":
        # Đăng nhập OIDC cần trình duyệt (chuyển hướng + PKCE), script không tự làm được: người chạy đăng nhập
        # trên trang rồi đưa ID token vào biến môi trường. Token không đi qua dòng lệnh nên không nằm trong lịch sử shell.
        token = os.getenv("PORTAL_ID_TOKEN", "").strip()
        if not token:
            raise RuntimeError("This portal signs in through an OIDC redirect; put a valid ID token in PORTAL_ID_TOKEN")
        return token
    raise RuntimeError("This script supports the local and oidc sign-in providers only")


def upload(client, created, content, mime_type):
    """Gửi file tới nơi `POST /api/videos` chỉ định, kèm các header máy chủ yêu cầu. Trả (được nhận hay không, mã HTTP)."""
    headers = created.get("upload_headers") or {"Content-Type": mime_type}
    # Không gửi token của portal tới storage: URL ký sẵn (ticket hoặc SAS) là quyền duy nhất.
    status, _, _ = client.call("PUT", created["upload_url"], content, headers, auth=False, raw=True)
    return status == 201, status


def tampered(url):
    """Cùng URL nhưng chữ ký bị sửa: storage phải từ chối."""
    if re.search(r"[?&]sig=", url):
        return re.sub(r"([?&])sig=[^&]+", r"\1sig=" + "A" * 43 + "%3D", url)
    return url[:-6] + "AAAAAA"
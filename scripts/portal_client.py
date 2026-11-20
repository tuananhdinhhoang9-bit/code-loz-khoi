"""Client HTTP nhỏ dùng chung cho smoke_test.py và seed_remote.py (chỉ dùng thư viện chuẩn).

Biết đăng nhập theo hai kiểu của portal (tài khoản nội bộ hoặc Amazon Cognito) và gửi file theo đúng
cách máy chủ yêu cầu: PUT thẳng lên portal (storage local) hoặc form POST ký sẵn lên S3.
"""

import json
import re
import socket
import ssl
import urllib.error
import urllib.request
from uuid import uuid4


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

    Dùng để kiểm thử bản AWS qua load balancer trước khi đổi DNS của tên miền.
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
    if config.get("provider") == "cognito":
        # Giống trang web: mật khẩu đi thẳng tới Cognito, portal chỉ nhận ID token.
        body = json.dumps({"AuthFlow": "USER_PASSWORD_AUTH", "ClientId": config["client_id"],
                           "AuthParameters": {"USERNAME": email, "PASSWORD": password}}).encode()
        headers = {"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth"}
        status, result, _ = client.call("POST", f"https://cognito-idp.{config['region']}.amazonaws.com/", body, headers, auth=False)
        return (result.get("AuthenticationResult") or {}).get("IdToken") if status == 200 else None
    raise RuntimeError("This script supports the local and cognito sign-in providers only")


def encode_form(fields, content):
    """Thân multipart/form-data cho S3: các trường đã ký đứng trước, file đứng cuối cùng."""
    boundary = uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode() for name, value in fields.items()]
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="upload"\r\n'
                 f"Content-Type: application/octet-stream\r\n\r\n".encode() + content + f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def upload(client, created, content, mime_type):
    """Gửi file tới nơi `POST /api/videos` chỉ định. Trả (được nhận hay không, mã HTTP)."""
    if created.get("upload_method") == "POST":
        body, content_type = encode_form(created["upload_fields"], content)
        status, _, _ = client.call("POST", created["upload_url"], body, {"Content-Type": content_type}, auth=False, raw=True)
        return status == 204, status
    status, _, _ = client.call("PUT", created["upload_url"], content, {"Content-Type": mime_type}, auth=False, raw=True)
    return status == 201, status


def tampered(url):
    """Cùng URL nhưng chữ ký bị sửa: storage phải từ chối."""
    if "X-Amz-Signature=" in url:
        return re.sub(r"X-Amz-Signature=[0-9a-f]+", "X-Amz-Signature=" + "0" * 64, url)
    return url[:-6] + "AAAAAA"

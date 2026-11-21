import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
from threading import Lock
from uuid import uuid4

from flask import abort, current_app
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException

MAX_BYTES = 50_000_000
URL_TTL = 120
storage_lock = Lock()
# Tên object do server sinh ra: chỉ chữ, số, '.', '_', '-' và phân cách bằng '/'.
OBJECT_NAME = re.compile(r"(inputs|outputs)(/[A-Za-z0-9][A-Za-z0-9._-]{0,99}){1,6}")
WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL"} | {f"{name}{number}" for name in ("COM", "LPT") for number in range(1, 10)}


class StorageFull(HTTPException):
    code = 507
    description = "storage_full"


def blob_origin(account):
    """Địa chỉ trình duyệt dùng để tải lên/phát trực tiếp từ Blob Storage (cần cho CSP và CORS)."""
    return f"https://{account}.blob.core.windows.net"


class StorageUnavailable(OSError):
    """Storage tạm thời không dùng được (ví dụ Blob Storage lỗi mạng): API trả 503, worker coi là lỗi thử lại được."""


class RedactStorageTickets(logging.Filter):
    def filter(self, record):
        record.msg = re.sub(r"ticket=[^&\s\"']+", "ticket=[redacted]", record.getMessage())
        record.args = ()
        return True


def file_generation(path):
    # Băm theo khối để file lớn không bị nạp hết vào RAM.
    with Path(path).open("rb") as stream:
        return "local-sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


class LocalStorage:
    def __init__(self, root, key=None, max_bytes=MAX_BYTES, min_free_bytes=0):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes
        self.min_free_bytes = min_free_bytes
        self.verified = {}
        if key is None:
            key_path = self.root / ".signing-key"
            temporary_key = self.root / (".signing-key." + uuid4().hex + ".tmp")
            try:
                with temporary_key.open("x", encoding="ascii") as stream:
                    stream.write(secrets.token_urlsafe(48))
                try:
                    os.link(temporary_key, key_path)
                except FileExistsError:
                    pass
            finally:
                temporary_key.unlink(missing_ok=True)
            key = key_path.read_text(encoding="ascii")
            if len(key) < 32:
                raise ValueError("Local storage signing key is invalid")
        self.signer = URLSafeTimedSerializer(key, salt="video-portal-local-storage-v1")

    def path(self, name):
        if not isinstance(name, str) or not OBJECT_NAME.fullmatch(name):
            abort(404, description="object_not_found")
        parts = name.split("/")
        if any(part.split(".")[0].upper() in WINDOWS_DEVICES or part.endswith(".") for part in parts):
            abort(404, description="object_not_found")
        plain = self.root.joinpath(*parts)
        # Không đi qua symlink/junction: link trong storage có thể trỏ ra ngoài thư mục riêng tư.
        for part in [plain, *plain.parents]:
            if part == self.root:
                break
            if part.is_symlink() or part.is_junction():
                abort(404, description="object_not_found")
        path = plain.resolve()
        if self.root not in path.parents:
            abort(404, description="object_not_found")
        return path

    def signed_url(self, operation, **values):
        ticket = self.signer.dumps({"operation": operation, **values})
        return f"/local-storage/{operation}?ticket={ticket}"

    def upload_target(self, video_id, name, mime_type, size_limit):
        """Nơi trình duyệt gửi file gốc và các header phải gửi kèm; BlobStorage trả cùng dạng với URL có SAS."""
        url = self.signed_url("upload", video_id=video_id, name=name, mime_type=mime_type, size_limit=size_limit)
        return {"upload_url": url, "upload_method": "PUT", "upload_headers": {"Content-Type": mime_type}}

    def read_url(self, name, generation, mime_type):
        return self.signed_url("read", name=name, generation=generation, mime_type=mime_type)

    def verify(self, ticket, operation):
        try:
            data = self.signer.loads(ticket, max_age=URL_TTL)
        except BadSignature:
            abort(403, description="invalid_or_expired_storage_ticket")
        if not isinstance(data, dict) or data.get("operation") != operation:
            abort(403, description="invalid_storage_operation")
        return data

    def free_bytes(self):
        return shutil.disk_usage(self.root).free

    def ensure_space(self, size):
        if self.min_free_bytes and self.free_bytes() < size + self.min_free_bytes:
            raise StorageFull()

    def write(self, name, stream, mime_type, size_limit):
        path = self.path(name)
        limit = min(self.max_bytes, size_limit)
        self.ensure_space(limit)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary.open("xb") as target:
                while chunk := stream.read(64 * 1024):
                    size += len(chunk)
                    if size > limit:
                        abort(413, description="upload_too_large")
                    digest.update(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            if size == 0:
                abort(400, description="empty_upload")
            try:
                # Hard link là thao tác nguyên tử và không ghi đè object đã có.
                os.link(temporary, path)
            except FileExistsError:
                abort(409, description="object_already_uploaded")
            metadata = {"size_bytes": size, "mime_type": mime_type, "generation": "local-sha256:" + digest.hexdigest()}
            path.with_name(path.name + ".metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        finally:
            temporary.unlink(missing_ok=True)

    def head(self, name):
        path = self.path(name)
        try:
            metadata = json.loads(path.with_name(path.name + ".metadata.json").read_text(encoding="utf-8"))
            state = path.stat()
            if state.st_size != metadata["size_bytes"]:
                abort(409, description="object_changed")
            # File local là private và chỉ ghi một lần; kiểm tra lại phiên bản khi truy cập.
            # Kết quả băm được nhớ theo (kích thước, thời điểm sửa) để phát Range không băm lại cả file.
            seen = (state.st_size, state.st_mtime_ns, metadata["generation"])
            if self.verified.get(name) != seen:
                if file_generation(path) != metadata["generation"]:
                    abort(409, description="object_changed")
                if len(self.verified) > 2000:
                    self.verified.clear()
                self.verified[name] = seen
            return metadata
        except (OSError, ValueError, KeyError):
            abort(409, description="object_not_ready")

    def delete(self, name):
        """Xoá một object và metadata của nó; không báo lỗi nếu object đã mất."""
        path = self.path(name)
        self.verified.pop(name, None)
        path.unlink(missing_ok=True)
        path.with_name(path.name + ".metadata.json").unlink(missing_ok=True)
        for folder in path.parents:
            if folder == self.root or folder.parent == self.root:
                break
            try:
                folder.rmdir()
            except OSError:
                break


def storage():
    app = current_app
    with storage_lock:
        if "storage" not in app.extensions and app.config.get("STORAGE_BACKEND") == "blob":
            from app.storage_blob import BlobStorage, blob_service
            account = app.config["AZURE_STORAGE_ACCOUNT"]
            app.extensions["storage"] = BlobStorage(account, app.config["AZURE_STORAGE_CONTAINER"], blob_service(account),
                                                    app.config.get("MAX_UPLOAD_BYTES", MAX_BYTES))
        if "storage" not in app.extensions:
            app.extensions["storage"] = LocalStorage(
                app.config["STORAGE_ROOT"], app.config.get("STORAGE_SIGNING_KEY"),
                app.config.get("MAX_UPLOAD_BYTES", MAX_BYTES), app.config.get("MIN_FREE_BYTES", 0),
            )
    return app.extensions["storage"]

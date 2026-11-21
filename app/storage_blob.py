"""Storage riêng tư trên Azure Blob Storage, cùng giao diện với LocalStorage (ADR-024).

Trình duyệt tải lên và phát video bằng URL có SAS sống URL_TTL giây; container không có quyền công khai.
SAS được ký bằng user delegation key (lấy bằng managed identity), không dùng account key.
Storage account phải bật versioning: version ID của blob nguồn chính là `source_generation` của job.
"""

from datetime import datetime, timedelta, timezone
import logging
from threading import Lock
from urllib.parse import quote

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.storage.blob import BlobSasPermissions, BlobServiceClient, ContentSettings, generate_blob_sas
from flask import abort

from app.storage import MAX_BYTES, OBJECT_NAME, URL_TTL, StorageUnavailable, blob_origin

KEY_HOURS = 1
logger = logging.getLogger(__name__)


def blob_service(account):
    # DefaultAzureCredential dùng managed identity trên Azure (AZURE_CLIENT_ID chọn identity); không có khoá nào trong cấu hình.
    from azure.identity import DefaultAzureCredential
    return BlobServiceClient(blob_origin(account), credential=DefaultAzureCredential(), connection_timeout=5, read_timeout=60)


class BlobStorage:
    def __init__(self, account, container, service, max_bytes=MAX_BYTES):
        self.account = account
        self.container = container
        self.service = service
        self.max_bytes = max_bytes
        self.delegation = None
        self.lock = Lock()

    def key(self, name):
        if not isinstance(name, str) or not OBJECT_NAME.fullmatch(name):
            abort(404, description="object_not_found")
        return name

    def call(self, label, action):
        """Gọi Blob Storage. Blob không tồn tại -> None; lỗi khác -> StorageUnavailable (API trả 503, worker thử lại)."""
        try:
            return action()
        except ResourceNotFoundError:
            return None
        except AzureError as error:
            # Chỉ ghi tên thao tác và loại lỗi: không ghi tên blob, URL hay thông tin xác thực.
            logger.warning("blob %s failed type=%s", label, type(error).__name__)
            raise StorageUnavailable("blob_request_failed") from None

    def blob(self, name, version=None):
        return self.service.get_blob_client(self.container, self.key(name), version_id=version)

    def delegation_key(self):
        """Khoá ký SAS do Azure cấp cho identity của ứng dụng; nhớ lại và xin mới trước khi hết hạn."""
        now = datetime.now(timezone.utc)
        with self.lock:
            if self.delegation is None or self.delegation[1] - now < timedelta(minutes=10):
                expires = now + timedelta(hours=KEY_HOURS)
                key = self.call("get_user_delegation_key", lambda: self.service.get_user_delegation_key(now - timedelta(minutes=5), expires))
                if key is None:
                    raise StorageUnavailable("blob_signing_failed")
                self.delegation = (key, expires)
            return self.delegation[0]

    def signed_url(self, name, permission, version=None, content_type=None):
        now = datetime.now(timezone.utc)
        token = generate_blob_sas(
            self.account, self.container, self.key(name), user_delegation_key=self.delegation_key(), permission=permission,
            # Lùi giờ bắt đầu vài phút để lệch đồng hồ giữa máy chủ và Azure không làm URL "chưa có hiệu lực".
            start=now - timedelta(minutes=5), expiry=now + timedelta(seconds=URL_TTL), protocol="https",
            version_id=version, content_type=content_type,
        )
        # SAS của một phiên bản (sr=bv) chỉ hợp lệ khi URL nêu đúng phiên bản đó.
        pinned = f"versionid={quote(version, safe='')}&" if version else ""
        return f"{blob_origin(self.account)}/{self.container}/{quote(name)}?{pinned}{token}"

    def free_bytes(self):
        return None

    def ensure_space(self, size):
        """Blob Storage không có dung lượng cố định; giới hạn nằm ở kích thước từng file."""

    def upload_target(self, video_id, name, mime_type, size_limit):
        # Quyền "create": tạo đúng blob này một lần, không ghi đè được blob đã có.
        # SAS không giới hạn được kích thước hay Content-Type; `complete` đọc lại blob và kiểm tra cả hai.
        url = self.signed_url(name, BlobSasPermissions(create=True))
        headers = {"x-ms-blob-type": "BlockBlob", "x-ms-blob-content-type": mime_type, "Content-Type": mime_type}
        return {"upload_url": url, "upload_method": "PUT", "upload_headers": headers}

    def read_url(self, name, generation, mime_type):
        # Ký đúng phiên bản đã kiểm tra: blob bị ghi đè sau đó cũng không đổi nội dung được phát.
        return self.signed_url(name, BlobSasPermissions(read=True), version=generation, content_type=mime_type)

    def head(self, name):
        properties = self.call("get_blob_properties", self.blob(name).get_blob_properties)
        if properties is None:
            abort(409, description="object_not_ready")
        if not properties.version_id:
            logger.error("blob versioning is not enabled on the storage account")
            raise StorageUnavailable("blob_versioning_disabled")
        return {"size_bytes": properties.size, "mime_type": properties.content_settings.content_type or "", "generation": properties.version_id}

    def download(self, name, generation, target):
        """Chép đúng phiên bản `generation` của blob về file `target` (file chưa được tồn tại)."""
        downloader = self.call("download_blob", self.blob(name, generation).download_blob)
        if downloader is None:
            abort(409, description="object_changed")
        try:
            with open(target, "xb") as stream:
                for chunk in downloader.chunks():
                    stream.write(chunk)
        except AzureError:
            raise StorageUnavailable("blob_download_failed") from None

    def write(self, name, stream, mime_type, size_limit):
        size = stream.seek(0, 2)
        stream.seek(0)
        if size == 0:
            abort(400, description="empty_upload")
        if size > min(self.max_bytes, size_limit):
            abort(413, description="upload_too_large")
        client = self.blob(name)
        self.call("upload_blob", lambda: client.upload_blob(stream, length=size, overwrite=True, content_settings=ContentSettings(content_type=mime_type)))

    def delete(self, name):
        """Xoá mọi phiên bản của blob. Có versioning nên xoá thường chỉ biến bản hiện tại thành bản cũ."""
        key = self.key(name)
        self.call("delete_blob", self.blob(key).delete_blob)
        container = self.service.get_container_client(self.container)
        versions = self.call("list_blobs", lambda: [item.version_id for item in container.list_blobs(name_starts_with=key, include=["versions"]) if item.name == key])
        for version in versions or []:
            self.call("delete_blob", self.blob(key, version).delete_blob)

    def old_objects(self, prefix, cutoff):
        """Tên các blob dưới `prefix` được ghi trước thời điểm `cutoff` (datetime có múi giờ)."""
        container = self.service.get_container_client(self.container)
        blobs = self.call("list_blobs", lambda: list(container.list_blobs(name_starts_with=prefix)))
        for item in blobs or []:
            if item.last_modified < cutoff:
                yield item.name

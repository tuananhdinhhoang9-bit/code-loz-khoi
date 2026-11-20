"""Storage riêng tư trên Amazon S3, cùng giao diện với LocalStorage (ADR-021).

Trình duyệt tải lên và phát video bằng URL ký sẵn sống URL_TTL giây; bucket không có quyền công khai.
Bucket phải bật versioning: VersionId của object nguồn chính là `source_generation` của job.
"""

import logging

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from flask import abort

from app.storage import MAX_BYTES, OBJECT_NAME, URL_TTL, StorageUnavailable

MISSING = {"404", "NoSuchKey", "NoSuchVersion", "NotFound"}
logger = logging.getLogger(__name__)


def s3_client(region):
    # Endpoint theo region + SigV4: URL ký sẵn trỏ thẳng tới bucket, trình duyệt không bị chuyển hướng.
    return boto3.client(
        "s3", region_name=region, endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"},
                      connect_timeout=5, read_timeout=60, retries={"max_attempts": 3}),
    )


class S3Storage:
    def __init__(self, bucket, client, max_bytes=MAX_BYTES):
        self.bucket = bucket
        self.client = client
        self.max_bytes = max_bytes

    def key(self, name):
        if not isinstance(name, str) or not OBJECT_NAME.fullmatch(name):
            abort(404, description="object_not_found")
        return name

    def call(self, operation, **values):
        """Gọi S3. Object không tồn tại -> None; lỗi khác -> StorageUnavailable (API trả 503, worker thử lại)."""
        try:
            return getattr(self.client, operation)(Bucket=self.bucket, **values)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code in MISSING:
                return None
            # Chỉ ghi tên thao tác và mã lỗi: không ghi tên object, URL hay thông tin xác thực.
            logger.warning("s3 %s failed code=%s", operation, code)
            raise StorageUnavailable("s3_request_failed") from None
        except BotoCoreError as error:
            logger.warning("s3 %s failed type=%s", operation, type(error).__name__)
            raise StorageUnavailable("s3_request_failed") from None

    def presign(self, method, *args, **values):
        try:
            return getattr(self.client, method)(*args, ExpiresIn=URL_TTL, **values)
        except BotoCoreError as error:
            logger.warning("s3 %s failed type=%s", method, type(error).__name__)
            raise StorageUnavailable("s3_signing_failed") from None

    def free_bytes(self):
        return None

    def ensure_space(self, size):
        """S3 không có dung lượng cố định; giới hạn nằm ở kích thước từng file."""

    def upload_target(self, video_id, name, mime_type, size_limit):
        # Presigned POST: S3 tự từ chối file sai Content-Type hoặc lớn hơn giới hạn đã ký.
        limit = min(self.max_bytes, size_limit)
        form = self.presign(
            "generate_presigned_post", self.bucket, self.key(name), Fields={"Content-Type": mime_type},
            Conditions=[{"Content-Type": mime_type}, ["content-length-range", 1, limit]],
        )
        return {"upload_url": form["url"], "upload_method": "POST", "upload_fields": form["fields"]}

    def read_url(self, name, generation, mime_type):
        # Ký đúng VersionId đã kiểm tra: object bị ghi đè sau đó cũng không đổi nội dung được phát.
        return self.presign("generate_presigned_url", "get_object", Params={
            "Bucket": self.bucket, "Key": self.key(name), "VersionId": generation, "ResponseContentType": mime_type})

    def head(self, name):
        response = self.call("head_object", Key=self.key(name))
        if response is None:
            abort(409, description="object_not_ready")
        version = response.get("VersionId")
        if not version or version == "null":
            logger.error("s3 bucket versioning is not enabled")
            raise StorageUnavailable("s3_versioning_disabled")
        return {"size_bytes": response["ContentLength"], "mime_type": response.get("ContentType", ""), "generation": version}

    def download(self, name, generation, target):
        """Chép đúng phiên bản `generation` của object về file `target` (file chưa được tồn tại)."""
        response = self.call("get_object", Key=self.key(name), VersionId=generation)
        if response is None:
            abort(409, description="object_changed")
        try:
            with open(target, "xb") as stream:
                for chunk in response["Body"].iter_chunks(64 * 1024):
                    stream.write(chunk)
        except BotoCoreError:
            raise StorageUnavailable("s3_download_failed") from None

    def write(self, name, stream, mime_type, size_limit):
        size = stream.seek(0, 2)
        stream.seek(0)
        if size == 0:
            abort(400, description="empty_upload")
        if size > min(self.max_bytes, size_limit):
            abort(413, description="upload_too_large")
        self.call("put_object", Key=self.key(name), Body=stream, ContentType=mime_type, ContentLength=size)

    def delete(self, name):
        """Xoá mọi phiên bản của object. Bucket có versioning nên xoá thường chỉ thêm delete marker."""
        key = self.key(name)
        listing = self.call("list_object_versions", Prefix=key) or {}
        for item in listing.get("Versions", []) + listing.get("DeleteMarkers", []):
            if item["Key"] == key:
                self.call("delete_object", Key=key, VersionId=item["VersionId"])

    def old_objects(self, prefix, cutoff):
        """Tên các object dưới `prefix` được ghi trước thời điểm `cutoff` (datetime có múi giờ)."""
        token = {}
        while True:
            page = self.call("list_objects_v2", Prefix=prefix, **token) or {}
            for item in page.get("Contents", []):
                if item["LastModified"] < cutoff:
                    yield item["Key"]
            if not page.get("NextContinuationToken"):
                return
            token = {"ContinuationToken": page["NextContinuationToken"]}

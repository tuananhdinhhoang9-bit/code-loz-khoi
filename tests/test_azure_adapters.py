"""Phase 07 (Azure) — kiểm thử adapter Blob Storage, Service Bus và xác minh token OIDC mà KHÔNG gọi Azure.

Ba loại kiểm thử, không loại nào là bằng chứng về một hệ thống Azure đang chạy:
- SDK thật + lớp vận chuyển giả (Recorder): request HTTP do azure-storage-blob tạo ra được đối chiếu từng cái,
  SAS được sinh thật (ngoại tuyến) bằng khoá giả.
- FakeBlobService / FakeBus trong bộ nhớ: chạy luồng API/worker đầy đủ với PostgreSQL và FFmpeg thật.
- Chữ ký hàm của SDK đã cài được đối chiếu với cách mã nguồn gọi chúng.
"""

import base64
from datetime import datetime, timedelta, timezone
import inspect
import io
import json
import shutil
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError, ServiceRequestError
from azure.core.pipeline.transport import HttpResponse, HttpTransport
from azure.core.utils import CaseInsensitiveDict
from azure.servicebus import ServiceBusClient, ServiceBusReceiver, ServiceBusSender
from azure.servicebus.exceptions import ServiceBusError
from azure.storage.blob import BlobClient, BlobServiceClient, ContainerClient, UserDelegationKey
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from jwt.exceptions import PyJWKClientConnectionError
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.exceptions import HTTPException

from app import admin_cli, auth_oidc
from app.main import create_app
from app.maintenance import cleanup_outputs, cleanup_uploads
from app.models import OutboxEvent, OutputObject, OutputProfile, TranscodeJob, Video
from app.pipeline import dispatch_one, relay
from app.queue_local import QueueError
from app.queue_pg import PgBroker, make_broker
from app.queue_servicebus import ServiceBusBroker
from app.storage import StorageUnavailable, blob_origin, storage
from app.storage_blob import BlobStorage
from app.worker_service import run_once
from worker.transcode import transcode

ACCOUNT = "videoportaltest"
CONTAINER = "media"
ORIGIN = f"https://{ACCOUNT}.blob.core.windows.net"
NAMESPACE = "video-portal-test"
QUEUE = "transcode-jobs"
LOGIN = "https://tenant.ciamlogin.example"
ISSUER = LOGIN + "/11111111-2222-3333-4444-555555555555/v2.0"
CLIENT_ID = "test-app-client"
OIDC = {"OIDC_ISSUER": ISSUER, "OIDC_CLIENT_ID": CLIENT_ID, "OIDC_JWKS_URL": LOGIN + "/discovery/v2.0/keys",
        "OIDC_AUTHORIZE_URL": LOGIN + "/oauth2/v2.0/authorize", "OIDC_TOKEN_URL": LOGIN + "/oauth2/v2.0/token"}
VERSION = "2026-11-21T05:00:00.0000001Z"
KEY_VALUE = base64.b64encode(b"test-only-delegation-key-value-32").decode()
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="Real FFmpeg/ffprobe required")


def delegation_key():
    """Khoá giả chỉ để SDK ký SAS ngoại tuyến; Azure thật cấp khoá này cho managed identity."""
    key = UserDelegationKey()
    key.signed_oid, key.signed_tid = "00000000-0000-0000-0000-0000000000aa", "00000000-0000-0000-0000-0000000000bb"
    key.signed_start, key.signed_expiry = "2026-11-21T00:00:00Z", "2026-11-21T01:00:00Z"
    key.signed_service, key.signed_version, key.value = "b", "2025-01-05", KEY_VALUE
    return key


# ---------- Blob Storage giả trong bộ nhớ ----------

class FakeBlobService:
    """Blob Storage có versioning trong bộ nhớ, chỉ đủ cho các thao tác BlobStorage dùng. Không phải bằng chứng về Azure."""

    def __init__(self, versioning=True):
        self.blobs = {}  # tên -> danh sách phiên bản, phiên bản hiện tại (nếu có) đứng cuối và có current=True
        self.versioning = versioning
        self.count = 0
        self.key_requests = 0
        self.fail = None

    def check(self):
        if self.fail is not None:
            raise self.fail

    def get_user_delegation_key(self, key_start_time, key_expiry_time):
        self.check()
        self.key_requests += 1
        return delegation_key()

    def get_blob_client(self, container, blob, snapshot=None, *, version_id=None):
        assert container == CONTAINER
        return FakeBlobClient(self, blob, version_id)

    def get_container_client(self, container):
        assert container == CONTAINER
        return FakeContainer(self)

    def put(self, name, data, content_type):
        """Mô phỏng một lần ghi blob (trình duyệt PUT bằng SAS, hoặc ai đó ghi đè)."""
        self.count += 1
        for item in self.blobs.setdefault(name, []):
            item["current"] = False
        self.blobs[name].append({"version_id": f"version-{self.count:04d}", "data": data, "content_type": content_type,
                                 "last_modified": datetime.now(timezone.utc), "current": True})
        return self.blobs[name][-1]["version_id"]


class FakeBlobClient:
    def __init__(self, service, name, version_id):
        self.service, self.name, self.version_id = service, name, version_id

    def find(self):
        self.service.check()
        for item in self.service.blobs.get(self.name, []):
            if item["version_id"] == self.version_id or (self.version_id is None and item["current"]):
                return item
        raise ResourceNotFoundError("BlobNotFound")

    def get_blob_properties(self):
        item = self.find()
        return SimpleNamespace(name=self.name, size=len(item["data"]), content_settings=SimpleNamespace(content_type=item["content_type"]),
                               version_id=item["version_id"] if self.service.versioning else None, last_modified=item["last_modified"])

    def upload_blob(self, data, length=None, overwrite=False, content_settings=None):
        self.service.check()
        content = data.read()
        assert length == len(content) and overwrite is True
        self.service.put(self.name, content, content_settings.content_type)

    def download_blob(self):
        data = self.find()["data"]
        return SimpleNamespace(chunks=lambda: iter([data[:5], data[5:]]))

    def delete_blob(self):
        item = self.find()
        if self.version_id is None:
            item["current"] = False  # có versioning: bản hiện tại chỉ trở thành bản cũ
            return
        # Mô hình thận trọng: chỉ xoá được phiên bản cũ theo ID, nên mã nguồn phải xoá blob hiện tại trước.
        assert item["current"] is False
        self.service.blobs[self.name].remove(item)
        if not self.service.blobs[self.name]:
            del self.service.blobs[self.name]


class FakeContainer:
    def __init__(self, service):
        self.service = service

    def list_blobs(self, name_starts_with=None, include=None):
        self.service.check()
        versions = "versions" in (include or [])
        for name, items in sorted(self.service.blobs.items()):
            for item in items:
                if name.startswith(name_starts_with or "") and (versions or item["current"]):
                    yield SimpleNamespace(name=name, version_id=item["version_id"], last_modified=item["last_modified"])


@pytest.fixture
def blob():
    service = FakeBlobService()
    return BlobStorage(ACCOUNT, CONTAINER, service, max_bytes=1000), service


# ---------- Blob Storage: SAS (sinh thật, ngoại tuyến) ----------

def sas(url):
    parts = urlsplit(url)
    return parts, {name: values[0] for name, values in parse_qs(parts.query).items()}


def test_blob_upload_target_is_a_short_create_only_sas_for_one_blob(blob):
    store, service = blob
    target = store.upload_target("video-1", "inputs/video-1/source", "video/mp4", 500)
    assert target["upload_method"] == "PUT"
    assert target["upload_headers"] == {"x-ms-blob-type": "BlockBlob", "x-ms-blob-content-type": "video/mp4", "Content-Type": "video/mp4"}
    parts, query = sas(target["upload_url"])
    assert parts.scheme == "https" and parts.netloc == f"{ACCOUNT}.blob.core.windows.net" and parts.path == f"/{CONTAINER}/inputs/video-1/source"
    # Quyền "c" (create) trên đúng một blob (sr=b), chỉ qua HTTPS, ký bằng user delegation key (skoid), không phải account key.
    assert query["sp"] == "c" and query["sr"] == "b" and query["spr"] == "https" and query["skoid"] and "sig" in query
    remaining = datetime.fromisoformat(query["se"].replace("Z", "+00:00")) - datetime.now(timezone.utc)
    assert timedelta(seconds=60) < remaining <= timedelta(seconds=121)
    assert datetime.fromisoformat(query["st"].replace("Z", "+00:00")) < datetime.now(timezone.utc)
    assert KEY_VALUE not in json.dumps(target) and "versionid" not in query
    # Khoá ký được nhớ lại: URL thứ hai không hỏi Azure thêm lần nào.
    store.upload_target("video-2", "inputs/video-2/source", "video/webm", 500)
    assert service.key_requests == 1
    store.delegation = (store.delegation[0], datetime.now(timezone.utc) + timedelta(minutes=5))
    store.upload_target("video-3", "inputs/video-3/source", "video/mp4", 500)
    assert service.key_requests == 2  # khoá sắp hết hạn thì xin khoá mới


def test_blob_read_url_pins_the_version_and_expires(blob):
    store, _ = blob
    parts, query = sas(store.read_url("outputs/job/attempt/video.mp4", VERSION, "video/mp4"))
    assert parts.netloc == f"{ACCOUNT}.blob.core.windows.net" and parts.path == f"/{CONTAINER}/outputs/job/attempt/video.mp4"
    # sr=bv: chữ ký chỉ hợp lệ cho đúng phiên bản nêu trong URL; rsct ép Content-Type của phản hồi.
    assert query["versionid"] == VERSION and query["sr"] == "bv" and query["sp"] == "r" and query["rsct"] == "video/mp4"
    remaining = datetime.fromisoformat(query["se"].replace("Z", "+00:00")) - datetime.now(timezone.utc)
    assert timedelta(seconds=60) < remaining <= timedelta(seconds=121)
    other = sas(store.read_url("outputs/job/attempt/video.mp4", "2026-11-21T06:00:00.0000001Z", "video/mp4"))[1]
    assert other["sig"] != query["sig"]


def test_blob_signing_failure_is_storage_unavailable(blob):
    store, service = blob
    service.fail = HttpResponseError("AuthorizationPermissionMismatch")
    with pytest.raises(StorageUnavailable):
        store.upload_target("video-1", "inputs/video-1/source", "video/mp4", 500)


@pytest.mark.parametrize("name", ["../secret", "outputs/../inputs/x", "other/file", "inputs/", "inputs/a b", "", None, "inputs/" + "a/" * 7 + "x"])
def test_blob_rejects_names_outside_the_private_layout(blob, name):
    store, _ = blob
    for action in [lambda: store.head(name), lambda: store.delete(name), lambda: store.read_url(name, "v", "video/mp4"),
                   lambda: store.upload_target("v", name, "video/mp4", 10)]:
        with pytest.raises(HTTPException) as error:
            action()
        assert error.value.code == 404


# ---------- Blob Storage: thao tác trên blob giả ----------

def test_blob_head_reports_version_and_missing_or_unversioned_blobs(blob):
    store, service = blob
    with pytest.raises(HTTPException) as error:
        store.head("inputs/v/source")
    assert error.value.code == 409 and error.value.description == "object_not_ready"
    version = service.put("inputs/v/source", b"12345678", "video/mp4")
    assert store.head("inputs/v/source") == {"size_bytes": 8, "mime_type": "video/mp4", "generation": version}
    # Storage account chưa bật versioning: không có version ID thì không xác định được phiên bản nguồn.
    service.versioning = False
    with pytest.raises(StorageUnavailable):
        store.head("inputs/v/source")
    service.versioning, service.fail = True, ServiceRequestError("network down")
    with pytest.raises(StorageUnavailable):
        store.head("inputs/v/source")


def test_blob_write_checks_size_before_sending(blob):
    store, service = blob
    store.write("outputs/job/attempt/video.mp4", io.BytesIO(b"12345"), "video/mp4", 100)
    assert service.blobs["outputs/job/attempt/video.mp4"][-1]["data"] == b"12345"
    for content, limit, status in [(b"", 100, 400), (b"123456", 5, 413), (b"x" * 1001, 5000, 413)]:
        with pytest.raises(HTTPException) as error:
            store.write("outputs/job/attempt/other.mp4", io.BytesIO(content), "video/mp4", limit)
        assert error.value.code == status
    assert "outputs/job/attempt/other.mp4" not in service.blobs


def test_blob_download_fetches_the_exact_version(blob, tmp_path):
    store, service = blob
    first = service.put("inputs/v/source", b"source-bytes", "video/mp4")
    service.put("inputs/v/source", b"overwritten later", "video/mp4")
    store.download("inputs/v/source", first, tmp_path / "source")
    assert (tmp_path / "source").read_bytes() == b"source-bytes"
    with pytest.raises(HTTPException) as error:
        store.download("inputs/v/source", "version-9999", tmp_path / "second")
    assert error.value.code == 409 and not (tmp_path / "second").exists()
    service.fail = HttpResponseError("ServerBusy")
    with pytest.raises(OSError):
        store.download("inputs/v/source", first, tmp_path / "third")


def test_blob_delete_removes_every_version_of_only_that_blob(blob):
    store, service = blob
    for content in [b"one", b"two", b"three"]:
        service.put("inputs/v/source", content, "video/mp4")
    service.put("inputs/v/source-other", b"keep", "video/mp4")
    store.delete("inputs/v/source")
    assert list(service.blobs) == ["inputs/v/source-other"] and service.blobs["inputs/v/source-other"][0]["current"]
    store.delete("inputs/v/source")  # đã mất: không báo lỗi


def test_blob_old_objects_lists_only_current_blobs_older_than_the_cutoff(blob):
    store, service = blob
    now = datetime.now(timezone.utc)
    for name in ["outputs/a/b/video.mp4", "outputs/c/d/video.mp4", "outputs/e/f/thumbnail.jpg", "inputs/x/y"]:
        service.put(name, b"data", "video/mp4")
    for name in ["outputs/a/b/video.mp4", "outputs/e/f/thumbnail.jpg", "inputs/x/y"]:
        service.blobs[name][-1]["last_modified"] = now - timedelta(days=2)
    assert list(store.old_objects("outputs/", now - timedelta(days=1))) == ["outputs/a/b/video.mp4", "outputs/e/f/thumbnail.jpg"]


# ---------- Blob Storage: SDK thật với lớp vận chuyển giả (đối chiếu request HTTP) ----------

class Reply(HttpResponse):
    def __init__(self, request, status, headers, content):
        super().__init__(request, None)
        self.status_code, self.reason, self.content = status, "test", content
        self.headers = CaseInsensitiveDict({"x-ms-request-id": "request-1", "Date": "Sat, 21 Nov 2026 05:00:00 GMT", **headers})
        self.content_type = self.headers.get("Content-Type")

    def body(self):
        return self.content


class Recorder(HttpTransport):
    """Ghi lại request mà SDK định gửi và trả lời theo kịch bản; không mở kết nối mạng."""

    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    def send(self, request, **kwargs):
        self.requests.append(request)
        status, headers, content = self.replies.pop(0)
        return Reply(request, status, headers, content)

    def open(self):
        pass

    def close(self):
        pass

    def __exit__(self, *args):
        pass


BLOB_HEADERS = {"Content-Length": "8", "Content-Type": "video/mp4", "x-ms-version-id": VERSION, "x-ms-blob-type": "BlockBlob",
                "Last-Modified": "Sat, 21 Nov 2026 05:00:00 GMT", "ETag": '"0x1"'}


def listed(*blobs):
    items = "".join(
        f"<Blob><Name>{name}</Name><VersionId>{version}</VersionId><Properties><Last-Modified>{modified}</Last-Modified><Etag>0x1</Etag>"
        "<Content-Length>8</Content-Length><Content-Type>video/mp4</Content-Type><BlobType>BlockBlob</BlobType></Properties></Blob>"
        for name, version, modified in blobs)
    body = f'<?xml version="1.0" encoding="utf-8"?><EnumerationResults ContainerName="{CONTAINER}"><Blobs>{items}</Blobs><NextMarker /></EnumerationResults>'
    return 200, {"Content-Type": "application/xml"}, body.encode()


def real_store(replies):
    transport = Recorder(replies)
    service = BlobServiceClient(ORIGIN, credential=None, transport=transport, retry_total=0)
    return BlobStorage(ACCOUNT, CONTAINER, service, max_bytes=1000), transport


def test_real_sdk_head_and_write_requests():
    store, transport = real_store([(200, BLOB_HEADERS, b""), (404, {"x-ms-error-code": "BlobNotFound"}, b""),
                                   (201, {"x-ms-version-id": "v2", "ETag": '"0x2"', "Last-Modified": "Sat, 21 Nov 2026 05:00:00 GMT"}, b""),
                                   (403, {"x-ms-error-code": "AuthorizationPermissionMismatch"}, b"")])
    assert store.head("inputs/v/source") == {"size_bytes": 8, "mime_type": "video/mp4", "generation": VERSION}
    with pytest.raises(HTTPException) as error:
        store.head("inputs/v/source")
    assert error.value.code == 409
    store.write("outputs/job/attempt/video.mp4", io.BytesIO(b"12345"), "video/mp4", 100)
    with pytest.raises(StorageUnavailable):
        store.head("inputs/v/source")
    head, _, put, _ = transport.requests
    assert (head.method, head.url) == ("HEAD", f"{ORIGIN}/{CONTAINER}/inputs/v/source")
    assert (put.method, put.url) == ("PUT", f"{ORIGIN}/{CONTAINER}/outputs/job/attempt/video.mp4")
    assert put.headers["x-ms-blob-type"] == "BlockBlob" and put.headers["x-ms-blob-content-type"] == "video/mp4" and put.headers["Content-Length"] == "5"
    assert transport.replies == []


def test_real_sdk_delete_and_listing_requests():
    old = "Thu, 19 Nov 2026 05:00:00 GMT"
    store, transport = real_store([
        (202, {}, b""), listed(("inputs/v/source", VERSION, old), ("inputs/v/source-other", "2026-11-21T05:00:01.0000001Z", old)), (202, {}, b""),
        listed(("outputs/a/b/video.mp4", VERSION, old), ("outputs/c/d/video.mp4", VERSION, "Sat, 21 Nov 2026 05:00:00 GMT")),
    ])
    store.delete("inputs/v/source")
    first, listing, second = transport.requests
    assert (first.method, first.url) == ("DELETE", f"{ORIGIN}/{CONTAINER}/inputs/v/source")
    assert listing.method == "GET" and parse_qs(urlsplit(listing.url).query) == {
        "restype": ["container"], "comp": ["list"], "prefix": ["inputs/v/source"], "include": ["versions"]}
    # Chỉ phiên bản của đúng blob đó bị xoá; blob có tên bắt đầu giống thì không.
    assert second.method == "DELETE" and urlsplit(second.url).path == f"/{CONTAINER}/inputs/v/source"
    assert parse_qs(urlsplit(second.url).query) == {"versionid": [VERSION]}
    cutoff = datetime(2026, 11, 20, tzinfo=timezone.utc)
    assert list(store.old_objects("outputs/", cutoff)) == ["outputs/a/b/video.mp4"]
    assert "include" not in parse_qs(urlsplit(transport.requests[3].url).query) and transport.replies == []


def test_calls_match_the_installed_sdk_signatures():
    """Fake không biết SDK thật nhận tham số nào: đối chiếu cách gọi trong mã nguồn với chữ ký của SDK đã cài."""
    def accepts(function, *args, **kwargs):
        inspect.signature(function).bind(None, *args, **kwargs)

    now = datetime.now(timezone.utc)
    accepts(BlobServiceClient.get_blob_client, CONTAINER, "inputs/v/source", version_id=VERSION)
    accepts(BlobServiceClient.get_user_delegation_key, now, now)
    accepts(BlobServiceClient.get_container_client, CONTAINER)
    accepts(ContainerClient.list_blobs, name_starts_with="outputs/", include=["versions"])
    accepts(BlobClient.upload_blob, io.BytesIO(b"x"), length=1, overwrite=True, content_settings=None)
    accepts(BlobClient.download_blob)
    accepts(BlobClient.delete_blob)
    accepts(BlobClient.get_blob_properties)
    accepts(ServiceBusClient.get_queue_sender, QUEUE)
    accepts(ServiceBusClient.get_queue_receiver, QUEUE)
    accepts(ServiceBusSender.send_messages, object())
    accepts(ServiceBusReceiver.receive_messages, max_message_count=1, max_wait_time=2)
    accepts(ServiceBusReceiver.complete_message, object())
    accepts(ServiceBusReceiver.dead_letter_message, object(), reason="invalid_job_message")
    accepts(ServiceBusReceiver.renew_message_lock, object())


# ---------- Service Bus giả ----------

class FakeBus:
    """Queue peek-lock trong bộ nhớ, chỉ đủ cho các thao tác ServiceBusBroker dùng. Không phải bằng chứng về Azure."""

    def __init__(self):
        self.queue, self.dead = [], []
        self.completed, self.renewed, self.closed = 0, 0, 0
        self.opened = {"sender": 0, "receiver": 0}
        self.fail = set()

    def check(self, operation):
        if operation in self.fail:
            raise ServiceBusError("simulated failure")

    def get_queue_sender(self, queue_name):
        assert queue_name == QUEUE
        self.opened["sender"] += 1
        return FakeLink(self)

    def get_queue_receiver(self, queue_name):
        assert queue_name == QUEUE
        self.opened["receiver"] += 1
        return FakeLink(self)

    def close(self):
        self.closed += 1

    def expire_locks(self):
        """Mô phỏng khoá hết hạn (worker chết): message hiện lại để được giao lần nữa."""
        for message in self.queue:
            message.locked = False


class FakeMessage:
    def __init__(self, body, message_id=None):
        self.text, self.message_id, self.delivery_count, self.locked = body, message_id, 0, False

    def __str__(self):
        return self.text


class FakeLink:
    def __init__(self, bus):
        self.bus = bus

    def send_messages(self, message):
        self.bus.check("send")
        # `message` là ServiceBusMessage thật của SDK: đọc thân và message_id từ chính nó.
        self.bus.queue.append(FakeMessage(str(message), message.message_id))

    def receive_messages(self, max_message_count=1, max_wait_time=None):
        self.bus.check("receive")
        for message in self.bus.queue:
            if not message.locked:
                message.locked = True
                message.delivery_count += 1
                return [message]
        return []

    def complete_message(self, message):
        self.bus.check("complete")
        self.bus.queue.remove(message)
        self.bus.completed += 1

    def dead_letter_message(self, message, reason=None, error_description=None):
        self.bus.check("dead_letter")
        self.bus.queue.remove(message)
        self.bus.dead.append((str(message), reason))

    def renew_message_lock(self, message):
        self.bus.check("renew")
        self.bus.renewed += 1

    def close(self):
        pass


@pytest.fixture
def bus():
    fake = FakeBus()
    return ServiceBusBroker(fake, QUEUE), fake


def test_servicebus_publish_receive_and_ack(bus):
    broker, fake = bus
    key, payload = uuid4(), {"job_id": str(uuid4()), "source_generation": VERSION, "profile_id": str(uuid4())}
    broker.publish(key, payload)
    broker.publish(uuid4(), payload)
    assert fake.opened["sender"] == 1  # một sender dùng lại cho mọi lần gửi
    # message_id là khoá thao tác của event: gửi lại cùng event thì message mang cùng ID.
    assert fake.queue[0].message_id == str(key) and json.loads(str(fake.queue[0])) == {"operation_key": str(key), "payload": payload}
    delivery = broker.receive()
    assert delivery["operation_key"] == str(key) and delivery["payload"] == payload and delivery["deliveries"] == 1
    broker.ack(delivery)
    assert fake.completed == 1 and len(fake.queue) == 1
    broker.ack(broker.receive())
    assert broker.receive() is None and fake.opened["receiver"] == 1


def test_servicebus_unacked_message_is_delivered_again(bus):
    broker, fake = bus
    broker.publish(uuid4(), {"job_id": "x"})
    first = broker.receive()
    assert broker.receive() is None  # đang bị khoá bởi lần nhận trước
    fake.expire_locks()
    again = broker.receive()
    assert again["operation_key"] == first["operation_key"] and again["deliveries"] == 2


def test_servicebus_failures_become_queue_errors_and_limits_hold(bus):
    broker, fake = bus
    with pytest.raises(QueueError, match="message_too_large"):
        broker.publish(uuid4(), {"padding": "x" * 5000})
    with pytest.raises(ValueError):
        broker.publish("not-a-uuid", {})
    assert fake.queue == []
    fake.fail = {"send"}
    with pytest.raises(QueueError):
        broker.publish(uuid4(), {"job_id": "x"})
    fake.fail = set()
    broker.publish(uuid4(), {"job_id": "x"})
    assert fake.opened["sender"] == 2  # sau lỗi, kết nối cũ bị bỏ và mở lại
    fake.fail = {"receive"}
    with pytest.raises(QueueError):
        broker.receive()
    fake.fail = set()
    delivery = broker.receive()
    fake.fail = {"complete"}
    with pytest.raises(QueueError):
        broker.ack(delivery)
    # Receiver đã bị bỏ sau lỗi: ack bằng khoá cũ không được lặng lẽ coi là thành công.
    fake.fail = set()
    with pytest.raises(QueueError):
        broker.ack(delivery)


def test_servicebus_invalid_message_goes_to_the_dead_letter_queue(bus, tmp_path):
    broker, fake = bus
    fake.queue.append(FakeMessage("this is not json"))
    # Message hỏng bị loại trước khi chạm DB hay storage, nên không cần engine/store thật ở đây.
    assert dispatch_one(None, broker, None, tmp_path) == "dead_letter"
    assert fake.dead == [("this is not json", "invalid_job_message")] and fake.queue == []


def test_servicebus_heartbeat_renews_the_lock_only_when_due(bus):
    broker, fake = bus
    broker.publish(uuid4(), {"job_id": "x"})
    delivery = broker.receive()
    broker.extend(delivery)  # vừa nhận xong: chưa cần gọi Service Bus
    assert fake.renewed == 0
    delivery["extended_at"] -= 25
    broker.extend(delivery)
    assert fake.renewed == 1 and time.monotonic() - delivery["extended_at"] < 5
    delivery["extended_at"] -= 25
    fake.fail = {"renew"}
    broker.extend(delivery)  # lỗi gia hạn không được làm hỏng job đang chạy
    assert fake.renewed == 1


def test_servicebus_close_releases_the_client(bus):
    broker, fake = bus
    broker.publish(uuid4(), {"job_id": "x"})
    broker.close()
    assert fake.closed == 1 and broker.sender is None and broker.receiver is None


# ---------- OIDC (Microsoft Entra External ID) ----------

@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def oidc(monkeypatch, signing_key):
    """App dùng AUTH_PROVIDER=oidc; khoá JWKS được thay bằng khoá công khai của cặp khoá test."""
    asked = []

    def fake_jwks(url):
        asked.append(url)
        return SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=signing_key.public_key()))
    monkeypatch.setattr(auth_oidc, "jwks_client", fake_jwks)
    app = create_app({"TESTING": True, "AUTH_PROVIDER": "oidc", **OIDC})
    app.extensions["jwks_urls"] = asked
    return app.test_client()


def id_token(key, algorithm="RS256", **changes):
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": str(uuid4()), "email": "Owner@Example.com", "iat": now, "exp": now + 600, **changes}
    return jwt.encode({name: value for name, value in claims.items() if value is not None}, key, algorithm=algorithm, headers={"kid": "test-key"})


def me(client, token):
    return client.get("/api/me", headers={"Authorization": "Bearer " + token})


def test_oidc_id_token_gives_email_identity_and_admin_role(oidc, signing_key):
    user = me(oidc, id_token(signing_key))
    assert user.status_code == 200 and user.json["uid"] == "owner@example.com" and user.json["admin"] is False
    assert oidc.application.extensions["jwks_urls"] == [OIDC["OIDC_JWKS_URL"]]
    admin = me(oidc, id_token(signing_key, roles=["viewer", "admin"]))
    assert admin.json["admin"] is True
    assert me(oidc, id_token(signing_key, roles="admin")).json["admin"] is False
    assert me(oidc, id_token(signing_key, email_verified=True)).status_code == 200


@pytest.mark.parametrize("changes", [
    {"aud": "another-app-client"}, {"iss": ISSUER + "-other"}, {"exp": int(time.time()) - 60}, {"exp": None}, {"iat": None},
    {"email_verified": False}, {"email_verified": "true"}, {"email": None}, {"email": 42}, {"email": "not-an-address"},
])
def test_oidc_rejects_wrong_or_incomplete_tokens(oidc, signing_key, changes):
    response = me(oidc, id_token(signing_key, **changes))
    assert response.status_code == 401 and response.json["error"] == "invalid_or_expired_token"


def test_oidc_rejects_other_keys_algorithms_and_garbage(oidc, signing_key):
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = [id_token(stranger), id_token("shared-secret-that-is-long-enough-for-hs256", algorithm="HS256"), "not.a.token", "x" * 40]
    assert [me(oidc, token).status_code for token in forged] == [401, 401, 401, 401]
    assert oidc.get("/api/me").status_code == 401


def test_oidc_email_claim_and_admin_role_names_are_configuration(monkeypatch, signing_key):
    fake_jwks = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=signing_key.public_key()))
    monkeypatch.setattr(auth_oidc, "jwks_client", lambda url: fake_jwks)
    app = create_app({"TESTING": True, "AUTH_PROVIDER": "oidc", **OIDC, "OIDC_EMAIL_CLAIM": "preferred_username", "OIDC_ADMIN_ROLE": "portal-admin"})
    client = app.test_client()
    user = me(client, id_token(signing_key, email=None, preferred_username="Viewer@Example.com", roles=["portal-admin"]))
    assert user.json["uid"] == "viewer@example.com" and user.json["admin"] is True
    assert me(client, id_token(signing_key, roles=["admin"])).status_code == 401  # không có claim đã cấu hình


def test_oidc_key_lookup_failures_fail_closed(monkeypatch, signing_key):
    def unreachable(url):
        return SimpleNamespace(get_signing_key_from_jwt=lambda token: (_ for _ in ()).throw(PyJWKClientConnectionError("down")))
    monkeypatch.setattr(auth_oidc, "jwks_client", unreachable)
    app = create_app({"TESTING": True, "AUTH_PROVIDER": "oidc", **OIDC})
    response = me(app.test_client(), id_token(signing_key))
    assert response.status_code == 503 and response.json["error"] == "auth_temporarily_unavailable"
    unconfigured = create_app({"TESTING": True, "AUTH_PROVIDER": "oidc"}).test_client()
    assert me(unconfigured, id_token(signing_key)).status_code == 503
    assert unconfigured.get("/api/auth/config").status_code == 503


def test_oidc_public_config_and_page_policy(oidc):
    config = oidc.get("/api/auth/config").json
    config.pop("request_id")
    assert config == {"provider": "oidc", "client_id": CLIENT_ID, "authorize_url": OIDC["OIDC_AUTHORIZE_URL"],
                      "token_url": OIDC["OIDC_TOKEN_URL"], "logout_url": None}
    assert oidc.get("/api/config").json["auth_provider"] == "oidc"
    assert oidc.post("/api/auth/login", json={"email": "a@example.com", "password": "x"}).status_code == 404
    policy = oidc.get("/").headers["Content-Security-Policy"]
    assert f"connect-src 'self' {LOGIN};" in policy and "identitytoolkit" not in policy


# ---------- Cấu hình ----------

def azure_settings(tmp_path):
    return {"WORK_ROOT": tmp_path / "work", "AUTH_PROVIDER": "oidc", "STORAGE_BACKEND": "blob", "QUEUE_BACKEND": "servicebus",
            "AZURE_STORAGE_ACCOUNT": ACCOUNT, "AZURE_STORAGE_CONTAINER": CONTAINER, "SERVICEBUS_NAMESPACE": NAMESPACE, "SERVICEBUS_QUEUE": QUEUE, **OIDC}


def test_azure_production_configuration_is_validated(monkeypatch, tmp_path):
    for name in ["FIREBASE_AUTH_EMULATOR_HOST", "K_SERVICE"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    good = azure_settings(tmp_path)
    app = create_app(dict(good))  # không cần STORAGE_ROOT khi file nằm trên Blob Storage
    client = app.test_client()
    policy = client.get("/").headers["Content-Security-Policy"]
    assert blob_origin(ACCOUNT) == ORIGIN
    assert f"connect-src 'self' {LOGIN} {ORIGIN};" in policy
    assert f"media-src 'self' {ORIGIN};" in policy and f"img-src 'self' {ORIGIN};" in policy
    # Với Blob Storage trình duyệt nói chuyện thẳng với Azure: hai route storage local không tồn tại.
    assert client.put("/local-storage/upload?ticket=x", data=b"x").status_code == 404
    assert client.get("/local-storage/read?ticket=x").status_code == 404
    # Tạo client của SDK không mở kết nối nào; chỉ kiểm tra đúng loại adapter được chọn.
    with app.app_context():
        assert isinstance(storage(), BlobStorage) and storage().account == ACCOUNT and storage().container == CONTAINER
    broker = make_broker(app, None)
    assert isinstance(broker, ServiceBusBroker) and broker.queue == QUEUE
    broker.close()
    bad_settings = [
        {**good, "AZURE_STORAGE_ACCOUNT": ""}, {**good, "AZURE_STORAGE_CONTAINER": ""}, {**good, "SERVICEBUS_NAMESPACE": ""}, {**good, "SERVICEBUS_QUEUE": ""},
        {**good, "OIDC_CLIENT_ID": ""}, {**good, "OIDC_ISSUER": ""}, {**good, "OIDC_JWKS_URL": ""}, {**good, "OIDC_TOKEN_URL": ""}, {**good, "OIDC_AUTHORIZE_URL": ""},
        {**good, "STORAGE_BACKEND": "s3"}, {**good, "QUEUE_BACKEND": "sqs"}, {**good, "AUTH_PROVIDER": "cognito"},
        {**good, "AZURE_STORAGE_ACCOUNT": "Has.Dots"}, {**good, "AZURE_STORAGE_ACCOUNT": "evil.example.com/x"}, {**good, "AZURE_STORAGE_CONTAINER": "a/../b"},
        {**good, "SERVICEBUS_NAMESPACE": "evil.example.com"}, {**good, "OIDC_TOKEN_URL": "http://login.example/token"},
        {**good, "OIDC_TOKEN_URL": "https://login.example/token; script-src *"}, {**good, "OIDC_ISSUER": "https://user@login.example/v2.0"},
        {**good, "OIDC_LOGOUT_URL": "javascript:alert(1)"},
        {**good, "WORK_ROOT": "relative/work"}, {name: value for name, value in good.items() if name != "WORK_ROOT"},
    ]
    for bad in bad_settings:
        with pytest.raises(ValueError):
            create_app(bad)
    with_logout = create_app({**good, "OIDC_LOGOUT_URL": LOGIN + "/oauth2/v2.0/logout"}).test_client()
    assert with_logout.get("/api/auth/config").json["logout_url"] == LOGIN + "/oauth2/v2.0/logout"


def test_azure_settings_come_from_environment_and_local_stays_default(monkeypatch, tmp_path):
    for name in ["FIREBASE_AUTH_EMULATOR_HOST", "K_SERVICE", "VIDEO_PORTAL_ENV_FILE", "APP_ENV"]:
        monkeypatch.delenv(name, raising=False)
    local = create_app({"TESTING": True})
    assert local.config["STORAGE_BACKEND"] == "local" and local.config["QUEUE_BACKEND"] == "postgres"
    assert isinstance(make_broker(local, None), PgBroker)
    assert "media-src" not in local.test_client().get("/").headers["Content-Security-Policy"]
    for name, value in {"AUTH_PROVIDER": "OIDC", "STORAGE_BACKEND": "Blob", "QUEUE_BACKEND": "servicebus", "AZURE_STORAGE_ACCOUNT": ACCOUNT,
                        "AZURE_STORAGE_CONTAINER": CONTAINER, "SERVICEBUS_NAMESPACE": NAMESPACE, "SERVICEBUS_QUEUE": QUEUE,
                        "WORK_ROOT": str(tmp_path / "work"), **OIDC}.items():
        monkeypatch.setenv(name, value)
    app = create_app()
    assert app.config["OIDC_ISSUER"] == ISSUER and app.config["OIDC_CLIENT_ID"] == CLIENT_ID
    assert app.config["STORAGE_BACKEND"] == "blob" and app.config["AUTH_PROVIDER"] == "oidc"
    assert app.config["OIDC_EMAIL_CLAIM"] == "email" and app.config["OIDC_ADMIN_ROLE"] == "admin"


# ---------- Luồng đầy đủ với Blob Storage và Service Bus giả (PostgreSQL thật) ----------

@pytest.fixture
def cloud(schema_engine):
    def verifier(token):
        if token not in {"owner", "viewer", "stranger", "admin"}:
            raise ValueError("invalid")
        return {"uid": token, "admin": token == "admin"}
    app = create_app({"TESTING": True, "TOKEN_VERIFIER": verifier, "STORAGE_BACKEND": "blob", "QUEUE_BACKEND": "servicebus",
                      "AZURE_STORAGE_ACCOUNT": ACCOUNT, "AZURE_STORAGE_CONTAINER": CONTAINER, "MAX_UPLOAD_BYTES": 1000})
    app.extensions["db_engine"] = schema_engine
    service, fake_bus = FakeBlobService(), FakeBus()
    app.extensions["storage"] = BlobStorage(ACCOUNT, CONTAINER, service, 50_000_000)
    app.extensions["broker"] = ServiceBusBroker(fake_bus, QUEUE, renew_seconds=0)
    with Session(schema_engine) as session, session.begin():
        session.add(OutputProfile(name="mp4-480p"))
    return SimpleNamespace(app=app, client=app.test_client(), engine=schema_engine, blobs=service, bus=fake_bus,
                           store=app.extensions["storage"], broker=app.extensions["broker"])


def headers(uid="owner"):
    return {"Authorization": "Bearer " + uid}


def test_portal_upload_complete_playback_and_delete_with_blob_storage(cloud):
    client, service = cloud.client, cloud.blobs
    created = client.post("/api/videos", headers=headers(), json={"title": "Cloud clip", "mime_type": "video/mp4", "size_bytes": 8})
    assert created.status_code == 201 and created.json["upload_method"] == "PUT" and created.json["expires_in"] == 120
    assert created.json["upload_headers"]["x-ms-blob-type"] == "BlockBlob"
    parts, query = sas(created.json["upload_url"])
    key = parts.path.removeprefix(f"/{CONTAINER}/")
    assert key.startswith("inputs/" + created.json["video_id"] + "/") and query["sp"] == "c"
    path = "/api/videos/" + created.json["video_id"]
    assert client.post(path + "/complete", headers=headers()).status_code == 409  # chưa có blob
    service.put(key, b"1234", "video/mp4")
    assert client.post(path + "/complete", headers=headers()).status_code == 400  # sai kích thước đã khai báo
    service.put(key, b"12345678", "text/plain")
    assert client.post(path + "/complete", headers=headers()).status_code == 400  # sai Content-Type
    service.put(key, b"12345678", "video/mp4")
    assert client.post(path + "/complete", headers=headers("stranger")).status_code == 404
    first = client.post(path + "/complete", headers=headers())
    assert first.status_code == 202
    assert client.post(path + "/complete", headers=headers()).json["job_id"] == first.json["job_id"]
    with Session(cloud.engine) as session:
        job = session.scalar(select(TranscodeJob))
        # source_generation là version ID của đúng lần upload được chấp nhận.
        assert job.source_generation == service.blobs[key][-1]["version_id"]
        event = session.scalar(select(OutboxEvent))
        assert event.payload_json["source_generation"] == job.source_generation
        # API đã gửi event sang Service Bus ngay sau khi commit, đúng một message dù `complete` được gọi hai lần.
        assert event.published_at is not None and len(cloud.bus.queue) == 1 and cloud.bus.queue[0].message_id == str(event.id)
        job_id = job.id
    listed_videos = client.get("/api/videos", headers=headers()).get_data(as_text=True)
    assert "inputs/" not in listed_videos and "blob.core.windows.net" not in listed_videos
    assert client.get(path + "/playback", headers=headers()).status_code == 409

    store = cloud.store
    with Session(cloud.engine) as session, session.begin():
        job = session.get(TranscodeJob, job_id)
        session.get(Video, job.video_id).status = job.status = "READY"
        for kind, content, mime in [("mp4", b"ready-mp4", "video/mp4"), ("thumbnail", b"ready-jpg", "image/jpeg")]:
            name = f"outputs/{job.id.hex}/{uuid4().hex}/{kind}"
            store.write(name, io.BytesIO(content), mime, 1000)
            session.add(OutputObject(transcode_job_id=job.id, source_generation=job.source_generation, profile_id=job.profile_id, kind=kind,
                                     storage_object=name, storage_generation=store.head(name)["generation"], bytes=len(content), duration_ms=1000))
    for uid, status in [(None, 401), ("stranger", 404), ("owner", 200)]:
        assert client.get(path + "/playback", headers=headers(uid) if uid else {}).status_code == status
    playback = client.get(path + "/playback", headers=headers()).json
    parts, query = sas(playback["url"])
    assert parts.path.startswith(f"/{CONTAINER}/outputs/{job_id.hex}/") and query["sr"] == "bv" and query["sp"] == "r" and query["rsct"] == "video/mp4"
    assert query["versionid"] == next(items[-1]["version_id"] for name, items in service.blobs.items() if name.endswith("/mp4"))
    monitor = client.get("/api/monitor", headers=headers("admin")).json
    assert monitor["storage_free_bytes"] is None and monitor["dead_messages"] is None
    # Output bị ghi đè sau khi công bố: phiên bản không còn khớp DB nên không cấp URL mới.
    thumbnail = next(name for name in service.blobs if name.endswith("/thumbnail"))
    service.put(thumbnail, b"tampered!", "image/jpeg")
    assert client.get(path + "/thumbnail", headers=headers()).status_code == 409

    assert client.delete(path, headers=headers("stranger")).status_code == 404
    assert client.delete(path, headers=headers()).status_code == 200
    assert service.blobs == {}


def test_oversized_blob_is_rejected_and_removed_at_complete(cloud):
    """SAS không giới hạn kích thước: file lớn hơn giới hạn vẫn tới được storage, và phải bị loại ở bước complete."""
    client, service = cloud.client, cloud.blobs
    assert client.post("/api/videos", headers=headers(), json={"title": "Big", "mime_type": "video/mp4", "size_bytes": 1001}).status_code == 413
    created = client.post("/api/videos", headers=headers(), json={"title": "Liar", "mime_type": "video/mp4", "size_bytes": 900})
    key = urlsplit(created.json["upload_url"]).path.removeprefix(f"/{CONTAINER}/")
    service.put(key, b"x" * 5000, "video/mp4")
    response = client.post(f"/api/videos/{created.json['video_id']}/complete", headers=headers())
    assert response.status_code == 413 and response.json["error"] == "upload_too_large"
    assert service.blobs == {} and cloud.bus.queue == []
    with Session(cloud.engine) as session:
        assert session.scalar(select(Video.status)) == "PENDING_UPLOAD" and session.scalar(select(TranscodeJob)) is None


def test_blob_outage_is_a_503_not_a_crash(cloud):
    created = cloud.client.post("/api/videos", headers=headers(), json={"title": "Cloud clip", "mime_type": "video/mp4", "size_bytes": 8})
    cloud.blobs.fail = HttpResponseError("ServerBusy")
    response = cloud.client.post(f"/api/videos/{created.json['video_id']}/complete", headers=headers())
    assert response.status_code == 503 and response.json["error"] == "storage_unavailable"
    with Session(cloud.engine) as session:
        assert session.scalar(select(Video.status)) == "PENDING_UPLOAD" and session.scalar(select(TranscodeJob)) is None
    # Khoá ký còn hạn nên vẫn cấp được URL tải lên mà không cần gọi Azure; hết khoá thì cũng trả 503.
    assert cloud.client.post("/api/videos", headers=headers(), json={"title": "Second", "mime_type": "video/mp4", "size_bytes": 8}).status_code == 201
    cloud.store.delegation = None
    assert cloud.client.post("/api/videos", headers=headers(), json={"title": "Third", "mime_type": "video/mp4", "size_bytes": 8}).status_code == 503


def test_queue_outage_after_commit_keeps_the_job_for_the_maintenance_cycle(cloud, monkeypatch):
    created = cloud.client.post("/api/videos", headers=headers(), json={"title": "Cloud clip", "mime_type": "video/mp4", "size_bytes": 8})
    key = urlsplit(created.json["upload_url"]).path.removeprefix(f"/{CONTAINER}/")
    cloud.blobs.put(key, b"12345678", "video/mp4")
    cloud.bus.fail = {"send"}
    # Giao dịch đã commit: người dùng vẫn nhận 202, event nằm lại trong outbox.
    assert cloud.client.post(f"/api/videos/{created.json['video_id']}/complete", headers=headers()).status_code == 202
    with Session(cloud.engine) as session:
        event = session.scalar(select(OutboxEvent))
        assert event.published_at is None and event.publish_attempts == 1 and event.last_error == "publish_failed"
    assert cloud.bus.queue == []
    # Lệnh của job maintenance theo lịch gửi lại event khi Service Bus đã trở lại.
    cloud.bus.fail = set()
    monkeypatch.setattr(admin_cli, "make_broker", lambda app, engine: ServiceBusBroker(cloud.bus, QUEUE))
    result = cloud.app.test_cli_runner().invoke(args=["maintain"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["event"] == "maintenance" and report["published"] == 1 and {"recovered", "work", "uploads", "outputs"} <= set(report)
    assert len(cloud.bus.queue) == 1 and cloud.bus.closed == 1
    with Session(cloud.engine) as session:
        assert session.scalar(select(OutboxEvent)).published_at is not None
    assert json.loads(cloud.app.test_cli_runner().invoke(args=["maintain"]).output)["published"] == 0
    status = cloud.app.test_cli_runner().invoke(args=["system-status"]).output
    assert "Azure Blob Storage" in status and "Azure Service Bus" in status


def test_local_mode_does_not_relay_from_the_api(schema_engine, tmp_path):
    """VPS/local: worker chạy liên tục tự relay; API không được đụng tới hàng đợi."""
    app = create_app({"TESTING": True, "TOKEN_VERIFIER": lambda token: {"uid": token}, "STORAGE_ROOT": tmp_path / "objects"})
    app.extensions["db_engine"] = schema_engine
    with Session(schema_engine) as session, session.begin():
        session.add(OutputProfile(name="mp4-480p"))
    client = app.test_client()
    created = client.post("/api/videos", headers=headers(), json={"title": "Local clip", "mime_type": "video/mp4", "size_bytes": 8})
    assert created.json["upload_headers"] == {"Content-Type": "video/mp4"}
    assert client.put(created.json["upload_url"], data=b"12345678", headers=created.json["upload_headers"]).status_code == 201
    assert client.post(f"/api/videos/{created.json['video_id']}/complete", headers=headers()).status_code == 202
    assert "broker" not in app.extensions
    with Session(schema_engine) as session:
        assert session.scalar(select(OutboxEvent)).published_at is None


@needs_ffmpeg
def test_one_job_run_transcodes_the_recorded_blob_version_and_renews_the_lock(cloud, seed_media, tmp_path):
    client, engine, service, store, broker, fake_bus = cloud.client, cloud.engine, cloud.blobs, cloud.store, cloud.broker, cloud.bus
    work = tmp_path / "work"
    assert run_once(engine, broker, store, work) == "empty"  # không có gì để làm: lần chạy kết thúc ngay
    clip = seed_media / "clip-01.mp4"
    video_id, job_id = uuid4(), uuid4()
    name = f"inputs/{video_id}/source"
    with clip.open("rb") as stream:
        store.write(name, stream, "video/mp4", 50_000_000)
    generation = store.head(name)["generation"]
    with Session(engine) as session, session.begin():
        profile_id = session.scalar(select(OutputProfile.id))
        session.add(Video(id=video_id, owner_uid="owner", title="Cloud pipeline clip", input_object=name, source_generation=generation,
                          size_bytes=clip.stat().st_size, mime_type="video/mp4", status="QUEUED"))
        session.flush()
        session.add(TranscodeJob(id=job_id, video_id=video_id, source_generation=generation, profile_id=profile_id))
        session.flush()
        session.add(OutboxEvent(job_id=job_id, kind="transcode.requested",
                                payload_json={"job_id": str(job_id), "source_generation": generation, "profile_id": str(profile_id)}))
    # Blob nguồn bị ghi đè sau khi job đã ghi nhận phiên bản: worker vẫn phải xử lý đúng phiên bản cũ.
    service.put(name, b"overwritten after completion", "video/mp4")

    def runner(source, output, attempt, on_progress):
        assert on_progress(40) is True
        return transcode(source, output)

    # Event chưa được gửi (API không kịp relay): lần chạy tự relay một event rồi xử lý luôn.
    assert run_once(engine, broker, store, work, runner=runner) == "READY"
    assert fake_bus.renewed == 1 and fake_bus.completed == 1 and fake_bus.queue == []
    assert not any(work.rglob("*.mp4"))
    playback = client.get(f"/api/videos/{video_id}/playback", headers=headers())
    assert playback.status_code == 200 and f"/outputs/{job_id.hex}/" in playback.json["url"] and playback.json["duration_ms"] > 0
    published = sorted(key.rsplit("/", 1)[1] for key in service.blobs if key.startswith("outputs/"))
    assert published == ["thumbnail.jpg", "video.mp4"]
    # Message giao lại sau khi đã READY: không tạo thêm kết quả nào.
    broker.publish(str(uuid4()), {"job_id": str(job_id), "source_generation": generation, "profile_id": str(profile_id)})
    assert run_once(engine, broker, store, work, runner=runner) == "no_op" and fake_bus.queue == []
    with Session(engine) as session:
        assert len(session.scalars(select(OutputObject)).all()) == 2

    # Dọn dẹp trên Blob Storage: chỉ blob cũ không còn được DB trỏ tới mới bị xoá.
    orphan = f"outputs/{uuid4().hex}/{uuid4().hex}/video.mp4"
    service.put(orphan, b"left by a dead attempt", "video/mp4")
    fresh = f"outputs/{uuid4().hex}/{uuid4().hex}/video.mp4"
    service.put(fresh, b"attempt still running", "video/mp4")
    for key, items in service.blobs.items():
        if key != fresh:
            items[-1]["last_modified"] = datetime.now(timezone.utc) - timedelta(days=2)
    assert cleanup_outputs(engine, store) == 1 and orphan not in service.blobs and fresh in service.blobs
    assert cleanup_uploads(engine, store) == 0
    assert client.get(f"/api/videos/{video_id}/playback", headers=headers()).status_code == 200


def test_one_job_run_reports_temporary_failures_instead_of_hiding_them(cloud, tmp_path):
    cloud.bus.fail = {"receive"}
    with pytest.raises(QueueError):
        run_once(cloud.engine, cloud.broker, cloud.store, tmp_path / "work")

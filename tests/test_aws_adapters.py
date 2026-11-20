"""Phase 07 (AWS) — kiểm thử adapter S3, SQS và xác minh token Cognito mà KHÔNG gọi AWS.

Hai loại kiểm thử, không loại nào là bằng chứng về một hệ thống AWS đang chạy:
- Client boto3 thật + botocore Stubber: tên thao tác và tham số được đối chiếu với mô hình dịch vụ của AWS,
  URL ký sẵn được sinh thật (ngoại tuyến) bằng khoá giả.
- FakeS3 trong bộ nhớ: chạy luồng API/worker đầy đủ với PostgreSQL và FFmpeg thật.
"""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import shutil
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from jwt.exceptions import PyJWKClientConnectionError
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.exceptions import HTTPException

from app import auth_oidc
from app.main import create_app
from app.maintenance import cleanup_outputs, cleanup_uploads
from app.models import OutboxEvent, OutputObject, OutputProfile, TranscodeJob, Video
from app.pipeline import dispatch_one, relay
from app.queue_local import QueueError
from app.queue_pg import PgBroker, make_broker
from app.queue_sqs import SqsBroker, sqs_client
from app.storage import StorageUnavailable, s3_origin, storage
from app.storage_s3 import S3Storage, s3_client
from worker.transcode import transcode

REGION = "ap-southeast-1"
BUCKET = "video-portal-test"
QUEUE = "https://sqs.ap-southeast-1.amazonaws.com/000000000000/video-jobs"
DEAD = "https://sqs.ap-southeast-1.amazonaws.com/000000000000/video-jobs-dead"
ISSUER = "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_TESTPOOL"
CLIENT_ID = "test-app-client"
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="Real FFmpeg/ffprobe required")


@pytest.fixture
def aws_env(monkeypatch):
    # Khoá giả chỉ để boto3 ký ngoại tuyến; Stubber chặn mọi lời gọi mạng.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-only-key-id")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-only-secret")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    for name in ["AWS_SESSION_TOKEN", "AWS_PROFILE", "AWS_ENDPOINT_URL"]:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def s3(aws_env):
    client = s3_client(REGION)
    with Stubber(client) as stub:
        yield S3Storage(BUCKET, client, max_bytes=1000), stub
        stub.assert_no_pending_responses()


@pytest.fixture
def sqs(aws_env):
    client = sqs_client(REGION)
    with Stubber(client) as stub:
        yield SqsBroker(client, QUEUE, DEAD), stub
        stub.assert_no_pending_responses()


# ---------- S3: URL ký sẵn (sinh thật, ngoại tuyến) ----------

def test_s3_upload_form_is_bound_to_key_type_size_and_expiry(s3):
    store, _ = s3
    target = store.upload_target("video-1", "inputs/video-1/source", "video/mp4", 500)
    assert target["upload_method"] == "POST"
    assert target["upload_url"].rstrip("/") == s3_origin(BUCKET, REGION)
    fields = target["upload_fields"]
    assert fields["key"] == "inputs/video-1/source" and fields["Content-Type"] == "video/mp4"
    policy = json.loads(base64.b64decode(fields["policy"]))
    conditions = policy["conditions"]
    assert ["content-length-range", 1, 500] in conditions
    assert {"Content-Type": "video/mp4"} in conditions and {"key": "inputs/video-1/source"} in conditions and {"bucket": BUCKET} in conditions
    remaining = datetime.fromisoformat(policy["expiration"].replace("Z", "+00:00")) - datetime.now(timezone.utc)
    assert timedelta(seconds=60) < remaining <= timedelta(seconds=121)
    # Giới hạn của máy chủ luôn thắng kích thước client khai báo.
    larger = store.upload_target("video-1", "inputs/video-1/source", "video/mp4", 5000)
    assert ["content-length-range", 1, 1000] in json.loads(base64.b64decode(larger["upload_fields"]["policy"]))["conditions"]
    assert "test-only-secret" not in json.dumps(target)


def test_s3_read_url_pins_version_and_expires(s3):
    store, _ = s3
    url = urlsplit(store.read_url("outputs/job/attempt/video.mp4", "version-7", "video/mp4"))
    query = parse_qs(url.query)
    assert url.scheme == "https" and url.netloc == f"{BUCKET}.s3.{REGION}.amazonaws.com"
    assert url.path == "/outputs/job/attempt/video.mp4"
    assert query["versionId"] == ["version-7"] and query["X-Amz-Expires"] == ["120"]
    assert query["response-content-type"] == ["video/mp4"] and "X-Amz-Signature" in query
    assert "test-only-secret" not in url.query


@pytest.mark.parametrize("name", ["../secret", "outputs/../inputs/x", "other/file", "inputs/", "inputs/a b", "", None, "inputs/" + "a/" * 7 + "x"])
def test_s3_rejects_names_outside_the_private_layout(s3, name):
    store, _ = s3
    for action in [lambda: store.head(name), lambda: store.delete(name), lambda: store.read_url(name, "v", "video/mp4"),
                   lambda: store.upload_target("v", name, "video/mp4", 10)]:
        with pytest.raises(HTTPException) as error:
            action()
        assert error.value.code == 404


# ---------- S3: lời gọi API (Stubber kiểm tra tham số theo mô hình dịch vụ) ----------

def test_s3_head_reports_version_and_missing_or_unversioned_objects(s3):
    store, stub = s3
    expected = {"Bucket": BUCKET, "Key": "inputs/v/source"}
    stub.add_response("head_object", {"ContentLength": 8, "ContentType": "video/mp4", "VersionId": "version-1"}, expected)
    assert store.head("inputs/v/source") == {"size_bytes": 8, "mime_type": "video/mp4", "generation": "version-1"}
    stub.add_client_error("head_object", service_error_code="404", http_status_code=404, expected_params=expected)
    with pytest.raises(HTTPException) as error:
        store.head("inputs/v/source")
    assert error.value.code == 409 and error.value.description == "object_not_ready"
    # Bucket chưa bật versioning: không có VersionId thì không xác định được phiên bản nguồn.
    stub.add_response("head_object", {"ContentLength": 8, "ContentType": "video/mp4"}, expected)
    with pytest.raises(StorageUnavailable):
        store.head("inputs/v/source")
    stub.add_client_error("head_object", service_error_code="AccessDenied", http_status_code=403, expected_params=expected)
    with pytest.raises(StorageUnavailable):
        store.head("inputs/v/source")


def test_s3_write_checks_size_before_sending(s3):
    store, stub = s3
    stub.add_response("put_object", {"VersionId": "version-2"},
                      {"Bucket": BUCKET, "Key": "outputs/job/attempt/video.mp4", "Body": ANY, "ContentType": "video/mp4", "ContentLength": 5})
    store.write("outputs/job/attempt/video.mp4", io.BytesIO(b"12345"), "video/mp4", 100)
    for content, limit, status in [(b"", 100, 400), (b"123456", 5, 413), (b"x" * 1001, 5000, 413)]:
        with pytest.raises(HTTPException) as error:
            store.write("outputs/job/attempt/video.mp4", io.BytesIO(content), "video/mp4", limit)
        assert error.value.code == status


def test_s3_download_fetches_the_exact_version(s3, tmp_path):
    store, stub = s3
    expected = {"Bucket": BUCKET, "Key": "inputs/v/source", "VersionId": "version-1"}
    stub.add_response("get_object", {"Body": StreamingBody(io.BytesIO(b"source-bytes"), 12)}, expected)
    store.download("inputs/v/source", "version-1", tmp_path / "source")
    assert (tmp_path / "source").read_bytes() == b"source-bytes"
    stub.add_client_error("get_object", service_error_code="NoSuchVersion", http_status_code=404, expected_params=expected)
    with pytest.raises(HTTPException) as error:
        store.download("inputs/v/source", "version-1", tmp_path / "second")
    assert error.value.code == 409 and not (tmp_path / "second").exists()
    stub.add_client_error("get_object", service_error_code="SlowDown", http_status_code=503, expected_params=expected)
    with pytest.raises(OSError):
        store.download("inputs/v/source", "version-1", tmp_path / "third")


def test_s3_delete_removes_every_version_of_only_that_key(s3):
    store, stub = s3
    key = "inputs/v/source"
    stub.add_response("list_object_versions", {
        "Versions": [{"Key": key, "VersionId": "version-1"}, {"Key": key, "VersionId": "version-2"}, {"Key": key + "-other", "VersionId": "version-9"}],
        "DeleteMarkers": [{"Key": key, "VersionId": "marker-1"}],
    }, {"Bucket": BUCKET, "Prefix": key})
    for version in ["version-1", "version-2", "marker-1"]:
        stub.add_response("delete_object", {}, {"Bucket": BUCKET, "Key": key, "VersionId": version})
    store.delete(key)
    stub.add_response("list_object_versions", {}, {"Bucket": BUCKET, "Prefix": key})
    store.delete(key)


def test_s3_old_objects_follows_pages(s3):
    store, stub = s3
    now = datetime.now(timezone.utc)
    old, new = now - timedelta(days=2), now - timedelta(minutes=5)
    stub.add_response("list_objects_v2", {"Contents": [{"Key": "outputs/a/b/video.mp4", "LastModified": old}, {"Key": "outputs/c/d/video.mp4", "LastModified": new}],
                                          "NextContinuationToken": "page-2"}, {"Bucket": BUCKET, "Prefix": "outputs/"})
    stub.add_response("list_objects_v2", {"Contents": [{"Key": "outputs/e/f/thumbnail.jpg", "LastModified": old}]},
                      {"Bucket": BUCKET, "Prefix": "outputs/", "ContinuationToken": "page-2"})
    assert list(store.old_objects("outputs/", now - timedelta(days=1))) == ["outputs/a/b/video.mp4", "outputs/e/f/thumbnail.jpg"]


# ---------- SQS ----------

def received(body, count="1", handle="receipt-1"):
    return {"Messages": [{"MessageId": "m-1", "ReceiptHandle": handle, "Body": body, "MD5OfBody": hashlib.md5(body.encode()).hexdigest(),
                          "Attributes": {"ApproximateReceiveCount": count}}]}


RECEIVE = {"QueueUrl": QUEUE, "MaxNumberOfMessages": 1, "WaitTimeSeconds": 2, "VisibilityTimeout": 300,
           "MessageSystemAttributeNames": ["ApproximateReceiveCount"]}


def test_sqs_publish_receive_and_ack(sqs):
    broker, stub = sqs
    key, payload = uuid4(), {"job_id": str(uuid4()), "source_generation": "version-1", "profile_id": str(uuid4())}
    body = json.dumps({"operation_key": str(key), "payload": payload})
    stub.add_response("send_message", {"MessageId": "m-1"}, {"QueueUrl": QUEUE, "MessageBody": body})
    broker.publish(key, payload)
    stub.add_response("receive_message", received(body, count="2"), RECEIVE)
    delivery = broker.receive()
    assert delivery["operation_key"] == str(key) and delivery["payload"] == payload and delivery["deliveries"] == 2
    stub.add_response("delete_message", {}, {"QueueUrl": QUEUE, "ReceiptHandle": "receipt-1"})
    broker.ack(delivery)
    stub.add_response("receive_message", {}, RECEIVE)
    assert broker.receive() is None


def test_sqs_failures_become_queue_errors_and_limits_hold(sqs):
    broker, stub = sqs
    with pytest.raises(QueueError, match="message_too_large"):
        broker.publish(uuid4(), {"padding": "x" * 5000})
    with pytest.raises(ValueError):
        broker.publish("not-a-uuid", {})
    stub.add_client_error("send_message", service_error_code="ServiceUnavailable", http_status_code=503)
    with pytest.raises(QueueError):
        broker.publish(uuid4(), {"job_id": "x"})
    stub.add_client_error("receive_message", service_error_code="AccessDenied", http_status_code=403)
    with pytest.raises(QueueError):
        broker.receive()
    stub.add_client_error("delete_message", service_error_code="ReceiptHandleIsInvalid", http_status_code=400)
    with pytest.raises(QueueError):
        broker.ack({"delivery_id": "stale-receipt"})


def test_sqs_invalid_message_goes_to_the_dead_letter_queue(sqs, tmp_path):
    broker, stub = sqs
    stub.add_response("receive_message", received("this is not json"), RECEIVE)
    stub.add_response("send_message", {"MessageId": "m-2"}, {
        "QueueUrl": DEAD, "MessageBody": "this is not json",
        "MessageAttributes": {"dead_reason": {"DataType": "String", "StringValue": "invalid_job_message"}}})
    stub.add_response("delete_message", {}, {"QueueUrl": QUEUE, "ReceiptHandle": "receipt-1"})
    # Message hỏng bị loại trước khi chạm DB hay storage, nên không cần engine/store thật ở đây.
    assert dispatch_one(None, broker, None, tmp_path) == "dead_letter"


def test_sqs_heartbeat_extends_visibility_only_when_due(sqs):
    broker, stub = sqs
    delivery = {"delivery_id": "receipt-1", "extended_at": time.monotonic()}
    broker.extend(delivery)  # vừa nhận xong: chưa cần gọi SQS
    delivery["extended_at"] -= 200
    stub.add_response("change_message_visibility", {}, {"QueueUrl": QUEUE, "ReceiptHandle": "receipt-1", "VisibilityTimeout": 300})
    broker.extend(delivery)
    assert time.monotonic() - delivery["extended_at"] < 5
    delivery["extended_at"] -= 200
    stub.add_client_error("change_message_visibility", service_error_code="ReceiptHandleIsInvalid", http_status_code=400)
    broker.extend(delivery)  # lỗi gia hạn không được làm hỏng job đang chạy


def test_sqs_counts_both_queues(sqs):
    broker, stub = sqs
    for url, count in [(QUEUE, "3"), (DEAD, "1")]:
        stub.add_response("get_queue_attributes", {"Attributes": {"ApproximateNumberOfMessages": count}},
                          {"QueueUrl": url, "AttributeNames": ["ApproximateNumberOfMessages"]})
    assert broker.counts() == {"pending": 3, "dead": 1}


# ---------- Cognito / OIDC ----------

@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def cognito(monkeypatch, signing_key):
    """App dùng AUTH_PROVIDER=cognito; khoá JWKS được thay bằng khoá công khai của cặp khoá test."""
    fake_jwks = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=signing_key.public_key()))
    monkeypatch.setattr(auth_oidc, "jwks_client", lambda issuer: fake_jwks)
    app = create_app({"TESTING": True, "AUTH_PROVIDER": "cognito", "AWS_REGION": REGION, "OIDC_ISSUER": ISSUER, "OIDC_CLIENT_ID": CLIENT_ID})
    return app.test_client()


def id_token(key, algorithm="RS256", **changes):
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": str(uuid4()), "token_use": "id", "email": "Owner@Example.com",
              "email_verified": True, "iat": now, "exp": now + 600, **changes}
    return jwt.encode({name: value for name, value in claims.items() if value is not None}, key, algorithm=algorithm, headers={"kid": "test-key"})


def me(client, token):
    return client.get("/api/me", headers={"Authorization": "Bearer " + token})


def test_cognito_id_token_gives_email_identity_and_admin_group(cognito, signing_key):
    user = me(cognito, id_token(signing_key))
    assert user.status_code == 200 and user.json["uid"] == "owner@example.com" and user.json["admin"] is False
    admin = me(cognito, id_token(signing_key, **{"cognito:groups": ["viewers", "admin"]}))
    assert admin.json["admin"] is True
    assert me(cognito, id_token(signing_key, **{"cognito:groups": "admin"})).json["admin"] is False


@pytest.mark.parametrize("changes", [
    {"aud": "another-app-client"}, {"iss": ISSUER + "-other"}, {"exp": int(time.time()) - 60}, {"exp": None}, {"iat": None},
    {"token_use": "access"}, {"email_verified": False}, {"email_verified": "true"}, {"email": None}, {"email": 42},
])
def test_cognito_rejects_wrong_or_incomplete_tokens(cognito, signing_key, changes):
    response = me(cognito, id_token(signing_key, **changes))
    assert response.status_code == 401 and response.json["error"] == "invalid_or_expired_token"


def test_cognito_rejects_other_keys_algorithms_and_garbage(cognito, signing_key):
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = [id_token(stranger), id_token("shared-secret-that-is-long-enough-for-hs256", algorithm="HS256"), "not.a.token", "x" * 40]
    assert [me(cognito, token).status_code for token in forged] == [401, 401, 401, 401]
    assert cognito.get("/api/me").status_code == 401


def test_cognito_key_lookup_failures_fail_closed(monkeypatch, signing_key):
    def unreachable(issuer):
        return SimpleNamespace(get_signing_key_from_jwt=lambda token: (_ for _ in ()).throw(PyJWKClientConnectionError("down")))
    monkeypatch.setattr(auth_oidc, "jwks_client", unreachable)
    app = create_app({"TESTING": True, "AUTH_PROVIDER": "cognito", "AWS_REGION": REGION, "OIDC_ISSUER": ISSUER, "OIDC_CLIENT_ID": CLIENT_ID})
    response = me(app.test_client(), id_token(signing_key))
    assert response.status_code == 503 and response.json["error"] == "auth_temporarily_unavailable"
    unconfigured = create_app({"TESTING": True, "AUTH_PROVIDER": "cognito"}).test_client()
    assert me(unconfigured, id_token(signing_key)).status_code == 503
    assert unconfigured.get("/api/auth/config").status_code == 503


def test_cognito_public_config_and_page_policy(cognito):
    config = cognito.get("/api/auth/config").json
    assert {name: config[name] for name in ["provider", "region", "client_id"]} == {"provider": "cognito", "region": REGION, "client_id": CLIENT_ID}
    assert cognito.get("/api/config").json["auth_provider"] == "cognito"
    assert cognito.post("/api/auth/login", json={"email": "a@example.com", "password": "x"}).status_code == 404
    policy = cognito.get("/").headers["Content-Security-Policy"]
    assert f"connect-src 'self' https://cognito-idp.{REGION}.amazonaws.com;" in policy and "identitytoolkit" not in policy


# ---------- Cấu hình ----------

def aws_settings(tmp_path):
    return {"WORK_ROOT": tmp_path / "work", "AUTH_PROVIDER": "cognito", "STORAGE_BACKEND": "s3", "QUEUE_BACKEND": "sqs",
            "AWS_REGION": REGION, "S3_BUCKET": BUCKET, "SQS_QUEUE_URL": QUEUE, "SQS_DEAD_LETTER_URL": DEAD,
            "OIDC_ISSUER": ISSUER, "OIDC_CLIENT_ID": CLIENT_ID}


def test_aws_production_configuration_is_validated(monkeypatch, tmp_path, aws_env):
    for name in ["FIREBASE_AUTH_EMULATOR_HOST", "K_SERVICE"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    good = aws_settings(tmp_path)
    app = create_app(dict(good))  # không cần STORAGE_ROOT khi file nằm trên S3
    client = app.test_client()
    policy = client.get("/").headers["Content-Security-Policy"]
    origin = s3_origin(BUCKET, REGION)
    assert f"connect-src 'self' https://cognito-idp.{REGION}.amazonaws.com {origin};" in policy
    assert f"media-src 'self' {origin};" in policy and f"img-src 'self' {origin};" in policy
    # Với S3 trình duyệt nói chuyện thẳng với bucket: hai route storage local không tồn tại.
    assert client.put("/local-storage/upload?ticket=x", data=b"x").status_code == 404
    assert client.get("/local-storage/read?ticket=x").status_code == 404
    with app.app_context():
        assert isinstance(storage(), S3Storage) and storage().bucket == BUCKET
    assert isinstance(make_broker(app, None), SqsBroker)
    bad_settings = [
        {**good, "S3_BUCKET": ""}, {**good, "AWS_REGION": ""}, {**good, "SQS_QUEUE_URL": ""}, {**good, "SQS_DEAD_LETTER_URL": ""},
        {**good, "OIDC_CLIENT_ID": ""}, {**good, "OIDC_ISSUER": ""}, {**good, "STORAGE_BACKEND": "gcs"}, {**good, "QUEUE_BACKEND": "pubsub"},
        {**good, "S3_BUCKET": "bucket.with.dots"}, {**good, "S3_BUCKET": "bucket/../x"}, {**good, "AWS_REGION": "evil.example.com/"},
        {**good, "WORK_ROOT": "relative/work"}, {name: value for name, value in good.items() if name != "WORK_ROOT"},
    ]
    for bad in bad_settings:
        with pytest.raises(ValueError):
            create_app(bad)


def test_aws_settings_come_from_environment_and_local_stays_default(monkeypatch, tmp_path, aws_env):
    for name in ["FIREBASE_AUTH_EMULATOR_HOST", "K_SERVICE", "VIDEO_PORTAL_ENV_FILE", "APP_ENV"]:
        monkeypatch.delenv(name, raising=False)
    local = create_app({"TESTING": True})
    assert local.config["STORAGE_BACKEND"] == "local" and local.config["QUEUE_BACKEND"] == "postgres"
    assert isinstance(make_broker(local, None), PgBroker)
    assert "media-src" not in local.test_client().get("/").headers["Content-Security-Policy"]
    for name, value in {"AUTH_PROVIDER": "cognito", "STORAGE_BACKEND": "S3", "QUEUE_BACKEND": "sqs", "AWS_REGION": REGION, "S3_BUCKET": BUCKET,
                        "SQS_QUEUE_URL": QUEUE, "SQS_DEAD_LETTER_URL": DEAD, "COGNITO_USER_POOL_ID": "ap-southeast-1_TESTPOOL",
                        "COGNITO_CLIENT_ID": CLIENT_ID, "WORK_ROOT": str(tmp_path / "work")}.items():
        monkeypatch.setenv(name, value)
    app = create_app()
    assert app.config["OIDC_ISSUER"] == ISSUER and app.config["OIDC_CLIENT_ID"] == CLIENT_ID and app.config["STORAGE_BACKEND"] == "s3"


# ---------- Luồng đầy đủ với S3 giả trong bộ nhớ (PostgreSQL thật) ----------

class FakeS3:
    """S3 có versioning trong bộ nhớ, chỉ đủ cho các thao tác S3Storage dùng. Không phải bằng chứng về AWS."""

    def __init__(self):
        self.objects = {}
        self.count = 0

    def put_object(self, Bucket, Key, Body, ContentType, ContentLength=None):
        self.count += 1
        data = Body.read() if hasattr(Body, "read") else Body
        self.objects.setdefault(Key, []).append({"VersionId": f"version-{self.count}", "Body": data, "ContentType": ContentType,
                                                 "LastModified": datetime.now(timezone.utc)})
        return {"VersionId": f"version-{self.count}"}

    def head_object(self, Bucket, Key):
        if not self.objects.get(Key):
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        latest = self.objects[Key][-1]
        return {"ContentLength": len(latest["Body"]), "ContentType": latest["ContentType"], "VersionId": latest["VersionId"]}

    def get_object(self, Bucket, Key, VersionId):
        for item in self.objects.get(Key, []):
            if item["VersionId"] == VersionId:
                return {"Body": StreamingBody(io.BytesIO(item["Body"]), len(item["Body"]))}
        raise ClientError({"Error": {"Code": "NoSuchVersion"}}, "GetObject")

    def list_object_versions(self, Bucket, Prefix):
        return {"Versions": [{"Key": key, "VersionId": item["VersionId"]} for key, items in self.objects.items() if key.startswith(Prefix) for item in items]}

    def delete_object(self, Bucket, Key, VersionId):
        self.objects[Key] = [item for item in self.objects[Key] if item["VersionId"] != VersionId]
        if not self.objects[Key]:
            del self.objects[Key]

    def list_objects_v2(self, Bucket, Prefix):
        return {"Contents": [{"Key": key, "LastModified": items[-1]["LastModified"]} for key, items in self.objects.items() if key.startswith(Prefix)]}

    def generate_presigned_post(self, Bucket, Key, Fields, Conditions, ExpiresIn):
        return {"url": f"https://{Bucket}.s3.test/", "fields": {"key": Key, **Fields, "policy": "signed-by-fake"}}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://{Params['Bucket']}.s3.test/{Params['Key']}?versionId={Params['VersionId']}&X-Amz-Expires={ExpiresIn}"


class MemoryBroker:
    def __init__(self):
        self.pending, self.acked, self.extended = [], 0, 0

    def publish(self, key, payload):
        self.pending.append({"operation_key": key, "payload": dict(payload)})

    def receive(self):
        return self.pending[0] if self.pending else None

    def ack(self, delivery):
        self.pending.remove(delivery)
        self.acked += 1

    def extend(self, delivery):
        self.extended += 1


@pytest.fixture
def cloud(schema_engine):
    def verifier(token):
        if token not in {"owner", "viewer", "stranger", "admin"}:
            raise ValueError("invalid")
        return {"uid": token, "admin": token == "admin"}
    app = create_app({"TESTING": True, "TOKEN_VERIFIER": verifier, "STORAGE_BACKEND": "s3", "QUEUE_BACKEND": "sqs", "AWS_REGION": REGION, "S3_BUCKET": BUCKET})
    app.extensions["db_engine"] = schema_engine
    fake = FakeS3()
    app.extensions["storage"] = S3Storage(BUCKET, fake, 50_000_000)
    with Session(schema_engine) as session, session.begin():
        session.add(OutputProfile(name="mp4-480p"))
    return app, app.test_client(), schema_engine, fake


def headers(uid="owner"):
    return {"Authorization": "Bearer " + uid}


def test_portal_upload_complete_playback_and_delete_with_s3(cloud):
    app, client, engine, fake = cloud
    store = app.extensions["storage"]
    created = client.post("/api/videos", headers=headers(), json={"title": "Cloud clip", "mime_type": "video/mp4", "size_bytes": 8})
    assert created.status_code == 201 and created.json["upload_method"] == "POST" and created.json["expires_in"] == 120
    key = created.json["upload_fields"]["key"]
    assert key.startswith("inputs/" + created.json["video_id"] + "/")
    path = "/api/videos/" + created.json["video_id"]
    assert client.post(path + "/complete", headers=headers()).status_code == 409  # chưa có object
    fake.put_object(BUCKET, key, b"1234", "video/mp4")
    assert client.post(path + "/complete", headers=headers()).status_code == 400  # sai kích thước đã khai báo
    fake.put_object(BUCKET, key, b"12345678", "text/plain")
    assert client.post(path + "/complete", headers=headers()).status_code == 400  # sai Content-Type
    fake.put_object(BUCKET, key, b"12345678", "video/mp4")
    assert client.post(path + "/complete", headers=headers("stranger")).status_code == 404
    first = client.post(path + "/complete", headers=headers())
    assert first.status_code == 202
    assert client.post(path + "/complete", headers=headers()).json["job_id"] == first.json["job_id"]
    with Session(engine) as session:
        job = session.scalar(select(TranscodeJob))
        # source_generation là VersionId của đúng lần upload được chấp nhận.
        assert job.source_generation == fake.objects[key][-1]["VersionId"]
        assert session.scalar(select(OutboxEvent)).payload_json["source_generation"] == job.source_generation
        job_id = job.id
    listed = client.get("/api/videos", headers=headers()).get_data(as_text=True)
    assert "inputs/" not in listed and "s3.test" not in listed
    assert client.get(path + "/playback", headers=headers()).status_code == 409

    with Session(engine) as session, session.begin():
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
    assert playback["url"].startswith(f"https://{BUCKET}.s3.test/outputs/{job_id.hex}/") and "versionId=" in playback["url"]
    monitor = client.get("/api/monitor", headers=headers("admin")).json
    assert monitor["storage_free_bytes"] is None and monitor["dead_messages"] is None
    # Output bị ghi đè sau khi công bố: phiên bản không còn khớp DB nên không cấp URL mới.
    thumbnail = next(name for name in fake.objects if name.endswith("/thumbnail"))
    fake.put_object(BUCKET, thumbnail, b"tampered!", "image/jpeg")
    assert client.get(path + "/thumbnail", headers=headers()).status_code == 409

    assert client.delete(path, headers=headers("stranger")).status_code == 404
    assert client.delete(path, headers=headers()).status_code == 200
    assert fake.objects == {}


def test_s3_outage_is_a_503_not_a_crash(cloud):
    app, client, engine, fake = cloud
    def broken(*args, **kwargs):
        raise ClientError({"Error": {"Code": "SlowDown"}}, "HeadObject")
    created = client.post("/api/videos", headers=headers(), json={"title": "Cloud clip", "mime_type": "video/mp4", "size_bytes": 8})
    fake.head_object = broken
    response = client.post(f"/api/videos/{created.json['video_id']}/complete", headers=headers())
    assert response.status_code == 503 and response.json["error"] == "storage_unavailable"
    with Session(engine) as session:
        assert session.scalar(select(Video.status)) == "PENDING_UPLOAD" and session.scalar(select(TranscodeJob)) is None


@needs_ffmpeg
def test_worker_transcodes_the_recorded_s3_version_and_keeps_the_message_hidden(cloud, seed_media, tmp_path):
    app, client, engine, fake = cloud
    store = app.extensions["storage"]
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
    # Object nguồn bị ghi đè sau khi job đã ghi nhận phiên bản: worker vẫn phải xử lý đúng phiên bản cũ.
    fake.put_object(BUCKET, name, b"overwritten after completion", "video/mp4")
    broker = MemoryBroker()
    assert relay(engine, broker) == 1

    def runner(source, output, attempt, on_progress):
        assert on_progress(40) is True
        return transcode(source, output)

    assert dispatch_one(engine, broker, store, tmp_path / "work", runner=runner, heartbeat=True) == "READY"
    assert broker.extended == 1 and broker.acked == 1 and broker.pending == []
    assert not any((tmp_path / "work").rglob("*.mp4"))
    playback = client.get(f"/api/videos/{video_id}/playback", headers=headers())
    assert playback.status_code == 200 and f"/outputs/{job_id.hex}/" in playback.json["url"] and playback.json["duration_ms"] > 0
    published = sorted(key.rsplit("/", 1)[1] for key in fake.objects if key.startswith("outputs/"))
    assert published == ["thumbnail.jpg", "video.mp4"]
    # Message giao lại sau khi đã READY: không tạo thêm kết quả nào.
    broker.publish(str(uuid4()), {"job_id": str(job_id), "source_generation": generation, "profile_id": str(profile_id)})
    assert dispatch_one(engine, broker, store, tmp_path / "work", runner=runner, heartbeat=True) == "no_op"
    with Session(engine) as session:
        assert len(session.scalars(select(OutputObject)).all()) == 2

    # Dọn dẹp trên S3: chỉ object cũ không còn được DB trỏ tới mới bị xoá.
    orphan = f"outputs/{uuid4().hex}/{uuid4().hex}/video.mp4"
    fake.put_object(BUCKET, orphan, b"left by a dead attempt", "video/mp4")
    fresh = f"outputs/{uuid4().hex}/{uuid4().hex}/video.mp4"
    fake.put_object(BUCKET, fresh, b"attempt still running", "video/mp4")
    for key, items in fake.objects.items():
        if key != fresh:
            items[-1]["LastModified"] = datetime.now(timezone.utc) - timedelta(days=2)
    assert cleanup_outputs(engine, store) == 1 and orphan not in fake.objects and fresh in fake.objects
    assert cleanup_uploads(engine, store) == 0
    assert client.get(f"/api/videos/{video_id}/playback", headers=headers()).status_code == 200

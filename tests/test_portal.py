from concurrent.futures import ThreadPoolExecutor
import io
import json
import logging
import time
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import OutboxEvent, OutputObject, OutputProfile, TranscodeJob, Video
from app.storage import LocalStorage, RedactStorageTickets


@pytest.fixture
def portal(schema_engine, tmp_path):
    def verifier(token):
        if token not in {"owner", "viewer", "stranger", "admin"}:
            raise ValueError("invalid")
        return {"uid": token, "admin": token == "admin"}
    app = create_app({"TESTING": True, "TOKEN_VERIFIER": verifier, "STORAGE_ROOT": tmp_path / "objects", "STORAGE_SIGNING_KEY": "test-only-key"})
    app.extensions["db_engine"] = schema_engine
    with Session(schema_engine) as session, session.begin():
        session.add(OutputProfile(name="mp4-480p"))
    return app, app.test_client(), schema_engine


def headers(uid="owner"):
    return {"Authorization": "Bearer " + uid}


def create(client, size=8, **changes):
    return client.post("/api/videos", headers=headers(), json={"title": "My private video", "mime_type": "video/mp4", "size_bytes": size, **changes})


def uploaded(portal):
    app, client, engine = portal
    created = create(client).json
    assert client.put(created["upload_url"], data=b"12345678", content_type="video/mp4").status_code == 201
    return created


def ready(portal):
    app, client, engine = portal
    created = uploaded(portal)
    completed = client.post(f"/api/videos/{created['video_id']}/complete", headers=headers()).json
    from uuid import UUID
    store = app.extensions["storage"]
    with Session(engine) as session, session.begin():
        job = session.get(TranscodeJob, UUID(completed["job_id"]))
        video = session.get(Video, job.video_id)
        video.status = job.status = "READY"
        for kind, content, mime in [("mp4", b"ready-mp4-fixture", "video/mp4"), ("thumbnail", b"ready-jpg-fixture", "image/jpeg")]:
            name = f"outputs/{job.id}/{kind}"
            store.write(name, io.BytesIO(content), mime, 1000)
            metadata = store.head(name)
            session.add(OutputObject(transcode_job_id=job.id, source_generation=job.source_generation, profile_id=job.profile_id, kind=kind, storage_object=name, storage_generation=metadata["generation"], bytes=len(content), duration_ms=1000))
    return created["video_id"]


def test_upload_complete_repeat_and_listing(portal):
    app, client, engine = portal
    created = uploaded(portal)
    path = f"/api/videos/{created['video_id']}"
    assert client.post(path + "/complete", headers=headers("stranger")).status_code == 404
    first = client.post(path + "/complete", headers=headers())
    assert first.status_code == 202
    second = client.post(path + "/complete", headers=headers())
    assert first.json["job_id"] == second.json["job_id"]
    assert client.get(path + "/status", headers=headers()).json["status"] == "QUEUED"
    assert client.get(path + "/playback", headers=headers()).status_code == 409
    listed = client.get("/api/videos", headers=headers())
    assert len(listed.json["videos"]) == 1
    assert "upload_url" not in listed.get_data(as_text=True) and "inputs/" not in listed.get_data(as_text=True)
    assert client.get("/api/videos", headers=headers("viewer")).json["videos"] == []
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(TranscodeJob)) == 1
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
        assert session.scalar(select(Video)).owner_uid == "owner"


def test_complete_logs_one_line_linking_request_video_and_job(portal, caplog):
    app, client, engine = portal
    created = uploaded(portal)
    with caplog.at_level(logging.INFO, logger="app.pipeline"):
        completed = client.post(f"/api/videos/{created['video_id']}/complete", headers=headers())
    lines = [json.loads(record.getMessage()) for record in caplog.records if record.name == "app.pipeline"]
    assert lines == [{"job_id": completed.json["job_id"], "status": "QUEUED", "video_id": created["video_id"], "request_id": completed.json["request_id"]}]

def test_parallel_complete_creates_one_job_event(portal):
    app, client, engine = portal
    created = uploaded(portal)
    def complete(_):
        with app.test_client() as thread_client:
            return thread_client.post(f"/api/videos/{created['video_id']}/complete", headers=headers()).json["job_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert len(set(pool.map(complete, range(2)))) == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 1


@pytest.mark.parametrize("changes,status", [({"title": " "}, 400), ({"size_bytes": 50_000_001}, 413), ({"size_bytes": True}, 400), ({"mime_type": "text/plain"}, 400), ({"mime_type": {}}, 400)])
def test_create_validation(portal, changes, status):
    assert create(portal[1], **changes).status_code == status


def test_owner_from_verified_token_only(portal):
    app, client, engine = portal
    assert create(client, owner_uid="stranger").status_code == 201
    assert client.get("/api/videos", headers=headers("stranger")).json["videos"] == []


def test_missing_upload_size_and_type_mismatch(portal):
    app, client, engine = portal
    created = create(client).json
    path = f"/api/videos/{created['video_id']}/complete"
    assert client.post(path, headers=headers()).status_code == 409
    assert client.put(created["upload_url"], data=b"12345678", content_type="text/plain").status_code == 400
    assert client.put(created["upload_url"], data=b"123456789", content_type="video/mp4").status_code == 413
    assert client.put(created["upload_url"], data=b"1234", content_type="video/mp4").status_code == 201
    assert client.post(path, headers=headers()).status_code == 400
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 0


def test_expired_tampered_and_cross_operation_tickets(portal):
    app, client, engine = portal
    with patch("itsdangerous.timed.time.time", return_value=time.time() - 180):
        expired = create(client).json
    assert client.put(expired["upload_url"], data=b"12345678", content_type="video/mp4").status_code == 403
    created = create(client).json
    base, signature = created["upload_url"].rsplit(".", 1)
    tampered = base + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
    assert client.put(tampered, data=b"12345678", content_type="video/mp4").status_code == 403
    query = urlsplit(created["upload_url"]).query
    assert client.get("/local-storage/read?" + query).status_code == 403
    assert client.get("/local-storage/read").status_code == 403


def test_private_playback_and_permission_revocation(portal):
    app, client, engine = portal
    video_id = ready(portal)
    base = f"/api/videos/{video_id}"
    for uid, status in [(None, 401), ("stranger", 404), ("viewer", 404), ("owner", 200)]:
        for suffix in ["/playback", "/thumbnail"]:
            response = client.get(base + suffix, headers=headers(uid) if uid else {})
            assert response.status_code == status
            if status != 200:
                assert "url" not in response.json
    assert client.post(base + "/permissions", headers=headers("viewer"), json={"viewer_uid": "stranger", "action": "grant"}).status_code == 404
    for _ in range(2):
        assert client.post(base + "/permissions", headers=headers(), json={"viewer_uid": "viewer", "action": "grant"}).status_code == 200
    assert len(client.get("/api/videos", headers=headers("viewer")).json["videos"]) == 1
    playback = client.get(base + "/playback", headers=headers("viewer")).json
    response = client.get(playback["url"], headers={"Range": "bytes=0-4"})
    assert response.status_code == 206 and response.data == b"ready"
    response.close()
    client.post(base + "/permissions", headers=headers(), json={"viewer_uid": "viewer", "action": "revoke"})
    assert client.get(base + "/playback", headers=headers("viewer")).status_code == 404
    # URL đã cấp là capability, vẫn có hiệu lực trong TTL dù quyền vừa bị thu hồi.
    response = client.get(playback["url"])
    assert response.status_code == 200
    response.close()


@pytest.mark.parametrize("mode", ["missing", "changed"])
def test_incomplete_or_changed_outputs_not_published(portal, mode):
    app, client, engine = portal
    video_id = ready(portal)
    with Session(engine) as session, session.begin():
        output = session.scalar(select(OutputObject).where(OutputObject.kind == "thumbnail"))
        name = output.storage_object
        if mode == "missing":
            session.delete(output)
    if mode == "changed":
        app.extensions["storage"].path(name).write_bytes(b"changed")
    assert client.get(f"/api/videos/{video_id}/playback", headers=headers()).status_code == 409


def test_complete_transaction_rolls_back_on_event_failure(portal):
    app, client, engine = portal
    created = uploaded(portal)
    def fail(*args):
        raise RuntimeError("simulated event insert failure")
    event.listen(OutboxEvent, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError):
            client.post(f"/api/videos/{created['video_id']}/complete", headers=headers())
    finally:
        event.remove(OutboxEvent, "before_insert", fail)
    with Session(engine) as session:
        assert session.scalar(select(Video.status)) == "PENDING_UPLOAD"
        assert session.scalar(select(func.count()).select_from(TranscodeJob)) == 0
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 0


def test_admin_and_unknown_api_denied(portal):
    client = portal[1]
    assert client.get("/api/monitor", headers=headers()).status_code == 403
    assert client.get("/api/monitor", headers=headers("admin")).status_code == 200
    assert client.get("/api/videos").status_code == 401


def test_storage_path_and_persistent_key(tmp_path):
    store = LocalStorage(tmp_path)
    url = store.signed_url("read", name="outputs/test")
    ticket = parse_qs(urlsplit(url).query)["ticket"][0]
    assert LocalStorage(tmp_path).verify(ticket, "read")["name"] == "outputs/test"
    app = create_app({"TESTING": True})
    with app.app_context(), pytest.raises(Exception) as error:
        store.path("outputs/../../secret")
    assert error.value.code == 404


def test_signed_ticket_access_log_redaction():
    record = logging.LogRecord("werkzeug", logging.INFO, "", 1, 'GET /local-storage/read?ticket=%s HTTP/1.1', ("private-ticket-marker",), None)
    RedactStorageTickets().filter(record)
    assert "private-ticket-marker" not in record.getMessage()


def test_parallel_key_initialization_and_stream_limit(tmp_path):
    with ThreadPoolExecutor(max_workers=4) as pool:
        stores = list(pool.map(lambda _: LocalStorage(tmp_path), range(4)))
    ticket = parse_qs(urlsplit(stores[0].signed_url("read", name="outputs/test")).query)["ticket"][0]
    assert all(store.verify(ticket, "read")["name"] == "outputs/test" for store in stores)
    app = create_app({"TESTING": True})
    with app.app_context(), pytest.raises(Exception) as error:
        stores[0].write("inputs/oversized", io.BytesIO(b"123456789"), "video/mp4", 8)
    assert error.value.code == 413
    assert not stores[0].path("inputs/oversized").exists()

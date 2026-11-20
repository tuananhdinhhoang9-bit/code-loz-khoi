"""Phase 07 — kiểm thử phần chuyển sang VPS Windows: storage riêng tư, hàng đợi PostgreSQL,
worker FFmpeg native, tài khoản nội bộ, migration, dọn dẹp và tắt service an toàn.
Mọi test dùng PostgreSQL/FFmpeg thật; thiếu công cụ thì test bị SKIP, không giả lập PASS."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import io
import json
import logging
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from uuid import uuid4

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app import auth_local, worker_native
from app.db_cli import upgrade_schema
from app.logs import configure_logging
from app.main import create_app
from app.maintenance import cleanup_outputs, cleanup_uploads, cleanup_work
from app.models import AuthSession, OutboxEvent, OutputObject, OutputProfile, QueueMessage, TranscodeJob, User, Video, VideoPermission
from app.pipeline import claim_job, dispatch_one, reconcile, relay, touch_lease
from app.queue_local import FileBroker, QueueError
from app.queue_pg import MAX_DELIVERIES, PgBroker
from app.storage import LocalStorage, StorageFull
from app.worker_native import run_native
from app.worker_service import run_worker, single_worker_lock
from worker import transcode as transcode_module
from worker.transcode import MediaError, probe

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = os.name == "nt"
PASSWORD = "correct horse battery staple"
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="Real FFmpeg/ffprobe required")
windows_only = pytest.mark.skipif(not WINDOWS, reason="Windows-only behaviour")


@pytest.fixture
def vps(schema_engine, tmp_path):
    auth_local.ip_attempts.clear()
    # Thư mục có dấu cách và dấu tiếng Việt: đường dẫn Windows thực tế hay gặp.
    app = create_app({"TESTING": True, "AUTH_PROVIDER": "local", "SESSION_HOURS": 1,
                      "STORAGE_ROOT": tmp_path / "Lưu trữ riêng" / "objects", "STORAGE_SIGNING_KEY": "test-only-key"})
    app.extensions["db_engine"] = schema_engine
    with Session(schema_engine) as session, session.begin():
        session.add(OutputProfile(name="mp4-480p"))
    return app, app.test_client(), schema_engine


def sign_in(vps, email, admin=False):
    app, client, engine = vps
    auth_local.create_user(engine, email, PASSWORD, admin)
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json["token"]}


def ready_video(vps, owner_headers):
    """Video READY với hai output cố định (fixture hợp đồng storage, không phải kết quả FFmpeg)."""
    app, client, engine = vps
    created = client.post("/api/videos", headers=owner_headers, json={"title": "Clip", "mime_type": "video/mp4", "size_bytes": 8}).json
    assert client.put(created["upload_url"], data=b"12345678", content_type="video/mp4").status_code == 201
    completed = client.post(f"/api/videos/{created['video_id']}/complete", headers=owner_headers).json
    store = app.extensions["storage"]
    with Session(engine) as session, session.begin():
        job = session.scalar(select(TranscodeJob).where(TranscodeJob.id == completed["job_id"]))
        video = session.get(Video, job.video_id)
        video.status = job.status = "READY"
        for kind, content, mime in [("mp4", b"ready-mp4-fixture", "video/mp4"), ("thumbnail", b"ready-jpg-fixture", "image/jpeg")]:
            name = f"outputs/{job.id.hex}/{uuid4().hex}/{kind}"
            store.write(name, io.BytesIO(content), mime, 1000)
            session.add(OutputObject(transcode_job_id=job.id, source_generation=job.source_generation, profile_id=job.profile_id, kind=kind,
                                     storage_object=name, storage_generation=store.head(name)["generation"], bytes=len(content), duration_ms=1000))
    return created["video_id"]


# ---------- Tài khoản nội bộ, phiên và phân quyền ----------

def test_local_login_session_and_logout(vps):
    app, client, engine = vps
    assert client.get("/api/auth/config").json["provider"] == "local"
    # Không có tài khoản mặc định: chưa tạo user thì không đăng nhập được.
    assert client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin"}).status_code == 401
    headers = sign_in(vps, "Owner@Example.com")
    assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong password!"}).json["error"] == "invalid_credentials"
    me = client.get("/api/me", headers=headers).json
    assert me["uid"] == "owner@example.com" and me["admin"] is False
    with Session(engine) as session:
        stored = session.scalar(select(AuthSession))
        # DB chỉ giữ SHA-256 của token và hash scrypt của mật khẩu.
        assert len(stored.token_hash) == 64 and stored.token_hash not in headers["Authorization"]
        assert session.get(User, "owner@example.com").password_hash.startswith("scrypt:")
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/me", headers=headers).status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer forged-token"}).status_code == 401


def test_lockout_expiry_disabled_user_and_password_rules(vps):
    app, client, engine = vps
    headers = sign_in(vps, "owner@example.com")
    for _ in range(auth_local.MAX_FAILURES):
        assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": "bad"}).status_code == 401
    locked = client.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
    assert locked.status_code == 429 and locked.json["error"] == "too_many_attempts"
    with Session(engine) as session, session.begin():
        session.get(User, "owner@example.com").locked_until = None
    assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).status_code == 200
    with Session(engine) as session, session.begin():
        for row in session.scalars(select(AuthSession)):
            row.expires_at = row.created_at - timedelta(seconds=1)
    assert client.get("/api/me", headers=headers).status_code == 401
    fresh = client.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).json["token"]
    auth_local.set_active(engine, "owner@example.com", False)
    assert client.get("/api/me", headers={"Authorization": "Bearer " + fresh}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).status_code == 401
    with pytest.raises(ValueError):
        auth_local.create_user(engine, "short@example.com", "too-short")
    with pytest.raises(ValueError):
        auth_local.create_user(engine, "not-an-email", PASSWORD)
    with pytest.raises(ValueError):
        auth_local.create_user(engine, "owner@example.com", PASSWORD)


def test_admin_manages_accounts_through_the_api(vps):
    app, client, engine = vps
    admin = sign_in(vps, "admin@example.com", admin=True)
    member = sign_in(vps, "member@example.com")
    # Người thường và người chưa đăng nhập không quản lý được tài khoản.
    new = {"email": "New.Person@Example.com", "password": PASSWORD}
    for call in [lambda h: client.get("/api/users", headers=h), lambda h: client.post("/api/users", headers=h, json=new),
                 lambda h: client.post("/api/users/password", headers=h, json=new),
                 lambda h: client.post("/api/users/active", headers=h, json={"email": "admin@example.com", "active": False})]:
        assert call({}).status_code == 401
        assert call(member).status_code == 403
    created = client.post("/api/users", headers=admin, json=new)
    assert created.status_code == 201 and created.json["uid"] == "new.person@example.com"
    assert client.post("/api/users", headers=admin, json=new).json["error"] == "user_exists"
    assert client.post("/api/users", headers=admin, json={"email": "bad", "password": PASSWORD}).json["error"] == "invalid_email"
    assert client.post("/api/users", headers=admin, json={"email": "x@example.com", "password": "short"}).json["error"] == "weak_password"
    listed = client.get("/api/users", headers=admin).json["users"]
    assert [u["uid"] for u in listed] == ["admin@example.com", "member@example.com", "new.person@example.com"]
    assert listed[0]["admin"] is True and listed[2] == {**listed[2], "admin": False, "active": True, "locked": False}
    assert PASSWORD not in client.get("/api/users", headers=admin).get_data(as_text=True) and "scrypt" not in str(listed)
    # Tài khoản mới đăng nhập được; admin đặt lại mật khẩu thì phiên cũ mất hiệu lực.
    login = client.post("/api/auth/login", json=new)
    session = {"Authorization": "Bearer " + login.json["token"]}
    me = client.get("/api/me", headers=session).json
    assert me["uid"] == "new.person@example.com" and me["admin"] is False
    replacement = "another long passphrase"
    assert client.post("/api/users/password", headers=admin, json={"email": new["email"], "password": replacement}).status_code == 200
    assert client.get("/api/me", headers=session).status_code == 401
    assert client.post("/api/auth/login", json={**new, "password": replacement}).status_code == 200
    # Vô hiệu hoá chặn đăng nhập; admin không tự khoá được chính mình.
    assert client.post("/api/users/active", headers=admin, json={"email": new["email"], "active": False}).json["status"] == "disabled"
    assert client.post("/api/auth/login", json={**new, "password": replacement}).status_code == 401
    assert client.post("/api/users/active", headers=admin, json={"email": new["email"], "active": True}).json["status"] == "enabled"
    assert client.post("/api/users/active", headers=admin, json={"email": "admin@example.com", "active": False}).json["error"] == "cannot_disable_self"
    assert client.post("/api/users/active", headers=admin, json={"email": "ghost@example.com", "active": False}).status_code == 404
    assert client.post("/api/users/password", headers=admin, json={"email": "ghost@example.com", "password": PASSWORD}).status_code == 404


def test_user_changes_own_password(vps):
    app, client, engine = vps
    member = sign_in(vps, "member@example.com")
    fresh = "a brand new passphrase"
    wrong = client.post("/api/auth/password", headers=member, json={"current_password": "not my password", "new_password": fresh})
    assert wrong.status_code == 401 and client.get("/api/me", headers=member).status_code == 200
    assert client.post("/api/auth/password", headers=member, json={"current_password": PASSWORD, "new_password": "short"}).json["error"] == "weak_password"
    assert client.post("/api/auth/password", headers=member, json={"current_password": PASSWORD, "new_password": fresh}).status_code == 200
    assert client.get("/api/me", headers=member).status_code == 401
    assert client.post("/api/auth/login", json={"email": "member@example.com", "password": PASSWORD}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "member@example.com", "password": fresh}).status_code == 200


def test_account_api_is_absent_without_local_provider(vps):
    app, client, engine = vps
    admin = sign_in(vps, "admin@example.com", admin=True)
    app.config["AUTH_PROVIDER"] = "firebase"
    app.config["TOKEN_VERIFIER"] = lambda token: {"uid": "admin@example.com", "admin": True}
    assert client.get("/api/users", headers=admin).status_code == 404
    assert client.post("/api/users", headers=admin, json={"email": "x@example.com", "password": PASSWORD}).status_code == 404


def test_login_rate_limit_per_address():
    auth_local.ip_attempts.clear()
    assert all(auth_local.allow_address("203.0.113.9", now=1000.0) for _ in range(auth_local.IP_ATTEMPTS))
    assert not auth_local.allow_address("203.0.113.9", now=1001.0)
    assert auth_local.allow_address("203.0.113.10", now=1001.0)
    assert auth_local.allow_address("203.0.113.9", now=1001.0 + auth_local.IP_WINDOW_SECONDS)
    auth_local.ip_attempts.clear()


def test_backend_checks_every_private_video_api(vps):
    app, client, engine = vps
    owner, viewer, stranger = sign_in(vps, "owner@example.com"), sign_in(vps, "viewer@example.com"), sign_in(vps, "stranger@example.com")
    admin = sign_in(vps, "admin@example.com", admin=True)
    video_id = ready_video(vps, owner)
    base = f"/api/videos/{video_id}"
    client.post(base + "/permissions", headers=owner, json={"viewer_uid": "viewer@example.com", "action": "grant"})
    for method, path in [("get", base), ("get", base + "/status"), ("get", base + "/playback"), ("get", base + "/thumbnail"), ("delete", base)]:
        assert getattr(client, method)(path).status_code == 401
        assert getattr(client, method)(path, headers=stranger).status_code == 404
    assert client.get(base + "/playback", headers=viewer).status_code == 200
    # Viewer được xem nhưng không được sửa quyền hay xoá.
    assert client.post(base + "/permissions", headers=viewer, json={"viewer_uid": "stranger@example.com", "action": "grant"}).status_code == 404
    assert client.delete(base, headers=viewer).status_code == 404
    assert client.get("/api/monitor", headers=owner).status_code == 403
    monitor = client.get("/api/monitor", headers=admin).json
    assert monitor["jobs"] == {"READY": 1} and monitor["storage_free_bytes"] > 0 and monitor["dead_messages"] == 0


# ---------- Storage riêng tư trên Windows ----------

@pytest.mark.parametrize("name", [
    "inputs/../secret", "inputs\\..\\secret", "inputs/C:/secret", "inputs/a/./b", "inputs//b", "/inputs/a",
    "outputs/NUL", "outputs/con.txt/a", "outputs/COM1", "inputs/trailing.", "inputs/a b", "other/a", "inputs", "",
])
def test_storage_rejects_traversal_and_windows_device_names(tmp_path, name):
    store = LocalStorage(tmp_path / "objects", "test-only-key")
    with pytest.raises(Exception) as error:
        store.path(name)
    assert error.value.code == 404


@windows_only
def test_storage_refuses_junction_pointing_outside(tmp_path):
    store = LocalStorage(tmp_path / "objects", "test-only-key")
    outside = tmp_path / "outside"
    outside.mkdir()
    (store.root / "inputs").mkdir()
    link = store.root / "inputs" / "escape"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True)
    with pytest.raises(Exception) as error:
        store.write("inputs/escape/stolen", io.BytesIO(b"data"), "video/mp4", 100)
    assert error.value.code == 404 and not list(outside.iterdir())
    os.rmdir(link)


def test_storage_unicode_paths_no_overwrite_and_delete(tmp_path):
    store = LocalStorage(tmp_path / "Thư mục có dấu" / "objects", "test-only-key")
    name = "inputs/video-01/source"
    store.write(name, io.BytesIO(b"first"), "video/mp4", 100)
    with pytest.raises(Exception) as error:
        store.write(name, io.BytesIO(b"second"), "video/mp4", 100)
    assert error.value.code == 409 and store.path(name).read_bytes() == b"first"
    assert store.head(name)["size_bytes"] == 5
    assert not list(store.path(name).parent.glob("*.tmp"))
    store.delete(name)
    store.delete(name)
    assert not (store.root / "inputs" / "video-01").exists() and (store.root / "inputs").is_dir()


def test_storage_full_and_configurable_upload_limit(vps, tmp_path):
    with pytest.raises(StorageFull):
        LocalStorage(tmp_path / "full", "test-only-key", min_free_bytes=10**15).write("inputs/a", io.BytesIO(b"x"), "video/mp4", 10)
    app, client, engine = vps
    owner = sign_in(vps, "owner@example.com")
    app.config["MAX_UPLOAD_BYTES"] = 64
    body = {"title": "Clip", "mime_type": "video/mp4"}
    assert client.get("/api/config").json["max_upload_bytes"] == 64
    assert client.post("/api/videos", headers=owner, json={**body, "size_bytes": 65}).status_code == 413
    assert client.post("/api/videos", headers=owner, json={**body, "size_bytes": 64}).status_code == 201
    app.extensions["storage"].min_free_bytes = 10**15
    full = client.post("/api/videos", headers=owner, json={**body, "size_bytes": 8})
    assert full.status_code == 507 and full.json["error"] == "storage_full"


def test_storage_is_never_a_static_route(vps):
    app, client, engine = vps
    owner = sign_in(vps, "owner@example.com")
    ready_video(vps, owner)
    store = app.extensions["storage"]
    assert not store.root.is_relative_to(Path(app.static_folder))
    name = next(p for p in (store.root / "outputs").rglob("mp4")).relative_to(store.root).as_posix()
    for path in ["/static/" + name, "/" + name, "/local-storage/read", "/local-storage/read?ticket=" + name]:
        assert client.get(path).status_code in {403, 404}


def test_range_playback_supports_seeking(vps):
    app, client, engine = vps
    owner = sign_in(vps, "owner@example.com")
    url = client.get(f"/api/videos/{ready_video(vps, owner)}/playback", headers=owner).json["url"]
    cases = [("bytes=0-4", 206, b"ready"), ("bytes=6-8", 206, b"mp4"), ("bytes=-7", 206, b"fixture"), (None, 200, b"ready-mp4-fixture")]
    for header, status, body in cases:
        response = client.get(url, headers={"Range": header} if header else {})
        assert response.status_code == status and response.data == body
        assert response.headers["Accept-Ranges"] == "bytes"
        response.close()
    response = client.get(url, headers={"Range": "bytes=500-"})
    assert response.status_code == 416
    response.close()


def test_owner_delete_removes_rows_and_files(vps):
    app, client, engine = vps
    owner = sign_in(vps, "owner@example.com")
    video_id = ready_video(vps, owner)
    store = app.extensions["storage"]
    PgBroker(engine).publish(uuid4(), {"job_id": "unrelated"})
    with Session(engine) as session, session.begin():
        job = session.scalar(select(TranscodeJob))
        job.status, job.lease_until = "PROCESSING", session.scalar(select(func.clock_timestamp())) + timedelta(minutes=5)
        PgBroker(engine).publish(uuid4(), {"job_id": str(job.id)})
    assert client.delete(f"/api/videos/{video_id}", headers=owner).json["error"] == "video_processing"
    with Session(engine) as session, session.begin():
        session.scalar(select(TranscodeJob)).status = "READY"
    assert client.delete(f"/api/videos/{video_id}", headers=owner).json["status"] == "deleted"
    assert client.delete(f"/api/videos/{video_id}", headers=owner).status_code == 404
    with Session(engine) as session:
        for model in [Video, TranscodeJob, OutputObject, OutboxEvent, VideoPermission]:
            assert session.scalar(select(func.count()).select_from(model)) == 0
        assert session.scalar(select(func.count()).select_from(QueueMessage)) == 1
    files = [p for p in store.root.rglob("*") if p.is_file() and p.name != ".signing-key"]
    assert files == []


# ---------- Hàng đợi PostgreSQL ----------

def test_pg_queue_visibility_restart_ack_and_dead_letter(schema_engine):
    broker = PgBroker(schema_engine, visibility_seconds=300)
    key = uuid4()
    broker.publish(key, {"job_id": "a"})
    first = broker.receive()
    assert first["operation_key"] == str(key) and first["payload"] == {"job_id": "a"} and first["deliveries"] == 1
    assert broker.receive() is None
    # Tiến trình khởi động lại: message chưa ack vẫn còn trong DB, chỉ đang ẩn.
    schema_engine.dispose()
    restarted = PgBroker(schema_engine, visibility_seconds=0)
    assert restarted.counts() == {"pending": 1, "dead": 0}
    with Session(schema_engine) as session, session.begin():
        session.scalar(select(QueueMessage)).visible_at = session.scalar(select(func.clock_timestamp()))
    again = restarted.receive()
    assert again["delivery_id"] == first["delivery_id"] and again["deliveries"] == 2
    restarted.ack(again)
    assert restarted.receive() is None and restarted.counts() == {"pending": 0, "dead": 0}
    restarted.publish(uuid4(), {"job_id": "b"})
    restarted.dead_letter(restarted.receive(), "invalid_job_message")
    assert restarted.receive() is None and restarted.counts() == {"pending": 0, "dead": 1}
    with pytest.raises(QueueError):
        restarted.publish(uuid4(), {"blob": "x" * 5000})
    with pytest.raises(ValueError):
        restarted.publish("not-a-uuid", {})


def test_pg_queue_concurrent_receivers_never_share_a_message(schema_engine):
    broker = PgBroker(schema_engine)
    for number in range(5):
        broker.publish(uuid4(), {"n": number})
    with ThreadPoolExecutor(max_workers=10) as pool:
        deliveries = [d for d in pool.map(lambda _: broker.receive(), range(10)) if d]
    assert len(deliveries) == 5 and len({d["delivery_id"] for d in deliveries}) == 5


def test_pg_queue_delivery_cap_is_bounded(schema_engine):
    broker = PgBroker(schema_engine, visibility_seconds=0)
    broker.publish(uuid4(), {"job_id": "poison"})
    for expected in range(1, MAX_DELIVERIES + 1):
        assert broker.receive()["deliveries"] == expected
    assert broker.receive() is None
    with Session(schema_engine) as session:
        assert session.scalar(select(QueueMessage.dead_reason)) == "delivery_exhausted"


# ---------- Worker FFmpeg native + pipeline ----------

@pytest.fixture
def native(schema_engine, tmp_path, seed_media):
    store = LocalStorage(tmp_path / "objects", "test-only-key")
    with Session(schema_engine) as session, session.begin():
        profile = OutputProfile(name="mp4-480p")
        session.add(profile)
        session.flush()
        profile_id = profile.id

    def enqueue(source=None):
        path = Path(source) if source else seed_media / "clip-01.mp4"
        video_id, job_id = uuid4(), uuid4()
        name = f"inputs/{video_id}/source"
        with path.open("rb") as stream:
            store.write(name, stream, "video/mp4", 50_000_000)
        generation = store.head(name)["generation"]
        payload = {"job_id": str(job_id), "source_generation": generation, "profile_id": str(profile_id)}
        with Session(schema_engine) as session, session.begin():
            session.add(Video(id=video_id, owner_uid="owner", title="Native clip", input_object=name, source_generation=generation,
                              size_bytes=path.stat().st_size, mime_type="video/mp4", status="QUEUED"))
            session.flush()
            session.add(TranscodeJob(id=job_id, video_id=video_id, source_generation=generation, profile_id=profile_id))
            session.flush()
            session.add(OutboxEvent(job_id=job_id, kind="transcode.requested", payload_json=payload))
        return {"video_id": video_id, "job_id": job_id, "payload": payload}

    return {"engine": schema_engine, "store": store, "work": tmp_path / "work", "enqueue": enqueue, "broker": PgBroker(schema_engine)}


def job_row(context, job_id):
    with Session(context["engine"]) as session:
        job = session.get(TranscodeJob, job_id)
        return {"status": job.status, "attempts": job.attempts, "error": job.last_error_code, "progress": job.progress_percent, "lease": job.lease_until}


@pytest.fixture(scope="module")
def heavy_clip(tmp_path_factory):
    """Clip 30 giây 1280x720 để FFmpeg chạy đủ lâu cho test timeout/huỷ."""
    if not shutil.which("ffmpeg"):
        pytest.skip("Real FFmpeg required")
    path = tmp_path_factory.mktemp("heavy") / "heavy.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-t", "30",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", str(path)], check=True, capture_output=True, timeout=120)
    return path


def processes_using(marker):
    """Tiến trình ffmpeg/python còn chạy mà dòng lệnh chứa thư mục của test này."""
    if WINDOWS:
        script = f"Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -like '*{marker}*' -and $_.Name -match 'ffmpeg|ffprobe|python' -and $_.ProcessId -ne {os.getpid()} }} | ForEach-Object {{ $_.Name }}"
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=60)
    else:
        result = subprocess.run(["pgrep", "-fl", marker], capture_output=True, text=True, timeout=30)
    return [line for line in result.stdout.splitlines() if line.strip() and "powershell" not in line.lower()]


@needs_ffmpeg
def test_native_worker_real_pipeline_with_pg_queue(native):
    item = native["enqueue"]()
    assert relay(native["engine"], native["broker"]) == 1
    assert dispatch_one(native["engine"], native["broker"], native["store"], native["work"], run_native, heartbeat=True) == "READY"
    state = job_row(native, item["job_id"])
    assert state["status"] == "READY" and state["attempts"] == 1 and state["progress"] == 100
    with Session(native["engine"]) as session:
        outputs = {o.kind: o for o in session.scalars(select(OutputObject))}
        assert set(outputs) == {"mp4", "thumbnail"} and outputs["mp4"].duration_ms > 0
        assert session.get(Video, item["video_id"]).status == "READY"
    streams = probe(native["store"].path(outputs["mp4"].storage_object))["streams"]
    assert any(s["codec_name"] == "h264" for s in streams)
    assert native["store"].path(outputs["thumbnail"].storage_object).read_bytes().startswith(b"\xff\xd8")
    # Message đã ack, thư mục tạm đã dọn, giao lại message trùng là no-op.
    assert native["broker"].counts() == {"pending": 0, "dead": 0}
    assert not list(native["work"].rglob("source"))
    native["broker"].publish(uuid4(), item["payload"])
    assert dispatch_one(native["engine"], native["broker"], native["store"], native["work"], run_native, heartbeat=True) == "no_op"
    assert job_row(native, item["job_id"])["attempts"] == 1


@needs_ffmpeg
def test_native_worker_rejects_invalid_video_once(native, tmp_path):
    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"this is not a video" * 10)
    item = native["enqueue"](corrupt)
    relay(native["engine"], native["broker"])
    assert dispatch_one(native["engine"], native["broker"], native["store"], native["work"], run_native, heartbeat=True) == "FAILED"
    state = job_row(native, item["job_id"])
    assert state["attempts"] == 1 and state["error"] == "invalid_media"
    with Session(native["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(OutputObject)) == 0


@needs_ffmpeg
def test_worker_loop_drains_backlog_one_at_a_time(native):
    items = [native["enqueue"]() for _ in range(3)]
    stop = threading.Event()
    running, peak = [0], [0]

    def counting_runner(source, output, attempt, on_progress):
        running[0] += 1
        peak[0] = max(peak[0], running[0])
        try:
            return run_native(source, output, attempt, on_progress)
        finally:
            running[0] -= 1

    worker = threading.Thread(target=run_worker, args=(native["engine"], native["broker"], native["store"], native["work"], stop),
                              kwargs={"runner": counting_runner, "poll_seconds": 0.2})
    worker.start()
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline and any(job_row(native, i["job_id"])["status"] != "READY" for i in items):
            time.sleep(0.3)
    finally:
        stop.set()
        worker.join(timeout=60)
    assert not worker.is_alive()
    assert [job_row(native, i["job_id"])["status"] for i in items] == ["READY"] * 3
    assert all(job_row(native, i["job_id"])["attempts"] == 1 for i in items) and peak[0] == 1
    with Session(native["engine"]) as session:
        # Không job nào bị publish lại vì chờ lâu trong hàng đợi.
        assert max(session.scalars(select(OutboxEvent.publish_attempts))) == 1


@needs_ffmpeg
def test_worker_restart_recovers_abandoned_job(native):
    item = native["enqueue"]()
    relay(native["engine"], native["broker"])
    delivery = native["broker"].receive()
    claim = claim_job(native["engine"], delivery["payload"])
    assert claim and job_row(native, item["job_id"])["status"] == "PROCESSING"
    # Worker "chết" ở đây: không ack, không kết quả. Cho lease hết hạn rồi khởi động worker mới.
    with Session(native["engine"]) as session, session.begin():
        session.get(TranscodeJob, item["job_id"]).lease_until = session.scalar(select(func.clock_timestamp())) - timedelta(seconds=1)
    stop = threading.Event()
    worker = threading.Thread(target=run_worker, args=(native["engine"], native["broker"], native["store"], native["work"], stop), kwargs={"poll_seconds": 0.3})
    worker.start()
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and job_row(native, item["job_id"])["status"] != "READY":
            time.sleep(0.3)
    finally:
        stop.set()
        worker.join(timeout=60)
    state = job_row(native, item["job_id"])
    assert state["status"] == "READY" and state["attempts"] == 2
    with Session(native["engine"]) as session:
        outputs = list(session.scalars(select(OutputObject.storage_object)))
        assert len(outputs) == 2 and all(claim["attempt_id"].hex not in name for name in outputs)


@needs_ffmpeg
def test_heartbeat_extends_lease_reports_progress_and_detects_loss(native):
    item = native["enqueue"]()
    claim = claim_job(native["engine"], item["payload"])
    before = job_row(native, item["job_id"])["lease"]
    time.sleep(0.05)
    assert touch_lease(native["engine"], claim, 42) is True
    state = job_row(native, item["job_id"])
    assert state["lease"] > before and state["progress"] == 42
    with Session(native["engine"]) as session, session.begin():
        session.get(TranscodeJob, item["job_id"]).current_attempt_id = uuid4()
    assert touch_lease(native["engine"], claim, 50) is False
    assert job_row(native, item["job_id"])["progress"] == 42


@needs_ffmpeg
def test_ffmpeg_timeout_stops_the_whole_process_tree(heavy_clip, tmp_path):
    output = tmp_path / ("timeout-" + uuid4().hex)
    started = time.monotonic()
    with pytest.raises(MediaError) as error:
        run_native(heavy_clip, output, uuid4(), timeout=1.5)
    assert error.value.code == "worker_timeout" and error.value.retryable
    assert time.monotonic() - started < 30
    assert processes_using(output.name) == []
    # Không còn tiến trình nào giữ file: xoá được ngay và không có metadata "đã kiểm tra".
    assert not (output / "metadata.json").exists()
    shutil.rmtree(output, ignore_errors=False) if output.exists() else None


@needs_ffmpeg
def test_cancelled_job_stops_ffmpeg(heavy_clip, tmp_path, monkeypatch):
    monkeypatch.setattr(worker_native, "HEARTBEAT_SECONDS", 0.3)
    output = tmp_path / ("cancel-" + uuid4().hex)
    calls = []
    with pytest.raises(MediaError) as error:
        run_native(heavy_clip, output, uuid4(), on_progress=lambda percent: calls.append(percent) or False)
    assert error.value.code == "worker_cancelled" and len(calls) == 1
    assert processes_using(output.name) == []


@needs_ffmpeg
@windows_only
def test_worker_death_does_not_leave_ffmpeg_running(heavy_clip, tmp_path):
    output = tmp_path / ("orphan-" + uuid4().hex)
    code = "import sys; from uuid import uuid4; from app.worker_native import run_native; run_native(sys.argv[1], sys.argv[2], uuid4())"
    parent = subprocess.Popen([sys.executable, "-c", code, str(heavy_clip), str(output)], cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 40
        seen = []
        while time.monotonic() < deadline and not any("ffmpeg" in name for name in seen):
            seen = processes_using(output.name)
        assert any("ffmpeg" in name for name in seen), "FFmpeg must actually be running before the worker is killed"
    finally:
        parent.kill()
        parent.wait(timeout=15)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and processes_using(output.name):
        time.sleep(0.5)
    assert processes_using(output.name) == []


@needs_ffmpeg
@windows_only
def test_ffmpeg_is_confined_to_two_cpus(heavy_clip, tmp_path, monkeypatch):
    if os.cpu_count() <= 2:
        pytest.skip("Needs more than two logical CPUs to observe the cap")
    monkeypatch.setenv("FFMPEG_THREADS", "2")
    assert bin(worker_native.cpu_mask(2)).count("1") == 2 and worker_native.cpu_mask(os.cpu_count()) == 0
    output = tmp_path / ("affinity-" + uuid4().hex)
    script = (f"Get-CimInstance Win32_Process | Where-Object {{ $_.Name -eq 'ffmpeg.exe' -and $_.CommandLine -like '*{output.name}*' }} | "
              "ForEach-Object { (Get-Process -Id $_.ProcessId).ProcessorAffinity.ToInt64() }")
    masks = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run_native, heavy_clip, output, uuid4())
        while not future.done() and not masks:
            found = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=60).stdout.split()
            masks = [int(value) for value in found if value.isdigit()]
        metadata = future.result(timeout=300)
    assert masks, "FFmpeg must be observed while it is encoding"
    assert all(bin(mask).count("1") == 2 for mask in masks)
    assert metadata["duration_ms"] > 29_000


def test_ffmpeg_settings_are_bounded(monkeypatch):
    monkeypatch.delenv("FFMPEG_THREADS", raising=False)
    assert transcode_module.threads() == "1"
    for value, expected in [("2", "2"), ("8", "2"), ("0", "1"), ("many", "1")]:
        monkeypatch.setenv("FFMPEG_THREADS", value)
        assert transcode_module.threads() == expected
    monkeypatch.setenv("TRANSCODE_TIMEOUT_SECONDS", "999999")
    assert transcode_module.encode_timeout() == 3600
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "200000000")
    assert transcode_module.max_input_bytes() == 200_000_000
    # File .env của máy dev có thể đã đặt sẵn FFPROBE_BIN; test này kiểm tra giá trị mặc định.
    monkeypatch.delenv("FFPROBE_BIN", raising=False)
    monkeypatch.setenv("FFMPEG_BIN", r"C:\Tools\ffmpeg\bin\ffmpeg.exe")
    assert transcode_module.tool("ffmpeg") == r"C:\Tools\ffmpeg\bin\ffmpeg.exe" and transcode_module.tool("ffprobe") == "ffprobe"


def test_single_worker_lock(schema_engine):
    first = single_worker_lock(schema_engine)
    assert first is not None
    assert single_worker_lock(schema_engine) is None
    first.close()
    second = single_worker_lock(schema_engine)
    assert second is not None
    second.close()


# ---------- Migration, dọn dẹp, cấu hình production, log ----------

def test_upgrade_schema_is_additive_and_repeatable(schema_engine):
    schema = schema_engine.get_execution_options()["schema_translate_map"][None]
    video_id = uuid4()
    with Session(schema_engine) as session, session.begin():
        session.add(Video(id=video_id, owner_uid="owner", title="Kept", input_object="inputs/x/y", source_generation="v1", size_bytes=1, mime_type="video/mp4"))
    # Giả lập DB của Phase 02-06: chưa có cột tiến độ và các bảng mới.
    with schema_engine.begin() as connection:
        connection.execute(text(f'ALTER TABLE "{schema}"."transcode_jobs" DROP COLUMN "progress_percent"'))
        for table in ["queue_messages", "auth_sessions", "users"]:
            connection.execute(text(f'DROP TABLE "{schema}"."{table}"'))
    for _ in range(2):
        upgrade_schema(schema_engine)
    columns = {c["name"] for c in inspect(schema_engine).get_columns("transcode_jobs", schema=schema)}
    assert "progress_percent" in columns
    assert {"queue_messages", "auth_sessions", "users"} <= set(inspect(schema_engine).get_table_names(schema=schema))
    with Session(schema_engine) as session:
        assert session.get(Video, video_id).title == "Kept"
        # DB mới phải có đúng một profile mặc định, nếu không thì không tạo được job nào.
        assert list(session.scalars(select(OutputProfile.name))) == ["mp4-480p"]


def test_cleanup_removes_only_old_unreferenced_data(vps, tmp_path):
    app, client, engine = vps
    owner = sign_in(vps, "owner@example.com")
    ready_video(vps, owner)
    store = app.extensions["storage"]
    two_days_ago = time.time() - 48 * 3600
    work = tmp_path / "work"
    old, fresh = work / "job-a" / "attempt-old", work / "job-a" / "attempt-fresh"
    for folder in [old, fresh]:
        (folder / "input").mkdir(parents=True)
        (folder / "input" / "source").write_bytes(b"temporary")
    os.utime(old, (two_days_ago, two_days_ago))
    assert cleanup_work(work) == 1 and not old.exists() and fresh.exists()
    assert cleanup_work(tmp_path / "missing") == 0
    # Upload bỏ dở: một cũ, một mới.
    body = {"title": "Abandoned", "mime_type": "video/mp4", "size_bytes": 8}
    abandoned = client.post("/api/videos", headers=owner, json=body).json
    client.put(abandoned["upload_url"], data=b"12345678", content_type="video/mp4")
    recent = client.post("/api/videos", headers=owner, json=body).json
    with Session(engine) as session, session.begin():
        row = session.scalar(select(Video).where(Video.id == abandoned["video_id"]))
        row.created_at = row.created_at - timedelta(hours=48)
        abandoned_object = row.input_object
    assert cleanup_uploads(engine, store) == 1
    assert not store.path(abandoned_object).exists()
    with Session(engine) as session:
        assert {str(v.id) for v in session.scalars(select(Video).where(Video.status == "PENDING_UPLOAD"))} == {recent["video_id"]}
    # Output mồ côi cũ bị xoá; output đã publish được giữ.
    with Session(engine) as session:
        published = session.scalar(select(OutputObject.storage_object))
    orphan = store.root / "outputs" / uuid4().hex / uuid4().hex
    orphan.mkdir(parents=True)
    (orphan / "video.mp4").write_bytes(b"partial")
    os.utime(orphan, (two_days_ago, two_days_ago))
    os.utime(store.path(published).parent, (two_days_ago, two_days_ago))
    assert cleanup_outputs(engine, store) == 1
    assert not orphan.exists() and store.path(published).is_file()


def test_production_requires_private_absolute_paths(monkeypatch, tmp_path):
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    good = {"STORAGE_ROOT": tmp_path / "storage" / "objects", "WORK_ROOT": tmp_path / "storage" / "temporary", "AUTH_PROVIDER": "local"}
    app = create_app(dict(good))
    assert app.config["MAX_UPLOAD_BYTES"] == 50_000_000 and app.test_client().get("/health").status_code == 503
    for bad in [{}, {**good, "STORAGE_ROOT": "relative/objects"}, {**good, "STORAGE_ROOT": ROOT / "app" / "static" / "videos"},
                {**good, "WORK_ROOT": ROOT / ".local" / "work"}, {**good, "AUTH_PROVIDER": "none"}]:
        with pytest.raises(ValueError):
            create_app(bad)
    # File queue vẫn chỉ dành cho máy dev; production dùng hàng đợi PostgreSQL.
    with pytest.raises(RuntimeError):
        FileBroker(tmp_path / "queue")
    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(ValueError):
        create_app(dict(good))
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("K_SERVICE", "cloud-run")
    with pytest.raises(ValueError):
        create_app(dict(good))


def test_logs_are_json_rotated_and_redacted(tmp_path):
    root = logging.getLogger()
    saved = list(root.handlers), root.level
    try:
        configure_logging(tmp_path, "sample", megabytes=0.002, backups=2)
        log = logging.getLogger("app.sample")
        log.info("GET /local-storage/read?ticket=PRIVATE-TICKET-VALUE done")
        log.info("Authorization: Bearer PRIVATE.TOKEN.VALUE")
        log.error(json.dumps({"event": "login_failed", "password": "PRIVATE-PASSWORD"}))
        for number in range(200):
            log.info(json.dumps({"event": "filler", "number": number}))
        for handler in root.handlers:
            handler.flush()
        files = sorted(p.name for p in tmp_path.iterdir())
        content = "".join(p.read_text(encoding="utf-8") for p in tmp_path.iterdir())
    finally:
        for handler in list(root.handlers):
            handler.close()
            root.removeHandler(handler)
        for handler in saved[0]:
            root.addHandler(handler)
        root.setLevel(saved[1])
    assert "sample.log" in files and "sample.log.1" in files and "sample-error.log" in files
    assert len([name for name in files if name.startswith("sample.log")]) <= 3
    assert all(secret not in content for secret in ["PRIVATE-TICKET-VALUE", "PRIVATE.TOKEN.VALUE", "PRIVATE-PASSWORD"])
    assert all(isinstance(json.loads(line), dict) for line in content.splitlines())


def test_admin_cli_manages_accounts_without_showing_passwords(vps):
    app, client, engine = vps
    runner = app.test_cli_runner()
    typed = f"{PASSWORD}\n{PASSWORD}\n"
    created = runner.invoke(args=["create-user", "Cli@Example.com", "--admin"], input=typed)
    assert created.exit_code == 0 and "cli@example.com" in created.output and PASSWORD not in created.output
    assert runner.invoke(args=["create-user", "cli@example.com"], input=typed).exit_code != 0
    assert runner.invoke(args=["create-user", "weak@example.com"], input="short\nshort\n").exit_code != 0
    login = client.post("/api/auth/login", json={"email": "cli@example.com", "password": PASSWORD})
    old = {"Authorization": "Bearer " + login.json["token"]}
    assert client.get("/api/me", headers=old).json["admin"] is True
    new_password = "a completely different passphrase"
    assert runner.invoke(args=["set-password", "cli@example.com"], input=f"{new_password}\n{new_password}\n").exit_code == 0
    assert client.get("/api/me", headers=old).status_code == 401
    assert client.post("/api/auth/login", json={"email": "cli@example.com", "password": new_password}).status_code == 200
    assert runner.invoke(args=["disable-user", "cli@example.com"]).exit_code == 0
    assert client.post("/api/auth/login", json={"email": "cli@example.com", "password": new_password}).status_code == 401
    assert runner.invoke(args=["enable-user", "cli@example.com"]).exit_code == 0
    status = runner.invoke(args=["system-status"])
    assert status.exit_code == 0 and "queue: {'pending': 0, 'dead': 0}" in status.output
    assert runner.invoke(args=["cleanup", "--max-age-hours", "1"]).exit_code == 0


@windows_only
@pytest.mark.skipif(not shutil.which("pg_dump"), reason="PostgreSQL client tools (pg_dump/pg_restore/psql) required")
def test_backup_and_restore_scripts_round_trip(schema_engine, tmp_path):
    """Chạy đúng hai script vận hành trên PostgreSQL thật: dump -> kiểm tra -> khôi phục vào DB thử -> so số dòng."""
    engine = create_app().extensions["db_engine"]
    upgrade_schema(engine)
    with engine.connect() as connection:
        expected = {table: connection.execute(text(f"SELECT count(*) FROM public.{table}")).scalar()
                    for table in ["videos", "transcode_jobs", "output_objects", "video_permissions", "outbox_events", "users"]}
    engine.dispose()
    scripts = ROOT / "scripts" / "windows"
    common = ["-EnvFile", str(ROOT / ".env"), "-Root", str(tmp_path / "portal"), "-PostgresBin", str(Path(shutil.which("pg_dump")).parent)]

    def run(script, *arguments):
        return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(scripts / script), *arguments, *common],
                              capture_output=True, text=True, timeout=300)

    backups = tmp_path / "backups"
    backup = run("backup.ps1", "-BackupDir", str(backups))
    assert backup.returncode == 0 and "BACKUP OK" in backup.stdout, backup.stdout + backup.stderr
    dump = next(backups.glob("videoportal-*.dump"))
    assert dump.stat().st_size > 0 and (backups / (dump.name + ".sha256")).is_file() and not list(backups.glob("*.partial"))
    target = "videoportal_drill_" + uuid4().hex[:12]
    restore = run("restore.ps1", "-DumpFile", str(dump), "-TargetDatabase", target, "-DropAfterVerify")
    assert restore.returncode == 0 and "RESTORE OK" in restore.stdout, restore.stdout + restore.stderr
    counts = json.loads(next(line for line in restore.stdout.splitlines() if line.startswith("RESTORE_COUNTS ")).split(" ", 1)[1])
    assert counts == expected
    # File dump bị sửa: script phải dừng trước khi tạo database.
    with dump.open("ab") as stream:
        stream.write(b"tampered")
    damaged = "videoportal_drill_" + uuid4().hex[:12]
    refused = run("restore.ps1", "-DumpFile", str(dump), "-TargetDatabase", damaged)
    assert refused.returncode != 0 and "SHA256 mismatch" in refused.stdout + refused.stderr
    live = run("restore.ps1", "-DumpFile", str(dump), "-TargetDatabase", "video_portal")
    assert live.returncode != 0
    engine = create_app().extensions["db_engine"]
    with engine.connect() as connection:
        leftovers = connection.execute(text("SELECT count(*) FROM pg_database WHERE datname IN (:a, :b)"), {"a": target, "b": damaged}).scalar()
    engine.dispose()
    assert leftovers == 0


# ---------- Tiến trình thật: worker service và Waitress ----------

def service_environment(schema_engine, tmp_path):
    """Môi trường cho tiến trình con: cùng DB test nhưng chỉ nhìn thấy schema riêng của test này."""
    schema = schema_engine.get_execution_options()["schema_translate_map"][None]
    environment = dict(os.environ)
    environment.update({"PGOPTIONS": f"-c search_path={schema}", "APP_ENV": "local", "AUTH_PROVIDER": "local",
                        "STORAGE_ROOT": str(tmp_path / "objects"), "WORK_ROOT": str(tmp_path / "work"), "LOG_DIR": str(tmp_path / "logs")})
    return environment


def wait_for_log(path, marker, seconds=40):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.is_file() and marker in path.read_text(encoding="utf-8", errors="replace"):
            return True
        time.sleep(0.3)
    return False


def stop_process(process):
    """Gửi tín hiệu dừng giống service manager: Ctrl+Break trên Windows, SIGTERM trên hệ khác."""
    process.send_signal(signal.CTRL_BREAK_EVENT if WINDOWS else signal.SIGTERM)
    return process.wait(timeout=30)


def test_worker_service_graceful_shutdown_and_single_instance(schema_engine, tmp_path):
    environment = service_environment(schema_engine, tmp_path)
    flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {}
    command = [sys.executable, "-m", "app.worker_service"]
    log = tmp_path / "logs" / "worker.log"
    worker = subprocess.Popen(command, cwd=ROOT, env=environment, **flags)
    try:
        assert wait_for_log(log, "worker_started"), "worker did not start"
        second = subprocess.run(command, cwd=ROOT, env=environment, timeout=60)
        assert second.returncode == 3
        assert "another_worker_is_running" in log.read_text(encoding="utf-8")
        assert stop_process(worker) == 0
    finally:
        if worker.poll() is None:
            worker.kill()
    assert "worker_stopped" in log.read_text(encoding="utf-8")


def test_waitress_serves_on_loopback_and_stops(schema_engine, tmp_path):
    with socket.socket() as probe_socket:
        probe_socket.bind(("127.0.0.1", 0))
        port = probe_socket.getsockname()[1]
    environment = service_environment(schema_engine, tmp_path) | {"BIND_PORT": str(port)}
    flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {}
    server = subprocess.Popen([sys.executable, "-m", "app.serve"], cwd=ROOT, env=environment, **flags)
    try:
        response = None
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and response is None:
            try:
                response = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3)
            except OSError:
                time.sleep(0.3)
        assert response is not None and response.status == 200
        assert json.loads(response.read())["database"] == "ok"
        assert "waitress" not in (response.headers.get("Server") or "").lower()
        login = urllib.request.Request(f"http://127.0.0.1:{port}/api/auth/login", data=b'{"email":"nobody@example.com","password":"x"}',
                                       headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(login, timeout=10)
        assert error.value.code == 401
        assert wait_for_log(tmp_path / "logs" / "api.log", '"path": "/health"')
    finally:
        if server.poll() is None:
            server.send_signal(signal.CTRL_BREAK_EVENT if WINDOWS else signal.SIGTERM)
            try:
                server.wait(timeout=20)
            except subprocess.TimeoutExpired:
                server.kill()
    # Log truy cập chỉ có path/status; thân request (email, mật khẩu) không bao giờ được ghi.
    logged = (tmp_path / "logs" / "api.log").read_text(encoding="utf-8")
    assert "nobody@example.com" not in logged and "password" not in logged

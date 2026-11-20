from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import OutboxEvent, OutputObject, OutputProfile, TranscodeJob, Video, VideoPermission
from app.pipeline import claim_job, dispatch_one, execute_claim, reconcile, relay, retry_failed_job
from app.queue_local import FileBroker, QueueError
from app.storage import LocalStorage
from app.worker_runner import run_container
from worker.transcode import MediaError, probe, transcode


class SimulatedCrash(BaseException):
    pass


class FakeBroker:
    """Test-only transport; production code never imports this fake."""
    def __init__(self):
        self.pending = deque()
        self.acked = []
        self.dead = []
        self.fail_publish = False
        self.crash_after_publish = False
        self.fail_ack = False

    def publish(self, key, payload):
        if self.fail_publish:
            raise QueueError("simulated_publish_failure")
        self.pending.append({"operation_key": key, "payload": dict(payload), "delivery_id": str(uuid4())})
        if self.crash_after_publish:
            self.crash_after_publish = False
            raise SimulatedCrash()

    def receive(self):
        return self.pending[0] if self.pending else None

    def ack(self, delivery):
        if self.fail_ack:
            raise QueueError("simulated_ack_failure")
        self.acked.append(delivery)
        self.pending.remove(delivery)

    def dead_letter(self, delivery, reason):
        self.dead.append(reason)
        self.pending.remove(delivery)


def real_host_runner(source, output, attempt):
    return transcode(source, output)


@pytest.fixture
def pipeline(schema_engine, tmp_path, seed_media):
    app = create_app({"TESTING": True, "TOKEN_VERIFIER": lambda token: {"uid": token}})
    app.extensions["db_engine"] = schema_engine
    store = LocalStorage(tmp_path / "objects", "test-only-key")
    app.extensions["storage"] = store
    with Session(schema_engine) as session, session.begin():
        profile = OutputProfile(name="mp4-480p")
        session.add(profile)
        session.flush()
        profile_id = profile.id

    def enqueue(source=None, max_attempts=3):
        path = Path(source) if source else seed_media / "clip-01.mp4"
        video_id, job_id, event_id = uuid4(), uuid4(), uuid4()
        name = f"inputs/{video_id}/source"
        with path.open("rb") as stream:
            store.write(name, stream, "video/mp4", 50_000_000)
        metadata = store.head(name)
        payload = {"job_id": str(job_id), "source_generation": metadata["generation"], "profile_id": str(profile_id)}
        with Session(schema_engine) as session, session.begin():
            session.add(Video(id=video_id, owner_uid="owner", title="Pipeline real clip", input_object=name, source_generation=metadata["generation"], size_bytes=path.stat().st_size, mime_type="video/mp4", status="QUEUED"))
            session.flush()
            session.add(TranscodeJob(id=job_id, video_id=video_id, source_generation=metadata["generation"], profile_id=profile_id, max_attempts=max_attempts))
            session.add(VideoPermission(video_id=video_id, viewer_uid="viewer"))
            session.flush()
            session.add(OutboxEvent(id=event_id, job_id=job_id, kind="transcode.requested", payload_json=payload))
        return {"video_id": video_id, "job_id": job_id, "event_id": event_id, "payload": payload}

    return {"engine": schema_engine, "store": store, "work": tmp_path / "work", "app": app, "enqueue": enqueue}


def dispatch(context, broker, runner=real_host_runner):
    return dispatch_one(context["engine"], broker, context["store"], context["work"], runner=runner)


def job_state(context, job_id):
    with Session(context["engine"]) as session:
        job = session.get(TranscodeJob, job_id)
        return {"status": job.status, "attempts": job.attempts, "due": job.lease_until, "attempt_id": job.current_attempt_id, "error": job.last_error_code}


def run_due_retry(context, job_id):
    state = job_state(context, job_id)
    return reconcile(context["engine"], now=state["due"] + timedelta(seconds=1))


def test_relay_duplicates_one_logical_result(pipeline):
    item = pipeline["enqueue"]()
    broker = FakeBroker()
    assert relay(pipeline["engine"], broker) == 1
    broker.publish(str(item["event_id"]), item["payload"])
    assert dispatch(pipeline, broker) == "READY"
    assert dispatch(pipeline, broker) == "no_op"
    state = job_state(pipeline, item["job_id"])
    assert state["attempts"] == 1
    with Session(pipeline["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(OutputObject)) == 2
        assert session.get(Video, item["video_id"]).status == "READY"
        assert session.get(OutboxEvent, item["event_id"]).published_at is not None


def test_relay_crash_after_publish_redelivers_safely(pipeline):
    item = pipeline["enqueue"]()
    broker = FakeBroker()
    broker.crash_after_publish = True
    with pytest.raises(SimulatedCrash):
        relay(pipeline["engine"], broker)
    with Session(pipeline["engine"]) as session:
        assert session.get(OutboxEvent, item["event_id"]).published_at is None
    assert relay(pipeline["engine"], broker) == 1
    assert len(broker.pending) == 2
    assert len({m["operation_key"] for m in broker.pending}) == 1
    assert dispatch(pipeline, broker) == "READY"
    assert dispatch(pipeline, broker) == "no_op"
    assert job_state(pipeline, item["job_id"])["attempts"] == 1


def test_concurrent_claim_and_stale_attempt_fencing(pipeline):
    item = pipeline["enqueue"]()
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: claim_job(pipeline["engine"], item["payload"]), range(2)))
    first = next(c for c in claims if c)
    assert sum(c is not None for c in claims) == 1
    assert run_due_retry(pipeline, item["job_id"]) == 1
    assert job_state(pipeline, item["job_id"])["status"] == "RETRYING"
    run_due_retry(pipeline, item["job_id"])
    second = claim_job(pipeline["engine"], item["payload"])
    assert second["attempt_id"] != first["attempt_id"]
    assert execute_claim(pipeline["engine"], pipeline["store"], first, pipeline["work"], runner=real_host_runner) == "stale"
    assert execute_claim(pipeline["engine"], pipeline["store"], second, pipeline["work"], runner=real_host_runner) == "READY"
    assert job_state(pipeline, item["job_id"])["attempts"] == 2
    with Session(pipeline["engine"]) as session:
        paths = list(session.scalars(select(OutputObject.storage_object)))
        assert len(paths) == 2 and all(second["attempt_id"].hex in p for p in paths)


@pytest.mark.parametrize("point", ["mp4", "staging"])
def test_crash_before_atomic_publish_keeps_playback_private(pipeline, monkeypatch, point):
    item = pipeline["enqueue"]()
    broker = FakeBroker()
    relay(pipeline["engine"], broker)
    if point == "mp4":
        def crash_runner(source, output, attempt):
            output.mkdir(parents=True)
            (output / "video.mp4").write_bytes(b"partial")
            raise SimulatedCrash()
        runner = crash_runner
    else:
        original = pipeline["store"].head
        def crash_after_staging(name):
            result = original(name)
            if name.startswith("outputs/") and name.endswith("thumbnail.jpg"):
                raise SimulatedCrash()
            return result
        monkeypatch.setattr(pipeline["store"], "head", crash_after_staging)
        runner = real_host_runner
    with pytest.raises(SimulatedCrash):
        dispatch(pipeline, broker, runner)
    assert not broker.acked
    with Session(pipeline["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(OutputObject)) == 0
    client = pipeline["app"].test_client()
    assert client.get(f"/api/videos/{item['video_id']}/playback", headers={"Authorization": "Bearer owner"}).status_code == 409
    monkeypatch.undo()
    run_due_retry(pipeline, item["job_id"])
    run_due_retry(pipeline, item["job_id"])
    assert dispatch(pipeline, broker) == "READY"
    assert job_state(pipeline, item["job_id"])["attempts"] == 2


def test_bounded_retry_backoff_and_explicit_operator_recovery(pipeline):
    item = pipeline["enqueue"]()
    broker = FakeBroker()
    def transient(*args):
        raise MediaError("temporary_worker_failure", retryable=True)
    for attempt in range(1, 4):
        relay(pipeline["engine"], broker)
        assert dispatch(pipeline, broker, transient) == ("RETRYING" if attempt < 3 else "FAILED")
        state = job_state(pipeline, item["job_id"])
        assert state["attempts"] == attempt
        if attempt < 3:
            assert claim_job(pipeline["engine"], item["payload"]) is None
            assert reconcile(pipeline["engine"], now=state["due"] - timedelta(seconds=1)) == 0
            run_due_retry(pipeline, item["job_id"])
    broker.publish(str(item["event_id"]), item["payload"])
    assert dispatch(pipeline, broker) == "no_op"
    assert job_state(pipeline, item["job_id"])["attempts"] == 3
    retry_failed_job(pipeline["engine"], item["job_id"])
    relay(pipeline["engine"], broker)
    assert dispatch(pipeline, broker) == "READY"
    with pytest.raises(ValueError):
        retry_failed_job(pipeline["engine"], item["job_id"])


def test_permanent_bad_media_is_failed_once(pipeline, tmp_path):
    source = tmp_path / "corrupt.mp4"
    source.write_bytes(b"not a video")
    item = pipeline["enqueue"](source)
    broker = FakeBroker()
    relay(pipeline["engine"], broker)
    assert dispatch(pipeline, broker) == "FAILED"
    assert job_state(pipeline, item["job_id"])["attempts"] == 1


def test_failed_publish_is_bounded_and_operator_visible(pipeline):
    item = pipeline["enqueue"]()
    broker = FakeBroker()
    broker.fail_publish = True
    for _ in range(8):
        relay(pipeline["engine"], broker)
    assert job_state(pipeline, item["job_id"])["status"] == "FAILED"
    with Session(pipeline["engine"]) as session:
        event = session.get(OutboxEvent, item["event_id"])
        assert event.publish_attempts == 5 and event.last_error == "publish_exhausted"


def test_lost_dispatch_republished_but_never_unbounded(pipeline):
    item = pipeline["enqueue"]()
    broker = FakeBroker()
    for _ in range(5):
        relay(pipeline["engine"], broker)
        broker.pending.clear()
        run_due_retry(pipeline, item["job_id"])
    assert job_state(pipeline, item["job_id"])["status"] == "FAILED"
    assert job_state(pipeline, item["job_id"])["error"] == "dispatch_exhausted"


def test_ack_failure_after_ready_redelivery_noop(pipeline):
    item = pipeline["enqueue"]()
    broker = FakeBroker()
    relay(pipeline["engine"], broker)
    broker.fail_ack = True
    with pytest.raises(QueueError):
        dispatch(pipeline, broker)
    assert job_state(pipeline, item["job_id"])["status"] == "READY"
    broker.fail_ack = False
    assert dispatch(pipeline, broker) == "no_op"
    assert job_state(pipeline, item["job_id"])["attempts"] == 1


def test_invalid_delivery_dead_lettered(pipeline):
    item = pipeline["enqueue"]()
    broker = FakeBroker()
    broker.publish(str(item["event_id"]), item["payload"] | {"source_generation": "wrong-version"})
    assert dispatch(pipeline, broker) == "dead_letter"
    assert broker.dead == ["invalid_job_message"]
    assert job_state(pipeline, item["job_id"])["attempts"] == 0


def test_file_broker_restart_ack_and_production_guard(tmp_path, monkeypatch):
    root = tmp_path / "queue"
    FileBroker(root).publish(str(uuid4()), {"job_id": str(uuid4())})
    restarted = FileBroker(root)
    delivery = restarted.receive()
    assert delivery
    restarted.ack(delivery)
    assert FileBroker(root).receive() is None
    (restarted.pending / "broken.json").write_text("not-json")
    restarted.dead_letter(restarted.receive(), "invalid_message")
    assert len(list(restarted.dead.glob("*.json"))) == 1
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError):
        FileBroker(root)
    with pytest.raises(ValueError):
        create_app({})


def test_output_transaction_rollback_recovers_without_partial_pointers(pipeline):
    item = pipeline["enqueue"]()
    claim = claim_job(pipeline["engine"], item["payload"])
    def fail_insert(*args):
        raise SQLAlchemyError("injected commit failure")
    event.listen(OutputObject, "before_insert", fail_insert)
    try:
        with pytest.raises(SQLAlchemyError):
            execute_claim(pipeline["engine"], pipeline["store"], claim, pipeline["work"], real_host_runner)
    finally:
        event.remove(OutputObject, "before_insert", fail_insert)
    with Session(pipeline["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(OutputObject)) == 0
        assert session.get(TranscodeJob, item["job_id"]).status == "PROCESSING"
    run_due_retry(pipeline, item["job_id"])
    run_due_retry(pipeline, item["job_id"])
    broker = FakeBroker()
    relay(pipeline["engine"], broker)
    assert dispatch(pipeline, broker) == "READY"


def test_source_change_is_permanent_and_never_published(pipeline):
    item = pipeline["enqueue"]()
    claim = claim_job(pipeline["engine"], item["payload"])
    pipeline["store"].path(claim["input_object"]).write_bytes(b"changed")
    assert execute_claim(pipeline["engine"], pipeline["store"], claim, pipeline["work"], real_host_runner) == "FAILED"
    with Session(pipeline["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(OutputObject)) == 0


@pytest.mark.docker
@pytest.mark.skipif(os.getenv("RUN_DOCKER_TESTS") != "1", reason="Requires the actual local worker image")
def test_real_container_pipeline_and_authorized_playback(pipeline):
    item = pipeline["enqueue"]()
    broker = FileBroker(pipeline["work"].parent / "queue")
    relay(pipeline["engine"], broker)
    assert dispatch(pipeline, broker, run_container) == "READY"
    client = pipeline["app"].test_client()
    path = f"/api/videos/{item['video_id']}/playback"
    denied = client.get(path, headers={"Authorization": "Bearer outsider"})
    assert denied.status_code == 404 and "url" not in denied.json
    allowed = client.get(path, headers={"Authorization": "Bearer viewer"})
    assert allowed.status_code == 200 and allowed.json["duration_ms"] > 0
    response = client.get(allowed.json["url"])
    assert response.status_code == 200 and len(response.data) > 1000
    response.close()
    with Session(pipeline["engine"]) as session:
        output = session.scalar(select(OutputObject).where(OutputObject.kind == "mp4"))
        assert probe(pipeline["store"].path(output.storage_object))["streams"][0]["codec_name"] == "h264"


@pytest.mark.docker
@pytest.mark.skipif(os.getenv("RUN_DOCKER_TESTS") != "1", reason="Requires the actual local worker image")
def test_kill_actual_ffmpeg_container_then_retry(pipeline, tmp_path):
    source = tmp_path / "kill-input.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=1280x720:rate=24", "-t", "30", "-c:v", "libx264",
                    "-preset", "ultrafast", "-crf", "35", "-threads", "1", str(source)],
                   check=True, capture_output=True, timeout=45)
    item = pipeline["enqueue"](source)
    claim = claim_job(pipeline["engine"], item["payload"])
    name = "video-worker-" + claim["attempt_id"].hex
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(execute_claim, pipeline["engine"], pipeline["store"], claim,
                             pipeline["work"], run_container)
        deadline = time.monotonic() + 25
        killed = False
        while time.monotonic() < deadline and not future.done():
            processes = subprocess.run(["docker", "top", name, "-eo", "pid,comm"],
                                       capture_output=True, text=True, timeout=5)
            if "ffmpeg" in processes.stdout:
                subprocess.run(["docker", "kill", name], check=True, capture_output=True, timeout=10)
                killed = True
                break
            time.sleep(0.1)
        assert future.result(timeout=150) == "RETRYING"
        assert killed, "Must observe and kill a real FFmpeg process, not simulate success"
    with Session(pipeline["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(OutputObject)) == 0
    run_due_retry(pipeline, item["job_id"])
    broker = FileBroker(tmp_path / "kill-queue")
    relay(pipeline["engine"], broker)
    assert dispatch(pipeline, broker, run_container) == "READY"
    assert job_state(pipeline, item["job_id"])["attempts"] == 2
    with Session(pipeline["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(OutputObject)) == 2

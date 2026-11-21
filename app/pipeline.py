from datetime import timedelta
import json
import logging
import os
from pathlib import Path
import shutil
import time
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from werkzeug.exceptions import HTTPException

from app.models import OutboxEvent, OutputObject, OutputProfile, TranscodeJob, Video
from app.queue_local import QueueError
from app.storage import file_generation
from app.worker_runner import run_container
from worker.transcode import MAX_OUTPUT_BYTES, MediaError, max_input_bytes, validate_source, verify_outputs

LEASE_SECONDS = 180
# Thời hạn để worker nhận job sau khi event được gửi. Worker chạy liên tục: 30 giây là đủ. Job chạy theo sự kiện
# (Container Apps Job) còn phải chờ thăm dò hàng đợi và khởi động container, nên image Azure đặt số lớn hơn.
DISPATCH_SECONDS = min(max(int(os.getenv("DISPATCH_SECONDS", "30")), 5), 3600)
ATTEMPT_CAP = 3
PUBLISH_CAP = 5
logger = logging.getLogger(__name__)


def log_state(job_id, state, **values):
    logger.info(json.dumps({"job_id": str(job_id), "status": state, **values}))


def sync_video(session, job):
    video = session.get(Video, job.video_id, with_for_update=True)
    if video and video.source_generation == job.source_generation:
        video.status = job.status


def set_failure(session, job, code, retryable, now):
    job.last_error_code = code
    job.finished_at = now
    job.status = "RETRYING" if retryable and job.attempts < min(job.max_attempts, ATTEMPT_CAP) else "FAILED"
    job.lease_until = now + timedelta(seconds=5 * 2 ** max(0, job.attempts - 1)) if job.status == "RETRYING" else None
    sync_video(session, job)


def reset_event(session, job, reset_attempts=True):
    event = session.scalar(select(OutboxEvent).where(OutboxEvent.job_id == job.id, OutboxEvent.kind == "transcode.requested").order_by(OutboxEvent.created_at).limit(1).with_for_update())
    if event is None:
        event = OutboxEvent(job_id=job.id, kind="transcode.requested", payload_json={"job_id": str(job.id), "source_generation": job.source_generation, "profile_id": str(job.profile_id)})
        session.add(event)
    event.published_at = None
    if reset_attempts:
        event.publish_attempts = 0
    event.last_error = None


def relay(engine, broker, limit=20):
    with Session(engine) as session:
        candidates = session.execute(select(OutboxEvent.id, OutboxEvent.job_id).where(OutboxEvent.published_at.is_(None), OutboxEvent.publish_attempts < PUBLISH_CAP).order_by(OutboxEvent.created_at).limit(limit)).all()
    published = 0
    for event_id, job_id in candidates:
        with Session(engine) as session, session.begin():
            # Cùng thứ tự khóa job -> event với reconciler để tránh deadlock.
            job = session.scalar(select(TranscodeJob).where(TranscodeJob.id == job_id).with_for_update(skip_locked=True))
            if job is None:
                continue
            event = session.get(OutboxEvent, event_id, with_for_update=True)
            if event.published_at is not None or event.publish_attempts >= PUBLISH_CAP:
                continue
            now = session.scalar(select(func.clock_timestamp()))
            if job.status in {"READY", "PROCESSING", "FAILED"}:
                event.published_at = now
                continue
            if job.status == "RETRYING" and job.lease_until and job.lease_until > now:
                continue
            event.publish_attempts += 1
            try:
                broker.publish(str(event.id), event.payload_json)
            except (QueueError, OSError):
                event.last_error = "publish_failed"
                if event.publish_attempts >= PUBLISH_CAP:
                    event.last_error = "publish_exhausted"
                    set_failure(session, job, "publish_exhausted", False, now)
                continue
            event.published_at = now
            event.last_error = None
            job.status = "QUEUED"
            job.lease_until = now + timedelta(seconds=DISPATCH_SECONDS)
            sync_video(session, job)
            published += 1
    return published


def claim_job(engine, payload, now=None):
    try:
        job_id, profile_id = UUID(payload["job_id"]), UUID(payload["profile_id"])
        generation = payload["source_generation"]
    except (TypeError, ValueError, KeyError, AttributeError):
        raise ValueError("invalid_message") from None
    with Session(engine) as session, session.begin():
        job = session.get(TranscodeJob, job_id, with_for_update=True)
        if job is None or job.source_generation != generation or job.profile_id != profile_id:
            raise ValueError("message_does_not_match_job")
        now = now or session.scalar(select(func.clock_timestamp()))
        if job.status in {"READY", "FAILED", "PROCESSING"}:
            return None
        if job.status == "RETRYING" and job.lease_until and job.lease_until > now:
            return None
        if job.attempts >= min(job.max_attempts, ATTEMPT_CAP):
            set_failure(session, job, "attempts_exhausted", False, now)
            return None
        video = session.get(Video, job.video_id, with_for_update=True)
        profile = session.get(OutputProfile, job.profile_id)
        if video.source_generation != generation:
            set_failure(session, job, "source_version_changed", False, now)
            return None
        if (profile.name, profile.width_max, profile.height_max, profile.video_codec, profile.audio_codec) != ("mp4-480p", 854, 480, "h264", "aac"):
            set_failure(session, job, "unsupported_profile", False, now)
            return None
        job.attempts += 1
        job.current_attempt_id = uuid4()
        job.status = "PROCESSING"
        job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        job.started_at, job.finished_at, job.progress_percent = now, None, None
        sync_video(session, job)
        result = {"job_id": job.id, "attempt_id": job.current_attempt_id, "video_id": video.id,
                  "profile_id": job.profile_id, "generation": generation,
                  "input_object": video.input_object, "size_bytes": video.size_bytes}
        log_state(job.id, "PROCESSING", attempt_id=str(job.current_attempt_id), attempt=job.attempts, queue_age_seconds=max(0, (now - job.queued_at).total_seconds()))
        return result


def owns_lease(job, claim, now):
    # job có thể là None nếu chủ sở hữu đã xoá video trong lúc worker còn chạy.
    return job is not None and job.status == "PROCESSING" and job.current_attempt_id == claim["attempt_id"] and job.lease_until is not None and job.lease_until > now


def touch_lease(engine, claim, percent=None):
    """Heartbeat: gia hạn lease và ghi tiến độ đo được. Trả False nếu attempt này không còn giữ job."""
    with Session(engine) as session, session.begin():
        job = session.get(TranscodeJob, claim["job_id"], with_for_update=True)
        now = session.scalar(select(func.clock_timestamp()))
        if not owns_lease(job, claim, now):
            return False
        job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        if percent is not None:
            job.progress_percent = max(0, min(99, int(percent)))
        return True


def source_file(store, claim, seed_root=None):
    name = claim["input_object"]
    if name.startswith("local-seed/") and seed_root is not None:
        filename = name.removeprefix("local-seed/")
        if Path(filename).name != filename:
            raise MediaError("invalid_seed_source")
        path = Path(seed_root) / filename
    else:
        store.head(name)
        path = store.path(name)
    if not path.is_file() or path.is_symlink() or path.stat().st_size != claim["size_bytes"] or path.stat().st_size > max_input_bytes():
        raise MediaError("source_size_changed")
    if file_generation(path) != claim["generation"]:
        raise MediaError("source_generation_changed")
    return path


def fetch_source(store, claim, target, seed_root=None):
    """Chép đúng phiên bản nguồn của job vào thư mục riêng của attempt."""
    if hasattr(store, "download") and not claim["input_object"].startswith("local-seed/"):
        # Blob Storage: tải theo version ID nên nội dung chắc chắn là phiên bản đã ghi trong job.
        store.download(claim["input_object"], claim["generation"], target)
        if target.stat().st_size != claim["size_bytes"] or target.stat().st_size > max_input_bytes():
            raise MediaError("source_size_changed")
        return
    shutil.copyfile(source_file(store, claim, seed_root), target)
    if file_generation(target) != claim["generation"]:
        raise MediaError("source_generation_changed")


def execute_claim(engine, store, claim, work_root, runner=run_container, seed_root=None, heartbeat=False, on_beat=None):
    started = time.monotonic()
    attempt = Path(work_root).resolve() / str(claim["job_id"]) / str(claim["attempt_id"])

    def beat(percent):
        # on_beat giữ khoá của message trong lúc job còn chạy (Service Bus); lease trong DB vẫn là thứ quyết định.
        if on_beat:
            on_beat()
        return touch_lease(engine, claim, percent)

    try:
        private_input = attempt / "input" / "source"
        private_input.parent.mkdir(parents=True, exist_ok=False)
        fetch_source(store, claim, private_input, seed_root)
        output = attempt / "output"
        if heartbeat:
            # Runner native gọi lại định kỳ để gia hạn lease; trả False thì runner phải dừng FFmpeg.
            runner(private_input, output, claim["attempt_id"], beat)
        else:
            runner(private_input, output, claim["attempt_id"])
        metadata = verify_outputs(output, validate_source(private_input))
        # Job gắn duy nhất với video/generation/profile; tên ngắn tránh MAX_PATH trên Windows.
        prefix = f"outputs/{claim['job_id'].hex}/{claim['attempt_id'].hex}"
        objects = []
        for kind, filename, mime in [("mp4", "video.mp4", "video/mp4"), ("thumbnail", "thumbnail.jpg", "image/jpeg")]:
            name = prefix + "/" + filename
            with (output / filename).open("rb") as stream:
                store.write(name, stream, mime, MAX_OUTPUT_BYTES)
            info = store.head(name)
            objects.append({"kind": kind, "storage_object": name, "storage_generation": info["generation"], "bytes": info["size_bytes"]})
        with Session(engine) as session, session.begin():
            job = session.get(TranscodeJob, claim["job_id"], with_for_update=True)
            now = session.scalar(select(func.clock_timestamp()))
            if not owns_lease(job, claim, now):
                return "stale"
            video = session.get(Video, job.video_id, with_for_update=True)
            if video.source_generation != job.source_generation:
                set_failure(session, job, "source_version_changed", False, now)
                return "FAILED"
            for values in objects:
                session.add(OutputObject(transcode_job_id=job.id, source_generation=job.source_generation, profile_id=job.profile_id, duration_ms=metadata["duration_ms"], **values))
            job.status, job.finished_at, job.lease_until, job.last_error_code = "READY", now, None, None
            job.duration_ms = round((now - job.started_at).total_seconds() * 1000)
            job.progress_percent = 100
            sync_video(session, job)
        log_state(claim["job_id"], "READY", attempt_id=str(claim["attempt_id"]), processing_seconds=round(time.monotonic() - started, 3), output_bytes=sum(o["bytes"] for o in objects))
        # Output đã nằm trong storage riêng tư; thư mục tạm của attempt không còn cần.
        shutil.rmtree(attempt, ignore_errors=True)
        return "READY"
    except (MediaError, HTTPException, OSError) as error:
        if isinstance(error, OSError):
            logger.warning("local_io_failure errno=%s winerror=%s", error.errno, getattr(error, "winerror", None))
        code = error.code if isinstance(error, MediaError) else "source_or_storage_unavailable"
        retryable = error.retryable if isinstance(error, MediaError) else isinstance(error, OSError)
        with Session(engine) as session, session.begin():
            job = session.get(TranscodeJob, claim["job_id"], with_for_update=True)
            now = session.scalar(select(func.clock_timestamp()))
            if not owns_lease(job, claim, now):
                return "stale"
            set_failure(session, job, code, retryable, now)
            state = job.status
        log_state(claim["job_id"], state, attempt_id=str(claim["attempt_id"]), error=code)
        shutil.rmtree(attempt, ignore_errors=True)
        return state


def dispatch_one(engine, broker, store, work_root, runner=run_container, seed_root=None, heartbeat=False):
    delivery = broker.receive()
    if delivery is None:
        return "empty"
    try:
        UUID(str(delivery.get("operation_key")))
        claim = claim_job(engine, delivery.get("payload"))
    except (ValueError, TypeError):
        broker.dead_letter(delivery, "invalid_job_message")
        return "dead_letter"
    extend = getattr(broker, "extend", None)
    on_beat = (lambda: extend(delivery)) if extend else None
    result = execute_claim(engine, store, claim, work_root, runner, seed_root, heartbeat, on_beat) if claim else "no_op"
    # Ack chỉ sau khi kết quả hoặc trạng thái lease/retry đã commit bền vững.
    broker.ack(delivery)
    return result


def reconcile(engine, now=None, limit=20):
    recovered = 0
    with Session(engine) as session, session.begin():
        now = now or session.scalar(select(func.clock_timestamp()))
        jobs = session.scalars(select(TranscodeJob).where(TranscodeJob.status.in_(["PROCESSING", "RETRYING", "QUEUED"]), TranscodeJob.lease_until <= now).order_by(TranscodeJob.queued_at).limit(limit).with_for_update(skip_locked=True)).all()
        for job in jobs:
            if job.status == "PROCESSING":
                set_failure(session, job, "lease_expired", True, now)
            else:
                event = session.scalar(select(OutboxEvent).where(OutboxEvent.job_id == job.id, OutboxEvent.kind == "transcode.requested").limit(1).with_for_update())
                if job.status == "QUEUED" and event and event.publish_attempts >= PUBLISH_CAP:
                    set_failure(session, job, "dispatch_exhausted", False, now)
                    continue
                was_retry = job.status == "RETRYING"
                job.status, job.lease_until, job.current_attempt_id = "QUEUED", None, None
                reset_event(session, job, reset_attempts=was_retry)
                sync_video(session, job)
            recovered += 1
    return recovered


def retry_failed_job(engine, job_id):
    with Session(engine) as session, session.begin():
        job = session.get(TranscodeJob, job_id, with_for_update=True)
        if job is None or job.status != "FAILED":
            raise ValueError("Only an existing FAILED job can be retried explicitly")
        job.status, job.attempts, job.lease_until, job.current_attempt_id = "QUEUED", 0, None, None
        job.last_error_code, job.started_at, job.finished_at, job.duration_ms = None, None, None, None
        reset_event(session, job)
        sync_video(session, job)

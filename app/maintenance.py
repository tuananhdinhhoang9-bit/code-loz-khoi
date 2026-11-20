"""Dọn file tạm, upload bỏ dở và output mồ côi. Chỉ xoá bên trong thư mục được cấu hình."""

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import shutil
import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from werkzeug.exceptions import HTTPException

from app.models import OutputObject, TranscodeJob, Video

logger = logging.getLogger(__name__)


def is_link(path):
    return path.is_symlink() or path.is_junction()


def old_enough(path, cutoff):
    try:
        return path.stat().st_mtime < cutoff
    except OSError:
        return False


def cleanup_work(work_root, max_age_hours=24):
    """Xoá thư mục attempt tạm (<work>/<job>/<attempt>) đã cũ; attempt đang chạy luôn mới hơn ngưỡng."""
    root = Path(work_root).resolve()
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    if not root.is_dir():
        return 0
    for job_folder in root.iterdir():
        if not job_folder.is_dir() or is_link(job_folder):
            continue
        for attempt in job_folder.iterdir():
            if attempt.is_dir() and not is_link(attempt) and old_enough(attempt, cutoff):
                shutil.rmtree(attempt, ignore_errors=True)
                removed += 1
        try:
            job_folder.rmdir()
        except OSError:
            pass
    return removed


def cleanup_uploads(engine, store, max_age_hours=24):
    """Xoá bản ghi PENDING_UPLOAD bị bỏ dở và file .tmp sót lại trong inputs/."""
    removed = 0
    with Session(engine) as session, session.begin():
        now = session.scalar(select(func.clock_timestamp()))
        stale = session.scalars(select(Video).where(Video.status == "PENDING_UPLOAD", Video.created_at < now - timedelta(hours=max_age_hours)).with_for_update(skip_locked=True)).all()
        names = [video.input_object for video in stale]
        for video in stale:
            session.delete(video)
            removed += 1
    for name in names:
        try:
            store.delete(name)
        except (OSError, HTTPException):
            logger.warning("cleanup could not delete one abandoned upload")
    if not hasattr(store, "root"):
        # S3 không có file .tmp: upload dang dở không bao giờ thành object.
        return removed
    cutoff = time.time() - max_age_hours * 3600
    inputs = store.root / "inputs"
    if inputs.is_dir():
        for temporary in inputs.rglob("*.tmp"):
            if temporary.is_file() and not is_link(temporary) and old_enough(temporary, cutoff):
                temporary.unlink(missing_ok=True)
                removed += 1
    return removed


def cleanup_outputs(engine, store, max_age_hours=24):
    """Xoá thư mục output của attempt không được OutputObject nào trỏ tới (attempt hỏng hoặc bị thay thế)."""
    with Session(engine) as session:
        published = {name.rsplit("/", 1)[0] for name in session.scalars(select(OutputObject.storage_object))}
        active = {job_id.hex for job_id in session.scalars(select(TranscodeJob.id).where(TranscodeJob.status == "PROCESSING"))}
    removed = 0
    if not hasattr(store, "root"):
        # S3: tên object là outputs/<job>/<attempt>/<file>; xoá từng object cũ không còn được trỏ tới.
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        for name in list(store.old_objects("outputs/", cutoff)):
            parts = name.split("/")
            if len(parts) == 4 and parts[1] not in active and "/".join(parts[:3]) not in published:
                store.delete(name)
                removed += 1
        return removed
    outputs = store.root / "outputs"
    if not outputs.is_dir():
        return 0
    cutoff = time.time() - max_age_hours * 3600
    for job_folder in outputs.iterdir():
        if not job_folder.is_dir() or is_link(job_folder) or job_folder.name in active:
            continue
        for attempt in job_folder.iterdir():
            name = f"outputs/{job_folder.name}/{attempt.name}"
            if attempt.is_dir() and not is_link(attempt) and name not in published and old_enough(attempt, cutoff):
                shutil.rmtree(attempt, ignore_errors=True)
                removed += 1
        try:
            job_folder.rmdir()
        except OSError:
            pass
    return removed


def cleanup_all(engine, store, work_root, max_age_hours=24):
    return {"work": cleanup_work(work_root, max_age_hours),
            "uploads": cleanup_uploads(engine, store, max_age_hours),
            "outputs": cleanup_outputs(engine, store, max_age_hours)}


def disk_status(path):
    usage = shutil.disk_usage(path)
    return {"total_bytes": usage.total, "free_bytes": usage.free, "used_percent": round(100 * (usage.total - usage.free) / usage.total, 1)}

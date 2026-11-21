"""Worker chạy nền: reconcile -> relay outbox -> nhận job từ hàng đợi -> FFmpeg.

Chạy liên tục (VPS/local): python -m app.worker_service   (dừng bằng Ctrl+C / Ctrl+Break / lệnh stop của service)
Chạy một vòng rồi thoát (Container Apps Job trên Azure): python -m app.worker_service --once
Chỉ một worker hoạt động tại một thời điểm (advisory lock) và mỗi lần chỉ xử lý một video.
"""

import json
import logging
from pathlib import Path
import signal
import sys
import threading
import time

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.maintenance import cleanup_all
from app.pipeline import dispatch_one, reconcile, relay
from app.queue_local import QueueError
from app.worker_native import run_native

WORKER_LOCK_KEY = 741_000_701
CLEANUP_SECONDS = 3600
logger = logging.getLogger("app.worker")


def single_worker_lock(engine):
    """Giữ một kết nối có advisory lock suốt đời worker; worker thứ hai sẽ không lấy được."""
    connection = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    # Tách khỏi pool: close() sẽ đóng hẳn kết nối, nhờ đó PostgreSQL nhả lock ngay.
    connection.detach()
    if connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKER_LOCK_KEY}).scalar():
        return connection
    connection.close()
    return None


def run_worker(engine, broker, store, work_root, stop, runner=run_native, seed_root=None, poll_seconds=2.0, heartbeat=True):
    """Vòng lặp chính. Chỉ relay thêm khi hàng đợi trống để job không chờ quá hạn dispatch."""
    processed = 0
    next_cleanup = time.monotonic() + 60
    while not stop.is_set():
        try:
            reconcile(engine)
            outcome = dispatch_one(engine, broker, store, work_root, runner, seed_root, heartbeat)
            if outcome == "empty" and relay(engine, broker, limit=1):
                outcome = dispatch_one(engine, broker, store, work_root, runner, seed_root, heartbeat)
            if outcome == "empty" and time.monotonic() >= next_cleanup:
                next_cleanup = time.monotonic() + CLEANUP_SECONDS
                logger.info(json.dumps({"event": "cleanup", **cleanup_all(engine, store, work_root)}))
        except (SQLAlchemyError, QueueError, OSError) as error:
            # Lỗi tạm thời (DB khởi động lại, đĩa bận): ghi loại lỗi, chờ rồi thử lại, không thoát.
            logger.error(json.dumps({"event": "worker_cycle_failed", "error_type": type(error).__name__}))
            stop.wait(5)
            continue
        if outcome == "empty":
            stop.wait(poll_seconds)
        else:
            processed += 1
            logger.info(json.dumps({"event": "worker_outcome", "outcome": outcome}))
    return processed


def run_once(engine, broker, store, work_root, runner=run_native, seed_root=None, heartbeat=True):
    """Một lần chạy của Container Apps Job: cùng thứ tự với vòng lặp ở trên, xử lý tối đa một message rồi trả về.

    Lỗi tạm thời không bị nuốt: tiến trình thoát với mã lỗi, message chưa ack sẽ được Service Bus giao lại.
    """
    reconcile(engine)
    outcome = dispatch_one(engine, broker, store, work_root, runner, seed_root, heartbeat)
    if outcome == "empty" and relay(engine, broker, limit=1):
        outcome = dispatch_one(engine, broker, store, work_root, runner, seed_root, heartbeat)
    logger.info(json.dumps({"event": "worker_outcome", "outcome": outcome}))
    return outcome


def main(once=None):
    from app.logs import configure_logging
    from app.main import create_app
    from app.queue_pg import make_broker
    from app.storage import storage

    app = create_app()
    configure_logging(app.config.get("LOG_DIR"), "worker")
    engine = app.extensions["db_engine"]
    if engine is None:
        logger.error(json.dumps({"event": "worker_start_failed", "reason": "database_not_configured"}))
        return 2
    stop = threading.Event()
    for name in ["SIGINT", "SIGTERM", "SIGBREAK"]:
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: stop.set())
    try:
        lock = single_worker_lock(engine)
    except SQLAlchemyError:
        logger.error(json.dumps({"event": "worker_start_failed", "reason": "database_unavailable"}))
        return 2
    if lock is None:
        logger.error(json.dumps({"event": "worker_start_failed", "reason": "another_worker_is_running"}))
        return 3
    with app.app_context():
        store = storage()
    once = "--once" in sys.argv[1:] if once is None else once
    logger.info(json.dumps({"event": "worker_started", "mode": "once" if once else "loop"}))
    broker = make_broker(app, engine)
    seed_root = Path(app.config["STORAGE_ROOT"]).parent / "seed"
    try:
        if once:
            run_once(engine, broker, store, app.config["WORK_ROOT"], seed_root=seed_root)
        else:
            run_worker(engine, broker, store, app.config["WORK_ROOT"], stop, seed_root=seed_root)
    except (SQLAlchemyError, QueueError, OSError) as error:
        # Chỉ tới đây ở chế độ một vòng: báo lỗi bằng mã thoát để nền tảng ghi nhận lần chạy thất bại.
        logger.error(json.dumps({"event": "worker_cycle_failed", "error_type": type(error).__name__}))
        return 1
    finally:
        if hasattr(broker, "close"):
            broker.close()
        lock.close()
        engine.dispose()
    logger.info(json.dumps({"event": "worker_stopped"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

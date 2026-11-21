import json
from uuid import UUID, uuid4

from werkzeug.exceptions import HTTPException

from flask import abort, current_app, g, request, send_file
from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.auth import authorized_video, db_session, require_auth, video_data
from app.models import OutboxEvent, OutputObject, OutputProfile, QueueMessage, TranscodeJob, Video, VideoPermission
from app.pipeline import relay
from app.queue_local import QueueError
from app.queue_pg import make_broker
from app.storage import URL_TTL, storage

MIME_TYPES = {"video/mp4", "video/webm", "video/quicktime"}


def upload_limit():
    return current_app.config["MAX_UPLOAD_BYTES"]


def json_body():
    if not request.is_json:
        abort(400, description="json_required")
    raw = request.stream.read(16_385)
    if len(raw) > 16_384:
        abort(413, description="json_too_large")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        abort(400, description="invalid_json")
    if not isinstance(data, dict):
        abort(400, description="json_object_required")
    return data


def locked_owner(session, video_id):
    session.get(Video, video_id, with_for_update=True)
    return authorized_video(session, video_id, owner_only=True)


def register_video_routes(app):
    @app.get("/api/videos")
    @require_auth
    def list_videos():
        with db_session() as session:
            permitted = exists().where(VideoPermission.video_id == Video.id, VideoPermission.viewer_uid == g.user["uid"])
            videos = session.scalars(select(Video).where(or_(Video.owner_uid == g.user["uid"], permitted)).order_by(Video.created_at.desc()).limit(100))
            return {"videos": [video_data(v) for v in videos], "request_id": g.request_id}

    @app.post("/api/videos")
    @require_auth
    def create_video():
        data = json_body()
        title, mime, size = data.get("title"), data.get("mime_type"), data.get("size_bytes")
        if not isinstance(title, str) or not 0 < len(title.strip()) <= 200:
            abort(400, description="invalid_title")
        if not isinstance(mime, str) or mime not in MIME_TYPES:
            abort(400, description="unsupported_content_type")
        if type(size) is not int or size <= 0:
            abort(400, description="invalid_size")
        if size > upload_limit():
            abort(413, description="upload_too_large")
        storage().ensure_space(size)
        video_id = uuid4()
        name = f"inputs/{video_id}/{uuid4().hex}"
        with db_session() as session, session.begin():
            session.add(Video(id=video_id, owner_uid=g.user["uid"], title=title.strip(), input_object=name, source_generation="pending", size_bytes=size, mime_type=mime, status="PENDING_UPLOAD"))
        target = storage().upload_target(video_id=str(video_id), name=name, mime_type=mime, size_limit=size)
        return {"video_id": str(video_id), **target, "expires_in": URL_TTL, "request_id": g.request_id}, 201

    def relay_now():
        """Với Service Bus không có worker chạy liên tục: gửi event vừa commit ngay để job chuyển mã được khởi động.

        Giao dịch nghiệp vụ đã commit trước khi tới đây. Gửi lỗi thì chỉ ghi log; job maintenance theo lịch sẽ gửi lại.
        """
        if current_app.config.get("QUEUE_BACKEND") != "servicebus":
            return
        engine = current_app.extensions["db_engine"]
        try:
            if "broker" not in current_app.extensions:
                current_app.extensions["broker"] = make_broker(current_app, engine)
            relay(engine, current_app.extensions["broker"], limit=5)
        except (SQLAlchemyError, QueueError, OSError):
            current_app.logger.warning("Outbox relay after upload failed request_id=%s", g.request_id)

    def local_store():
        # Hai route /local-storage chỉ tồn tại khi file nằm trên đĩa của máy chủ; với Blob Storage trình duyệt nói chuyện thẳng với Azure.
        if current_app.config.get("STORAGE_BACKEND", "local") != "local":
            abort(404, description="not_found")
        return storage()

    @app.put("/local-storage/upload")
    def upload_object():
        data = local_store().verify(request.args.get("ticket", ""), "upload")
        if request.mimetype != data["mime_type"]:
            abort(400, description="content_type_mismatch")
        if request.content_length and request.content_length > min(upload_limit(), data["size_limit"]):
            abort(413, description="upload_too_large")
        with db_session() as session, session.begin():
            video = session.get(Video, UUID(data["video_id"]), with_for_update=True)
            if video is None or video.status != "PENDING_UPLOAD" or video.input_object != data["name"]:
                abort(409, description="upload_not_pending")
            storage().write(data["name"], request.stream, data["mime_type"], data["size_limit"])
        return {"status": "uploaded", "request_id": g.request_id}, 201

    @app.post("/api/videos/<uuid:video_id>/complete")
    @require_auth
    def complete_upload(video_id):
        with db_session() as session, session.begin():
            video = locked_owner(session, video_id)
            if video.status != "PENDING_UPLOAD":
                job = session.scalar(select(TranscodeJob).where(TranscodeJob.video_id == video.id, TranscodeJob.source_generation == video.source_generation))
                if job:
                    return {"job_id": str(job.id), "status": video.status, "request_id": g.request_id}
                abort(409, description="upload_not_pending")
            metadata = storage().head(video.input_object)
            if metadata["size_bytes"] > upload_limit():
                # Chỉ xảy ra với Blob Storage (SAS không giới hạn kích thước): bỏ ngay file quá cỡ, không chờ lệnh dọn dẹp.
                try:
                    storage().delete(video.input_object)
                except (OSError, HTTPException):
                    current_app.logger.warning("Oversized upload could not be deleted request_id=%s", g.request_id)
                abort(413, description="upload_too_large")
            if metadata["size_bytes"] != video.size_bytes or metadata["mime_type"] != video.mime_type:
                abort(400, description="uploaded_metadata_mismatch")
            profile = session.scalar(select(OutputProfile).where(OutputProfile.name == "mp4-480p"))
            if profile is None:
                abort(503, description="profile_not_initialized")
            video.source_generation = metadata["generation"]
            video.status = "QUEUED"
            job_id = uuid4()
            session.add(TranscodeJob(id=job_id, video_id=video.id, source_generation=video.source_generation, profile_id=profile.id))
            session.flush()
            session.add(OutboxEvent(job_id=job_id, kind="transcode.requested", payload_json={"job_id": str(job_id), "source_generation": video.source_generation, "profile_id": str(profile.id)}))
        relay_now()
        return {"job_id": str(job_id), "status": "QUEUED", "request_id": g.request_id}, 202

    @app.get("/api/videos/<uuid:video_id>/status")
    @require_auth
    def video_status(video_id):
        with db_session() as session:
            video = authorized_video(session, video_id)
            job = session.scalar(select(TranscodeJob).where(TranscodeJob.video_id == video.id, TranscodeJob.source_generation == video.source_generation))
            # Chỉ trả phần trăm FFmpeg đã đo khi đang xử lý; không đoán tiến độ.
            progress = job.progress_percent if job and job.status == "PROCESSING" else None
            return {"video_id": str(video.id), "status": video.status, "progress_percent": progress,
                    "error_code": job.last_error_code if job and job.status in {"FAILED", "RETRYING"} else None,
                    "request_id": g.request_id}

    @app.delete("/api/videos/<uuid:video_id>")
    @require_auth
    def delete_video(video_id):
        with db_session() as session, session.begin():
            video = locked_owner(session, video_id)
            jobs = session.scalars(select(TranscodeJob).where(TranscodeJob.video_id == video.id).with_for_update()).all()
            now = session.scalar(select(func.clock_timestamp()))
            if any(job.status == "PROCESSING" and job.lease_until and job.lease_until > now for job in jobs):
                abort(409, description="video_processing")
            job_ids = [job.id for job in jobs]
            names = [video.input_object] if video.input_object.startswith("inputs/") else []
            if job_ids:
                names += list(session.scalars(select(OutputObject.storage_object).where(OutputObject.transcode_job_id.in_(job_ids))))
                session.execute(delete(OutputObject).where(OutputObject.transcode_job_id.in_(job_ids)))
                session.execute(delete(OutboxEvent).where(OutboxEvent.job_id.in_(job_ids)))
                session.execute(delete(QueueMessage).where(QueueMessage.payload_json["job_id"].astext.in_([str(item) for item in job_ids])))
                session.execute(delete(TranscodeJob).where(TranscodeJob.id.in_(job_ids)))
            session.execute(delete(VideoPermission).where(VideoPermission.video_id == video.id))
            session.delete(video)
        # File chỉ bị xoá sau khi DB đã commit; file sót lại do lỗi sẽ được dọn bởi lệnh cleanup.
        for name in names:
            try:
                storage().delete(name)
            except (OSError, HTTPException):
                current_app.logger.warning("Storage delete left an orphan object request_id=%s", g.request_id)
        return {"status": "deleted", "request_id": g.request_id}

    @app.post("/api/videos/<uuid:video_id>/permissions")
    @require_auth
    def permissions(video_id):
        data = json_body()
        uid, action = data.get("viewer_uid"), data.get("action")
        if not isinstance(uid, str) or not uid.strip() or len(uid) > 128 or not isinstance(action, str) or action not in {"grant", "revoke"}:
            abort(400, description="invalid_permission")
        with db_session() as session, session.begin():
            video = locked_owner(session, video_id)
            permission = session.get(VideoPermission, (video.id, uid))
            if action == "grant" and permission is None:
                session.add(VideoPermission(video_id=video.id, viewer_uid=uid))
            if action == "revoke" and permission is not None:
                session.delete(permission)
        return {"status": action, "request_id": g.request_id}

    def output_url(video_id, kind):
        with db_session() as session:
            video = authorized_video(session, video_id)
            if video.status != "READY":
                abort(409, description="video_not_ready")
            job = session.scalar(select(TranscodeJob).where(TranscodeJob.video_id == video.id, TranscodeJob.source_generation == video.source_generation, TranscodeJob.status == "READY"))
            if job is None:
                abort(409, description="video_not_ready")
            outputs = {o.kind: o for o in session.scalars(select(OutputObject).where(OutputObject.transcode_job_id == job.id))}
            if set(outputs) != {"mp4", "thumbnail"}:
                abort(409, description="outputs_not_ready")
            for item in outputs.values():
                metadata = storage().head(item.storage_object)
                if metadata["generation"] != item.storage_generation or metadata["size_bytes"] != item.bytes:
                    abort(409, description="output_changed")
            item = outputs[kind]
            url = storage().read_url(item.storage_object, item.storage_generation, "video/mp4" if kind == "mp4" else "image/jpeg")
            return {"url": url, "expires_in": URL_TTL, "duration_ms": item.duration_ms, "request_id": g.request_id}

    @app.get("/api/videos/<uuid:video_id>/playback")
    @require_auth
    def playback(video_id):
        return output_url(video_id, "mp4")

    @app.get("/api/videos/<uuid:video_id>/thumbnail")
    @require_auth
    def thumbnail(video_id):
        return output_url(video_id, "thumbnail")

    @app.get("/local-storage/read")
    def read_object():
        data = local_store().verify(request.args.get("ticket", ""), "read")
        metadata = storage().head(data["name"])
        if metadata["generation"] != data["generation"]:
            abort(404, description="object_not_found")
        return send_file(storage().path(data["name"]), mimetype=data["mime_type"], conditional=True)

    @app.get("/api/monitor")
    @require_auth
    def monitor():
        if not g.user["admin"]:
            abort(403, description="admin_required")
        with db_session() as session:
            counts = session.execute(select(TranscodeJob.status, func.count()).group_by(TranscodeJob.status)).all()
            errors = session.execute(select(TranscodeJob.last_error_code, func.count()).where(TranscodeJob.status == "FAILED").group_by(TranscodeJob.last_error_code)).all()
            dead = session.scalar(select(func.count()).select_from(QueueMessage).where(QueueMessage.dead_at.is_not(None)))
            if current_app.config.get("QUEUE_BACKEND") == "servicebus":
                # Message chết nằm ở dead-letter queue của Service Bus (xem Azure Monitor); không báo 0 khi chưa đếm.
                dead = None
            return {"jobs": dict(counts), "failed_by_error": {code or "unknown": count for code, count in errors},
                    "dead_messages": dead, "storage_free_bytes": storage().free_bytes(), "request_id": g.request_id}

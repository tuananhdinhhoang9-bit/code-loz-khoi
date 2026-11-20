from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey,
    ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


def utc_now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Video(Base):
    __tablename__ = "videos"
    id = Column(Uuid, primary_key=True, default=uuid4)
    owner_uid = Column(String(128), nullable=False)
    title = Column(String(200), nullable=False)
    input_object = Column(String(512), nullable=False)
    source_generation = Column(String(128), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    mime_type = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    status = Column(String(24), nullable=False, default="QUEUED")
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="video_size_nonnegative"),
        CheckConstraint("status IN ('PENDING_UPLOAD','UPLOADED','QUEUED','PROCESSING','RETRYING','READY','FAILED')", name="video_status_valid"),
    )


class OutputProfile(Base):
    __tablename__ = "output_profiles"
    id = Column(Uuid, primary_key=True, default=uuid4)
    name = Column(String(80), nullable=False, unique=True)
    width_max = Column(Integer, nullable=False, default=854)
    height_max = Column(Integer, nullable=False, default=480)
    video_codec = Column(String(32), nullable=False, default="h264")
    audio_codec = Column(String(32), nullable=False, default="aac")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    __table_args__ = (CheckConstraint("width_max > 0 AND height_max > 0", name="profile_dimensions_positive"),)


class TranscodeJob(Base):
    __tablename__ = "transcode_jobs"
    id = Column(Uuid, primary_key=True, default=uuid4)
    video_id = Column(Uuid, ForeignKey("videos.id"), nullable=False)
    source_generation = Column(String(128), nullable=False)
    profile_id = Column(Uuid, ForeignKey("output_profiles.id"), nullable=False)
    status = Column(String(24), nullable=False, default="QUEUED")
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    lease_until = Column(DateTime(timezone=True))
    current_attempt_id = Column(Uuid)
    last_error_code = Column(String(80))
    queued_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    duration_ms = Column(BigInteger)
    # Tiến độ FFmpeg đo thật (0-100); NULL khi chưa có số đo.
    progress_percent = Column(Integer)
    __table_args__ = (
        UniqueConstraint("video_id", "source_generation", "profile_id", name="job_logical_key"),
        UniqueConstraint("id", "source_generation", "profile_id", name="job_output_version"),
        CheckConstraint("attempts >= 0 AND max_attempts > 0 AND attempts <= max_attempts", name="job_attempts_bounded"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="job_duration_nonnegative"),
        CheckConstraint("status IN ('QUEUED','PROCESSING','RETRYING','READY','FAILED')", name="job_status_valid"),
    )


class OutputObject(Base):
    __tablename__ = "output_objects"
    id = Column(Uuid, primary_key=True, default=uuid4)
    transcode_job_id = Column(Uuid, nullable=False)
    source_generation = Column(String(128), nullable=False)
    profile_id = Column(Uuid, nullable=False)
    kind = Column(String(16), nullable=False)
    storage_object = Column(String(512), nullable=False)
    storage_generation = Column(String(128), nullable=False)
    bytes = Column(BigInteger, nullable=False)
    duration_ms = Column(BigInteger)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    __table_args__ = (
        ForeignKeyConstraint(
            ["transcode_job_id", "source_generation", "profile_id"],
            ["transcode_jobs.id", "transcode_jobs.source_generation", "transcode_jobs.profile_id"],
            name="output_matches_job_version",
        ),
        UniqueConstraint("transcode_job_id", "kind", name="output_job_kind"),
        CheckConstraint("kind IN ('mp4','thumbnail')", name="output_kind_valid"),
        CheckConstraint("bytes >= 0 AND (duration_ms IS NULL OR duration_ms >= 0)", name="output_sizes_nonnegative"),
    )


class VideoPermission(Base):
    __tablename__ = "video_permissions"
    video_id = Column(Uuid, ForeignKey("videos.id"), primary_key=True)
    viewer_uid = Column(String(128), primary_key=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id = Column(Uuid, primary_key=True, default=uuid4)
    job_id = Column(Uuid, ForeignKey("transcode_jobs.id"), nullable=False)
    kind = Column(String(80), nullable=False)
    payload_json = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    published_at = Column(DateTime(timezone=True))
    publish_attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String(200))
    __table_args__ = (CheckConstraint("publish_attempts >= 0", name="outbox_attempts_nonnegative"),)


class QueueMessage(Base):
    """Hàng đợi bền trong PostgreSQL (thay Pub/Sub); chỉ chứa ID job, không chứa dữ liệu video."""
    __tablename__ = "queue_messages"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    operation_key = Column(Uuid, nullable=False)
    payload_json = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    visible_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    deliveries = Column(Integer, nullable=False, default=0)
    dead_at = Column(DateTime(timezone=True))
    dead_reason = Column(String(80))
    __table_args__ = (
        CheckConstraint("deliveries >= 0", name="queue_deliveries_nonnegative"),
        Index("queue_messages_due", "dead_at", "visible_at"),
    )


class User(Base):
    """Tài khoản nội bộ cho AUTH_PROVIDER=local; uid là email viết thường."""
    __tablename__ = "users"
    uid = Column(String(128), primary_key=True)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    failed_logins = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    __table_args__ = (CheckConstraint("failed_logins >= 0", name="user_failed_logins_nonnegative"),)


class AuthSession(Base):
    """Chỉ lưu SHA-256 của token phiên; token thật chỉ nằm ở trình duyệt."""
    __tablename__ = "auth_sessions"
    token_hash = Column(String(64), primary_key=True)
    uid = Column(String(128), ForeignKey("users.uid"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)

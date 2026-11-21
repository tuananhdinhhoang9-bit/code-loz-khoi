from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import OutboxEvent, OutputObject, OutputProfile, TranscodeJob, Video, VideoPermission

pytestmark = pytest.mark.integration


def add_job(session):
    video = Video(owner_uid="owner", title="Fixture", input_object="local/input.mp4", source_generation="local-v1", size_bytes=100, mime_type="video/mp4")
    profile = OutputProfile(name="mp4-480p")
    session.add_all([video, profile])
    session.flush()
    job = TranscodeJob(video_id=video.id, source_generation=video.source_generation, profile_id=profile.id)
    session.add(job)
    session.flush()
    return video, profile, job


def test_duplicate_logical_job_rejected(schema_engine):
    with Session(schema_engine) as session, session.begin():
        video, profile, job = add_job(session)
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(TranscodeJob(video_id=video.id, profile_id=profile.id, source_generation=job.source_generation))
            session.flush()
        assert session.scalar(select(func.count()).select_from(TranscodeJob)) == 1


def test_new_source_version_is_distinct_job(schema_engine):
    with Session(schema_engine) as session, session.begin():
        video, profile, _ = add_job(session)
        session.add(TranscodeJob(video_id=video.id, profile_id=profile.id, source_generation="local-v2"))
        session.flush()
        assert session.scalar(select(func.count()).select_from(TranscodeJob)) == 2


@pytest.mark.parametrize("field,value", [("attempts", -1), ("attempts", 4), ("max_attempts", 0), ("status", "UNKNOWN")])
def test_invalid_job_state_rejected(schema_engine, field, value):
    with Session(schema_engine) as session, session.begin():
        _, _, job = add_job(session)
        with pytest.raises(IntegrityError), session.begin_nested():
            setattr(job, field, value)
            session.flush()


def test_output_unique_and_matches_job_version(schema_engine):
    with Session(schema_engine) as session, session.begin():
        _, profile, job = add_job(session)
        values = {"transcode_job_id": job.id, "source_generation": job.source_generation, "profile_id": profile.id, "kind": "mp4", "storage_object": "local/published.mp4", "storage_generation": "local-1", "bytes": 100, "duration_ms": 1000}
        session.add(OutputObject(**values))
        session.flush()
        for changed in [{}, {"kind": "thumbnail", "source_generation": "wrong-version"}, {"kind": "thumbnail", "profile_id": uuid4()}, {"kind": "other"}, {"kind": "thumbnail", "bytes": -1}]:
            with pytest.raises(IntegrityError), session.begin_nested():
                session.add(OutputObject(**(values | changed)))
                session.flush()
        session.add(OutputObject(**(values | {"kind": "thumbnail", "storage_object": "local/thumbnail.jpg"})))
        session.flush()
        assert session.scalar(select(func.count()).select_from(OutputObject)) == 2


def test_permission_duplicates_and_orphans_rejected(schema_engine):
    with Session(schema_engine) as session, session.begin():
        video, _, _ = add_job(session)
        session.add(VideoPermission(video_id=video.id, viewer_uid="viewer"))
        session.flush()
        for video_id in [video.id, uuid4()]:
            with pytest.raises(IntegrityError), session.begin_nested():
                session.add(VideoPermission(video_id=video_id, viewer_uid="viewer"))
                session.flush()


def test_job_and_outbox_rollback_together(schema_engine):
    with pytest.raises(RuntimeError):
        with Session(schema_engine) as session, session.begin():
            _, _, job = add_job(session)
            session.add(OutboxEvent(job_id=job.id, kind="transcode.requested", payload_json={"job_id": str(job.id)}))
            session.flush()
            raise RuntimeError("Simulated failure before commit")
    with Session(schema_engine) as session:
        assert session.scalar(select(func.count()).select_from(TranscodeJob)) == 0
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 0
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(OutboxEvent(job_id=uuid4(), kind="transcode.requested", payload_json={}))
            session.flush()

import json
import shutil
import subprocess

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import OutboxEvent, OutputObject, OutputProfile, TranscodeJob, Video, VideoPermission
from app.seed import load_manifest, seed_database, seed_id
from app.seed_media import generate_media


def counts(engine):
    with Session(engine) as session:
        return {model.__tablename__: session.scalar(select(func.count()).select_from(model)) for model in [Video, OutputProfile, TranscodeJob, OutputObject, VideoPermission, OutboxEvent]}


def test_reference_clips_are_real_and_repeatable(seed_media, tmp_path):
    first = json.loads((seed_media / "manifest.json").read_text())
    second = generate_media(tmp_path / "repeat")
    assert first == second
    assert len(load_manifest(seed_media)) == 10
    for clip in first["clips"]:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(seed_media / clip["file"])], capture_output=True, text=True, check=True, timeout=10)
        info = json.loads(result.stdout)
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
        assert video["codec_name"] == "h264" and audio["codec_name"] == "aac"
        assert video["width"] == 320 and video["height"] == 180
        assert abs(float(info["format"]["duration"]) - clip["expected_duration_seconds"]) < 0.2
        assert float(info["format"]["duration"]) <= 30
        assert int(info["format"]["size"]) <= 50_000_000


def test_modified_media_is_rejected(seed_media, tmp_path):
    shutil.copytree(seed_media, tmp_path / "changed")
    directory = tmp_path / "changed"
    with (directory / "clip-01.mp4").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="manifest"):
        load_manifest(directory)


@pytest.mark.integration
def test_seed_repeat_preserves_ids_and_row_counts(schema_engine, seed_media):
    seed_database(schema_engine, seed_media)
    with Session(schema_engine) as session:
        first_ids = set(session.scalars(select(Video.id)))
    expected = {"videos": 10, "output_profiles": 1, "transcode_jobs": 10, "output_objects": 0, "video_permissions": 5, "outbox_events": 10}
    assert counts(schema_engine) == expected
    seed_database(schema_engine, seed_media)
    assert counts(schema_engine) == expected
    with Session(schema_engine) as session:
        assert set(session.scalars(select(Video.id))) == first_ids
        assert set(session.scalars(select(Video.status))) == {"QUEUED"}
        for event in session.scalars(select(OutboxEvent)):
            job = session.get(TranscodeJob, event.job_id)
            assert event.payload_json["job_id"] == str(job.id)
            assert event.payload_json["source_generation"] == job.source_generation
            assert event.published_at is None


@pytest.mark.integration
def test_seed_conflict_rolls_back_without_overwriting(schema_engine, seed_media):
    seed_database(schema_engine, seed_media)
    with Session(schema_engine) as session, session.begin():
        video = session.scalar(select(Video).limit(1))
        video.title = "Edited by user"
        changed_id = video.id
    before = counts(schema_engine)
    with pytest.raises(ValueError, match="differs"):
        seed_database(schema_engine, seed_media)
    assert counts(schema_engine) == before
    with Session(schema_engine) as session:
        assert session.get(Video, changed_id).title == "Edited by user"


@pytest.mark.integration
def test_seed_failure_removes_earlier_inserts(schema_engine, seed_media):
    with Session(schema_engine) as session, session.begin():
        session.add(Video(
            id=seed_id("video-3"), owner_uid="different-owner", title="Keep existing row",
            input_object="local/existing.mp4", source_generation="local-existing",
            size_bytes=100, mime_type="video/mp4",
        ))
    with pytest.raises(ValueError, match="differs"):
        seed_database(schema_engine, seed_media)
    assert counts(schema_engine) == {
        "videos": 1, "output_profiles": 0, "transcode_jobs": 0,
        "output_objects": 0, "video_permissions": 0, "outbox_events": 0,
    }

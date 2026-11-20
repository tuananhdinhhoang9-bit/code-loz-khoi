import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import OutboxEvent, OutputProfile, TranscodeJob, Video, VideoPermission
from app.seed_media import file_hash


def seed_id(name):
    return uuid5(NAMESPACE_URL, "video-portal:seed:" + name)


def load_manifest(directory):
    directory = Path(directory)
    data = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    clips = data["clips"]
    if data.get("format_version") != 1 or len(clips) != 10:
        raise ValueError("Seed requires format version 1 and exactly ten clips")
    if sorted(c["number"] for c in clips) != list(range(1, 11)):
        raise ValueError("Seed clip numbers must be unique, 1 to 10")
    for clip in clips:
        path = directory / clip["file"]
        if Path(clip["file"]).name != clip["file"] or path.is_symlink():
            raise ValueError("Seed file must be inside the dataset directory")
        if not 0 < path.stat().st_size <= 50_000_000:
            raise ValueError("Seed file exceeds the allowed size")
        if path.stat().st_size != clip["size_bytes"] or file_hash(path) != clip["sha256"]:
            raise ValueError("Seed file does not match its manifest")
        if not 0 < clip["expected_duration_seconds"] <= 30:
            raise ValueError("Seed duration is outside the reference limits")
    return clips


def insert_seed_row(session, model, values, keys=("id",)):
    row = session.get(model, tuple(values[k] for k in keys) if len(keys) > 1 else values[keys[0]])
    if row is not None:
        # Chạy seed lại không ghi đè dữ liệu đã được người dùng sửa hoặc worker xử lý.
        if any(getattr(row, key) != value for key, value in values.items()):
            raise ValueError("Existing seed data differs; use a separate local database")
        return
    session.execute(insert(model).values(**values))


def seed_database(engine, directory):
    clips = load_manifest(directory)
    profile_id = seed_id("mp4-480p")
    with Session(engine) as session, session.begin():
        insert_seed_row(session, OutputProfile, {"id": profile_id, "name": "mp4-480p", "width_max": 854, "height_max": 480, "video_codec": "h264", "audio_codec": "aac"})
        for clip in clips:
            video_id = seed_id(f"video-{clip['number']}")
            job_id = seed_id(f"job-{clip['number']}")
            generation = "local-sha256:" + clip["sha256"]
            insert_seed_row(session, Video, {
                "id": video_id, "owner_uid": clip["owner_uid"], "title": clip["title"],
                "input_object": "local-seed/" + clip["file"], "source_generation": generation,
                "size_bytes": clip["size_bytes"], "mime_type": "video/mp4", "status": "QUEUED",
            })
            insert_seed_row(session, TranscodeJob, {"id": job_id, "video_id": video_id, "source_generation": generation, "profile_id": profile_id, "status": "QUEUED", "attempts": 0, "max_attempts": 3})
            insert_seed_row(session, OutboxEvent, {
                "id": seed_id(f"event-{clip['number']}"), "job_id": job_id, "kind": "transcode.requested",
                "payload_json": {"job_id": str(job_id), "source_generation": generation, "profile_id": str(profile_id)},
            })
            if clip["viewer_uid"]:
                insert_seed_row(session, VideoPermission, {"video_id": video_id, "viewer_uid": clip["viewer_uid"]}, keys=("video_id", "viewer_uid"))

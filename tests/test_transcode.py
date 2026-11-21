import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from worker.transcode import MediaError, probe, transcode, validate_source


@pytest.fixture(scope="module")
def media_cases(tmp_path_factory):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("Real FFmpeg/ffprobe required")
    root = tmp_path_factory.mktemp("worker_inputs")
    cases = [
        ("silent.mp4", 1, "320x180", []),
        ("portrait.mp4", 1, "360x640", []),
        ("long.mp4", 31, "32x32", []),
        ("audio.mp4", 1, "320x180", ["-f", "lavfi", "-i", "sine=sample_rate=44100"]),
        ("oversized_dimensions.mp4", 1, "4100x2", []),
    ]
    for name, seconds, size, audio in cases:
        subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi",
            "-i", f"color=c=blue:size={size}:rate=10", *audio,
            "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast",
            "-threads", "1", "-pix_fmt", "yuv420p", "-c:a", "aac", str(root / name),
        ], check=True, capture_output=True, timeout=30)
    (root / "corrupt.mp4").write_bytes(b"not a video")
    with (root / "huge.mp4").open("wb") as stream:
        stream.truncate(50_000_001)
    subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi",
        "-i", "color=size=32x32:rate=10", "-t", "1", "-c:v", "mjpeg",
        "-threads", "1", str(root / "unsupported.mov"),
    ], check=True, capture_output=True, timeout=30)
    return root


@pytest.mark.parametrize("name,audio", [("silent.mp4", False), ("audio.mp4", True), ("portrait.mp4", False)])
def test_real_transcode_metadata_and_no_audio(media_cases, tmp_path, name, audio):
    output = tmp_path / "attempt"
    result = transcode(media_cases / name, output)
    assert result["mp4_bytes"] > 0 and result["thumbnail_bytes"] > 0
    assert 900 <= result["duration_ms"] <= 1300
    streams = probe(output / "video.mp4")["streams"]
    assert any(s["codec_name"] == "h264" for s in streams)
    assert any(s["codec_type"] == "audio" for s in streams) == audio
    assert result["width"] <= 854 and result["height"] <= 480
    if name == "portrait.mp4":
        assert abs(result["width"] / result["height"] - 360 / 640) < 0.01
    assert (output / "thumbnail.jpg").read_bytes().startswith(b"\xff\xd8")
    assert json.loads((output / "metadata.json").read_text()) == result


@pytest.mark.parametrize("name,code", [
    ("corrupt.mp4", "invalid_media"), ("huge.mp4", "input_size_invalid"),
    ("long.mp4", "input_too_long"), ("unsupported.mov", "unsupported_codec"),
    ("oversized_dimensions.mp4", "invalid_dimensions"),
])
def test_bad_real_inputs_rejected(media_cases, tmp_path, name, code):
    with pytest.raises(MediaError) as error:
        transcode(media_cases / name, tmp_path / "output")
    assert error.value.code == code and not error.value.retryable
    assert not (tmp_path / "output" / "metadata.json").exists()


def test_all_ten_reference_clips(seed_media, tmp_path):
    for path in sorted(seed_media.glob("clip-*.mp4")):
        result = transcode(path, tmp_path / path.stem)
        assert result["width"] <= 854 and result["height"] <= 480


def test_existing_attempt_is_not_overwritten(media_cases, tmp_path):
    output = tmp_path / "attempt"
    output.mkdir()
    (output / "keep.txt").write_text("existing")
    with pytest.raises(MediaError, match="attempt_directory_not_empty"):
        transcode(media_cases / "silent.mp4", output)
    assert (output / "keep.txt").read_text() == "existing"


def test_failure_after_mp4_leaves_no_validated_output(media_cases, tmp_path, monkeypatch):
    import worker.transcode as module
    original = module.run_tool
    def fail_thumbnail(arguments, timeout, error_code):
        if error_code == "thumbnail_failed":
            assert (tmp_path / "attempt" / "video.mp4").is_file()
            raise MediaError("thumbnail_failed")
        return original(arguments, timeout, error_code)
    monkeypatch.setattr(module, "run_tool", fail_thumbnail)
    with pytest.raises(MediaError):
        transcode(media_cases / "silent.mp4", tmp_path / "attempt")
    assert not list((tmp_path / "attempt").iterdir())


@pytest.mark.docker
@pytest.mark.skipif(os.getenv("RUN_DOCKER_TESTS") != "1", reason="Set RUN_DOCKER_TESTS=1 and build video-worker:phase05")
@pytest.mark.parametrize("name,expected", [("silent.mp4", 0), ("audio.mp4", 0), ("corrupt.mp4", 2), ("long.mp4", 2)])
def test_actual_bounded_worker_container(media_cases, tmp_path, name, expected):
    output = tmp_path / "container-output"
    output.mkdir()
    result = subprocess.run([
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--cpus", "1", "--memory", "512m", "--pids-limit", "64",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m",
        "--mount", f"type=bind,source={media_cases.resolve()},target=/input,readonly",
        "--mount", f"type=bind,source={output.resolve()},target=/output",
        "video-worker:phase05", f"/input/{name}", "/output",
    ], capture_output=True, text=True, timeout=140)
    assert result.returncode == expected, result.stderr
    data = json.loads(result.stdout)
    if expected == 0:
        assert data["status"] == "validated"
        assert probe(output / "video.mp4")["streams"][0]["codec_name"] == "h264"
        assert (output / "thumbnail.jpg").is_file()
    else:
        assert data["status"] == "failed" and not (output / "metadata.json").exists()

"""Generate local synthetic source clips, not processed output evidence."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_media(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    clips = []
    for number in range(1, 11):
        path = directory / f"clip-{number:02d}.mp4"
        seconds = 1 + (number - 1) % 3
        subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10",
            "-f", "lavfi", "-i", f"sine=frequency={400 + number * 20}:sample_rate=44100",
            "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "28", "-pix_fmt", "yuv420p", "-threads", "1",
            "-c:a", "aac", "-b:a", "64k", "-fflags", "+bitexact",
            "-flags:v", "+bitexact", "-flags:a", "+bitexact", "-map_metadata", "-1",
            str(path),
        ], check=True, timeout=30, capture_output=True)
        clips.append({
            "number": number, "file": path.name, "title": f"Synthetic clip {number:02d}",
            "owner_uid": "demo-owner", "viewer_uid": "demo-viewer" if number % 2 == 0 else None,
            "size_bytes": path.stat().st_size, "sha256": file_hash(path),
            "expected_duration_seconds": seconds,
            "expected_output": {"profile": "mp4-480p", "video_codec": "h264", "audio_codec": "aac", "thumbnail": "jpg", "width_max": 854, "height_max": 480},
        })
    manifest = {"format_version": 1, "identities": ["demo-owner", "demo-viewer"], "clips": clips}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=".local/seed")
    args = parser.parse_args()
    generate_media(args.output_dir)
    print("Generated 10 synthetic source clips and manifest; no worker outputs claimed.")

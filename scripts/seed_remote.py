"""Seed the ten reference clips into a RUNNING portal through its public API, then check the results.

Unlike `flask seed-db` (which writes local-only rows for development), this uploads the real files the
same way a browser does, so it works against any deployment, including S3 + Fargate. It is repeatable:
a clip whose title is already in the owner's library is not uploaded again.

  python -m app.seed_media --output-dir .local/seed        # generate the dataset once (needs FFmpeg)
  python scripts/seed_remote.py --base-url https://video.example.com --email owner@example.com \
      --viewer viewer@example.com

For every clip it waits for READY and compares the published duration with the manifest's expected
value. Clips with a viewer in the manifest are shared with --viewer. The password comes from the
SEED_PASSWORD environment variable or a prompt, never from the command line.
"""

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from portal_client import Client, resolve_host, sign_in, upload

DURATION_TOLERANCE_MS = 350


def load_clips(directory):
    """Đọc manifest và kiểm tra từng file đúng kích thước, đúng SHA-256 trước khi gửi đi."""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    clips = sorted(manifest["clips"], key=lambda clip: clip["number"])
    if len(clips) != 10:
        raise ValueError("The reference dataset must contain exactly ten clips")
    for clip in clips:
        content = (directory / Path(clip["file"]).name).read_bytes()
        if len(content) != clip["size_bytes"] or hashlib.sha256(content).hexdigest() != clip["sha256"]:
            raise ValueError(f"{clip['file']} does not match its manifest entry")
        clip["content"] = content
    return clips


def send(client, clip):
    """Tạo lượt tải, gửi file, báo hoàn tất. Trả ID video hoặc ném lỗi có mã HTTP."""
    slot = {"title": clip["title"], "mime_type": "video/mp4", "size_bytes": clip["size_bytes"]}
    status, created, _ = client.call("POST", "/api/videos", slot)
    if status != 201:
        raise RuntimeError(f"create returned HTTP {status} {created.get('error', '')}")
    accepted, status = upload(client, created, clip["content"], "video/mp4")
    if not accepted:
        raise RuntimeError(f"upload returned HTTP {status}")
    status, completed, _ = client.call("POST", f"/api/videos/{created['video_id']}/complete")
    if status not in {200, 202}:
        raise RuntimeError(f"complete returned HTTP {status} {completed.get('error', '')}")
    return created["video_id"]


def wait_ready(client, video_ids, timeout):
    """Chờ tới khi mọi video READY hoặc FAILED. Worker xử lý từng video một nên phải chờ cả lô."""
    states = {}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for video_id in video_ids:
            if states.get(video_id, {}).get("status") not in {"READY", "FAILED"}:
                states[video_id] = client.call("GET", f"/api/videos/{video_id}/status")[1]
        if all(state.get("status") in {"READY", "FAILED"} for state in states.values()):
            break
        time.sleep(2)
    return states


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True, help="owner account that will own the ten clips")
    parser.add_argument("--viewer", help="account that gets view permission on the clips marked shared in the manifest")
    parser.add_argument("--media-dir", type=Path, default=Path(".local/seed"))
    parser.add_argument("--timeout", type=int, default=900, help="seconds to wait for all clips")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--resolve", metavar="NAME=IP")
    args = parser.parse_args()
    clips = load_clips(args.media_dir)
    password = os.getenv("SEED_PASSWORD") or getpass.getpass("Password: ")
    if args.resolve:
        resolve_host(args.resolve)
    client = Client(args.base_url, args.insecure)
    client.token = sign_in(client, args.email, password) or ""
    status, me, _ = client.call("GET", "/api/me")
    if not client.token or status != 200:
        print("Sign-in failed")
        return 1

    # Chạy lại không tạo trùng: clip nào đã có trong thư viện của chủ sở hữu thì dùng lại.
    status, listing, _ = client.call("GET", "/api/videos")
    existing = {video["title"]: video["id"] for video in listing.get("videos", []) if video["owner_uid"] == me["uid"]}
    started = time.monotonic()
    video_ids, uploaded = {}, 0
    for clip in clips:
        if clip["title"] in existing:
            video_ids[clip["number"]] = existing[clip["title"]]
            continue
        video_ids[clip["number"]] = send(client, clip)
        uploaded += 1
        print(f"SENT  {clip['file']} ({clip['size_bytes']} bytes)", flush=True)

    states = wait_ready(client, list(video_ids.values()), args.timeout)
    failures = 0
    for clip in clips:
        video_id = video_ids[clip["number"]]
        state = states.get(video_id, {})
        problem = ""
        if state.get("status") != "READY":
            problem = f"status {state.get('status')} ({state.get('error_code')})"
        else:
            status, playback, _ = client.call("GET", f"/api/videos/{video_id}/playback")
            expected = clip["expected_duration_seconds"] * 1000
            if status != 200:
                problem = f"playback returned HTTP {status}"
            elif abs(playback.get("duration_ms", 0) - expected) > DURATION_TOLERANCE_MS:
                problem = f"duration {playback.get('duration_ms')} ms, expected {expected} ms"
            elif client.call("GET", f"/api/videos/{video_id}/thumbnail")[0] != 200:
                problem = "thumbnail not available"
        if not problem and clip.get("viewer_uid") and args.viewer:
            grant = {"viewer_uid": args.viewer.strip().lower(), "action": "grant"}
            if client.call("POST", f"/api/videos/{video_id}/permissions", grant)[0] != 200:
                problem = "permission grant failed"
        failures += bool(problem)
        print(("FAIL  " if problem else "PASS  ") + f"{clip['title']}" + (f": {problem}" if problem else ""), flush=True)

    summary = {"clips": len(clips), "uploaded_now": uploaded, "already_present": len(clips) - uploaded, "failed": failures,
               "shared_with_viewer": sum(1 for clip in clips if clip.get("viewer_uid")) if args.viewer else 0,
               "total_seconds": round(time.monotonic() - started, 1)}
    print("SEED_RESULT " + json.dumps(summary))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

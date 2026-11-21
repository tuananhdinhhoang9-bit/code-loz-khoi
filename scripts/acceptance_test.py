"""Run the instructor's three acceptance tests against a RUNNING portal through its public API.

  Test 1  every valid clip is processed, plays (HTTP Range) and matches the output profile
  Test 2  wrong type, corrupt file, clip longer than 30 s and file over the size limit are refused cleanly
  Test 3  repeating an event gives one result; a caller without permission gets neither the API nor the file

  python -m app.seed_media --output-dir .local/seed        # the ten reference clips, once (needs FFmpeg)
  python scripts/acceptance_test.py --base-url https://video.example.com --email admin@example.com

Sign in with an ADMINISTRATOR of a portal that uses local accounts: the script creates (or re-enables) the
helper account below with a random password that is never printed or stored, uses it as "the other user",
and disables it again at the end. The administrator's password comes from ACCEPT_PASSWORD or a prompt.
FFmpeg/ffprobe on PATH are needed for the profile check and the too-long clip; without them those checks
are reported as SKIP, not as PASS. The ten clips stay in the library (they are the demo data); everything
else the script uploads is deleted. What it cannot do from outside: make the queue deliver a message
twice or kill a worker — that is the failure drill, run on the server side.
"""

import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile

from portal_client import Client, sign_in, tampered, upload
from seed_remote import DURATION_TOLERANCE_MS, load_clips, send, wait_ready

HELPER = "acceptance-viewer@example.test"
results = []


def check(condition, label):
    results.append(("PASS" if condition else "FAIL", label))
    print(f"{results[-1][0]}  {label}", flush=True)
    return condition


def skip(label, reason):
    results.append(("SKIP", label))
    print(f"SKIP  {label} ({reason})", flush=True)


def probe(content):
    """Đọc codec, kích thước và container của file kết quả bằng ffprobe chạy trên máy này."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "output.mp4"
        path.write_bytes(content)
        fields = "stream=codec_type,codec_name,pix_fmt,width,height:format=format_name"
        done = subprocess.run(["ffprobe", "-v", "error", "-show_entries", fields, "-of", "json", str(path)],
                              capture_output=True, text=True, timeout=60)
    return json.loads(done.stdout or "{}")


def matches_profile(info):
    """Profile đầu ra của dự án: MP4, đúng một luồng H.264 yuv420p không quá 854x480, âm thanh (nếu có) là AAC."""
    streams = info.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    return ("mp4" in info.get("format", {}).get("format_name", "") and len(videos) == 1
            and videos[0].get("codec_name") == "h264" and videos[0].get("pix_fmt") == "yuv420p"
            and 0 < videos[0].get("width", 0) <= 854 and 0 < videos[0].get("height", 0) <= 480
            and all(s.get("codec_name") == "aac" for s in audios))


def long_clip():
    """Một MP4 hợp lệ dài 35 giây, tạo bằng FFmpeg trên máy này."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "long.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=15", "-f", "lavfi",
                        "-i", "sine=frequency=440", "-t", "35", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-y", str(path)], check=True, timeout=120)
        return path.read_bytes()


def create(client, title, mime_type, size):
    return client.call("POST", "/api/videos", {"title": title, "mime_type": mime_type, "size_bytes": size})[:2]


def test_valid_clips(owner, clips, timeout):
    """Test 1. Clip đã có sẵn trong thư viện (cùng tiêu đề) được dùng lại nên chạy nhiều lần không tạo trùng."""
    me = owner.call("GET", "/api/me")[1]
    listing = owner.call("GET", "/api/videos")[1].get("videos", [])
    existing = {video["title"]: video["id"] for video in listing if video["owner_uid"] == me["uid"]}
    video_ids = {clip["number"]: existing.get(clip["title"]) or send(owner, clip) for clip in clips}
    states = wait_ready(owner, list(video_ids.values()), timeout)
    can_probe = shutil.which("ffprobe") is not None
    for clip in clips:
        video = f"/api/videos/{video_ids[clip['number']]}"
        state = states.get(video_ids[clip["number"]], {})
        if not check(state.get("status") == "READY", f"{clip['title']}: processed ({state.get('status')} {state.get('error_code') or ''})"):
            continue
        status, playback, _ = owner.call("GET", video + "/playback")
        expected = clip["expected_duration_seconds"] * 1000
        check(status == 200 and abs(playback.get("duration_ms", 0) - expected) <= DURATION_TOLERANCE_MS,
              f"{clip['title']}: playback URL issued, duration {playback.get('duration_ms')} ms (expected {expected})")
        if status != 200:
            continue
        status, part, headers = owner.call("GET", playback["url"], headers={"Range": "bytes=0-1023"}, auth=False, raw=True)
        ranged = status == 206 and len(part) == 1024 and headers.get("Content-Range", "").startswith("bytes 0-1023/")
        status, whole, headers = owner.call("GET", playback["url"], auth=False, raw=True)
        check(ranged and status == 200 and whole[4:8] == b"ftyp" and headers.get("Content-Type") == "video/mp4",
              f"{clip['title']}: served as video/mp4 with Range support ({len(whole)} bytes)")
        if can_probe:
            check(matches_profile(probe(whole)), f"{clip['title']}: output is MP4 / H.264 yuv420p / at most 854x480 / AAC")
        thumbnail = owner.call("GET", video + "/thumbnail")[1]
        image = owner.call("GET", thumbnail.get("url", "/missing"), auth=False, raw=True)[1]
        check(image[:2] == b"\xff\xd8", f"{clip['title']}: thumbnail is a JPEG")
    if not can_probe:
        skip("output profile read with ffprobe", "ffprobe is not on PATH")
    return video_ids


def test_rejections(owner, limit, timeout):
    """Test 2. Mỗi trường hợp phải bị từ chối bằng mã lỗi rõ ràng và không bao giờ thành READY."""
    status, body = create(owner, "Acceptance: wrong type", "text/plain", 1000)
    check(status == 400 and body.get("error") == "unsupported_content_type", f"wrong content type refused at creation (HTTP {status} {body.get('error')})")
    status, body = create(owner, "Acceptance: too big", "video/mp4", limit + 1)
    check(status == 413 and body.get("error") == "upload_too_large", f"declared size over {limit} bytes refused at creation (HTTP {status} {body.get('error')})")

    # Khai đúng giới hạn nhưng gửi nhiều hơn một byte: máy chủ không được tin kích thước do client khai.
    status, slot = create(owner, "Acceptance: oversized upload", "video/mp4", limit)
    if check(status == 201, "slot for the oversized upload created"):
        video = f"/api/videos/{slot['video_id']}"
        accepted, put_status = upload(owner, slot, bytes(limit + 1), "video/mp4")
        status, body, _ = owner.call("POST", video + "/complete")
        check((not accepted and put_status == 413) or (status == 413 and body.get("error") == "upload_too_large"),
              f"file one byte over the limit refused (upload HTTP {put_status}, complete HTTP {status} {body.get('error')})")
        check(owner.call("GET", video + "/playback")[0] == 409, "oversized upload has no playback")
        owner.call("DELETE", video)

    queued = {"corrupt file": (b"this is not a video\n" * 200, None)}
    if shutil.which("ffmpeg"):
        queued["clip of 35 seconds"] = (long_clip(), "input_too_long")
    else:
        skip("clip longer than 30 seconds is refused", "ffmpeg is not on PATH to generate one")
    videos = {}
    for name, (content, _) in queued.items():
        status, slot = create(owner, "Acceptance: " + name, "video/mp4", len(content))
        if check(status == 201 and upload(owner, slot, content, "video/mp4")[0]
                 and owner.call("POST", f"/api/videos/{slot['video_id']}/complete")[0] == 202, f"{name}: stored privately and queued for validation"):
            videos[name] = slot["video_id"]
    states = wait_ready(owner, list(videos.values()), timeout)
    for name, video_id in videos.items():
        state, wanted = states.get(video_id, {}), queued[name][1]
        check(state.get("status") == "FAILED" and state.get("error_code") and wanted in (None, state.get("error_code")),
              f"{name}: rejected by the worker ({state.get('status')} {state.get('error_code')})")
        check(owner.call("GET", f"/api/videos/{video_id}/playback")[0] == 409, f"{name}: no playback URL")
        check(owner.call("DELETE", f"/api/videos/{video_id}")[0] == 200, f"{name}: rejected upload deleted")


def helper_account(owner):
    """Tài khoản thường dùng làm "người khác". Mật khẩu ngẫu nhiên chỉ nằm trong bộ nhớ của lần chạy này."""
    password = secrets.token_urlsafe(24)
    status = owner.call("POST", "/api/users", {"email": HELPER, "password": password})[0]
    if status == 409:
        status = owner.call("POST", "/api/users/password", {"email": HELPER, "password": password})[0]
        owner.call("POST", "/api/users/active", {"email": HELPER, "active": True})
    if status not in {200, 201}:
        return None
    other = Client(owner.base, owner.context is not None)
    other.token = sign_in(other, HELPER, password) or ""
    return other if other.token else None


def test_idempotency(owner, video):
    """Test 3, nửa đầu: gửi lại sự kiện hoàn tất của một video đã xong không được tạo job hay kết quả thứ hai."""
    before = owner.call("GET", video + "/playback")[1]
    first = owner.call("POST", video + "/complete")
    second = owner.call("POST", video + "/complete")
    after = owner.call("GET", video + "/playback")[1]
    check(first[0] == 200 and second[0] == 200 and first[1].get("job_id") and first[1].get("job_id") == second[1].get("job_id"),
          f"repeating the completion event returns the same job (HTTP {first[0]}, {second[0]})")
    same_object = before.get("url", "a").split("?")[0] == after.get("url", "b").split("?")[0] or "/local-storage/" in before.get("url", "")
    check(owner.call("GET", video + "/status")[1].get("status") == "READY" and before.get("duration_ms") == after.get("duration_ms") and same_object,
          "the video still has its one published result")


def test_privacy(owner, other, video):
    """Test 3, nửa sau: gọi thẳng API và URL lưu trữ mà không có quyền."""
    anonymous = Client(owner.base, owner.context is not None)
    refused = [anonymous.call("GET", video + path)[0] for path in ("", "/status", "/playback", "/thumbnail")]
    check(refused == [401] * 4, f"no token: metadata, status, playback and thumbnail refused {refused}")
    check(anonymous.call("GET", "/api/videos", headers={"Authorization": "Bearer " + "x" * 43})[0] == 401, "made-up token refused (401)")

    playback = owner.call("GET", video + "/playback")[1]
    bare = anonymous.call("GET", playback["url"].split("?")[0], raw=True)
    check(bare[0] in {403, 404, 409} and bare[1][4:8] != b"ftyp", f"storage URL without its signature gives no video (HTTP {bare[0]})")
    forged = anonymous.call("GET", tampered(playback["url"]), raw=True)
    check(forged[0] == 403 and forged[1][4:8] != b"ftyp", f"storage URL with a changed signature refused (HTTP {forged[0]})")

    if other is None:
        skip("second signed-in user without permission is refused", "needs an administrator on a portal with local accounts")
        return
    video_id = video.rsplit("/", 1)[1]
    listed = [item["id"] for item in other.call("GET", "/api/videos")[1].get("videos", [])]
    refused = [other.call("GET", video + path)[0] for path in ("", "/status", "/playback", "/thumbnail")]
    check(video_id not in listed and refused == [404] * 4, f"other user: not listed; metadata, status, playback and thumbnail refused {refused}")
    grant = {"viewer_uid": HELPER, "action": "grant"}
    check(other.call("POST", video + "/permissions", grant)[0] == 404 and other.call("DELETE", video)[0] == 404,
          "other user can neither grant themselves access nor delete the video")
    check(owner.call("GET", video + "/status")[1].get("status") == "READY", "the owner's video is untouched")

    check(owner.call("POST", video + "/permissions", grant)[0] == 200, "owner grants view permission")
    status, shared, _ = other.call("GET", video + "/playback")
    part = other.call("GET", shared.get("url", "/missing"), headers={"Range": "bytes=0-1023"}, auth=False, raw=True)
    check(status == 200 and part[0] == 206, "permitted viewer gets a playback URL and the bytes")
    check(other.call("DELETE", video)[0] == 404, "permitted viewer still cannot delete")
    owner.call("POST", video + "/permissions", {"viewer_uid": HELPER, "action": "revoke"})
    check(other.call("GET", video + "/playback")[0] == 404, "after revoke the viewer is refused again")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True, help="administrator that will own the ten clips")
    parser.add_argument("--media-dir", type=Path, default=Path(".local/seed"))
    parser.add_argument("--timeout", type=int, default=900, help="seconds to wait for each batch of clips")
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()
    clips = load_clips(args.media_dir)
    password = os.getenv("ACCEPT_PASSWORD") or getpass.getpass("Password: ")
    owner = Client(args.base_url, args.insecure)
    owner.token = sign_in(owner, args.email, password) or ""
    config = owner.call("GET", "/api/config", auth=False)[1]
    if not owner.token or owner.call("GET", "/api/me")[0] != 200:
        print("Sign-in failed")
        return 1

    print("TEST 1  valid clips play and match the output profile", flush=True)
    video_ids = test_valid_clips(owner, clips, args.timeout)
    print("TEST 2  invalid uploads are refused cleanly", flush=True)
    test_rejections(owner, config.get("max_upload_bytes", 50_000_000), args.timeout)
    print("TEST 3  one result per event; no access without permission", flush=True)
    video = f"/api/videos/{video_ids[clips[0]['number']]}"
    other = helper_account(owner) if config.get("auth_provider") == "local" else None
    try:
        test_idempotency(owner, video)
        test_privacy(owner, other, video)
    finally:
        if other is not None:
            owner.call("POST", "/api/users/active", {"email": HELPER, "active": False})

    counts = {state: sum(1 for result, _ in results if result == state) for state in ("PASS", "FAIL", "SKIP")}
    print("ACCEPTANCE_RESULT " + json.dumps({"passed": counts["PASS"], "failed": counts["FAIL"], "skipped": counts["SKIP"],
                                             "storage": "blob" if "blob.core.windows.net" in owner.call("GET", video + "/playback")[1].get("url", "") else "local"}))
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())

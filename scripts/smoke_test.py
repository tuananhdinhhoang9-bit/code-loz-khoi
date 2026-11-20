"""End-to-end smoke test against a RUNNING portal (API + worker, optionally behind Caddy).

It signs in with a local account, uploads one real clip, waits for the worker, plays it back with
HTTP Range, checks that unauthenticated/forged requests are refused, then deletes the clip.

  python scripts/smoke_test.py --base-url https://localhost --email you@example.com --clip clip.mp4

The password comes from the SMOKE_PASSWORD environment variable or an interactive prompt; it is
never accepted on the command line. --insecure skips certificate checks and is only meant for
Caddy's internal (non-public) certificate on localhost.
"""

import argparse
import getpass
import json
import os
from pathlib import Path
import ssl
import sys
import time
import urllib.error
import urllib.request


class Client:
    def __init__(self, base_url, insecure):
        self.base = base_url.rstrip("/")
        self.context = ssl._create_unverified_context() if insecure else None
        self.token = ""

    def call(self, method, path, body=None, headers=None, auth=True, raw=False):
        url = path if path.startswith("http") else self.base + path
        headers = dict(headers or {})
        if auth and self.token:
            headers["Authorization"] = "Bearer " + self.token
        if body is not None and not isinstance(body, bytes):
            body = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=600, context=self.context)
        except urllib.error.HTTPError as error:
            response = error
        data = response.read()
        if raw:
            return response.status, data, response.headers
        try:
            return response.status, json.loads(data), response.headers
        except ValueError:
            return response.status, {}, response.headers


def check(condition, label, results):
    results.append((label, bool(condition)))
    print(("PASS  " if condition else "FAIL  ") + label, flush=True)
    return condition


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--clip", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=600, help="seconds to wait for processing")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--keep", action="store_true", help="do not delete the uploaded clip")
    args = parser.parse_args()
    password = os.getenv("SMOKE_PASSWORD") or getpass.getpass("Password: ")
    client = Client(args.base_url, args.insecure)
    results, timings = [], {}
    content = args.clip.read_bytes()

    status, health, headers = client.call("GET", "/health", auth=False)
    check(status == 200 and health.get("database") == "ok", "health endpoint reports database ok", results)
    check("waitress" not in (headers.get("Server") or "").lower(), "server software is not advertised", results)
    status, config, _ = client.call("GET", "/api/config", auth=False)
    check(status == 200 and config.get("auth_provider") == "local", "portal uses local accounts", results)
    check(client.call("GET", "/api/videos", auth=False)[0] == 401, "listing without a token is refused (401)", results)
    check(client.call("POST", "/api/auth/login", {"email": args.email, "password": "definitely-wrong-password"}, auth=False)[0] == 401,
          "wrong password is refused (401)", results)
    status, session, _ = client.call("POST", "/api/auth/login", {"email": args.email, "password": password}, auth=False)
    if not check(status == 200 and session.get("token"), "sign-in succeeds", results):
        return 1
    client.token = session["token"]

    started = time.monotonic()
    status, created, _ = client.call("POST", "/api/videos", {"title": "Smoke test clip", "mime_type": "video/mp4", "size_bytes": len(content)})
    if not check(status == 201, f"upload slot created ({len(content)} bytes)", results):
        print(created)
        return 1
    video = "/api/videos/" + created["video_id"]
    status, _, _ = client.call("PUT", created["upload_url"], content, {"Content-Type": "video/mp4"}, auth=False)
    timings["upload_seconds"] = round(time.monotonic() - started, 2)
    check(status == 201, "private upload accepted", results)
    check(client.call("PUT", created["upload_url"], content, {"Content-Type": "video/mp4"}, auth=False)[0] == 409,
          "second upload to the same slot is refused (no overwrite)", results)
    status, completed, _ = client.call("POST", video + "/complete")
    if not check(status == 202, f"job queued (HTTP {status} {completed.get('error', '')})", results):
        return 1
    check(client.call("GET", video + "/playback")[0] == 409, "playback is refused before processing finishes", results)

    queued = time.monotonic()
    state, progress = {}, set()
    while time.monotonic() - queued < args.timeout:
        _, state, _ = client.call("GET", video + "/status")
        if state.get("progress_percent") is not None:
            progress.add(state["progress_percent"])
        if state.get("status") in {"READY", "FAILED"}:
            break
        time.sleep(0.5)
    timings["processing_seconds"] = round(time.monotonic() - queued, 2)
    timings["progress_values_seen"] = sorted(progress)
    if not check(state.get("status") == "READY", f"worker finished: {state.get('status')} ({state.get('error_code')})", results):
        return 1

    status, playback, _ = client.call("GET", video + "/playback")
    check(status == 200 and playback.get("duration_ms", 0) > 0, "authorized playback URL issued", results)
    status, part, headers = client.call("GET", playback["url"], headers={"Range": "bytes=0-1023"}, auth=False, raw=True)
    check(status == 206 and len(part) == 1024 and headers.get("Content-Range", "").startswith("bytes 0-1023/"), "Range request returns 206 partial content", results)
    status, whole, _ = client.call("GET", playback["url"], auth=False, raw=True)
    check(status == 200 and whole[4:8] == b"ftyp", "full MP4 is served", results)
    timings["output_bytes"] = len(whole)
    status, thumbnail, _ = client.call("GET", video + "/thumbnail")
    status, image, _ = client.call("GET", thumbnail["url"], auth=False, raw=True)
    check(status == 200 and image[:2] == b"\xff\xd8", "thumbnail is a JPEG", results)
    forged = playback["url"][:-6] + "AAAAAA"
    check(client.call("GET", forged, auth=False, raw=True)[0] == 403, "tampered storage ticket is refused (403)", results)
    check(client.call("GET", video + "/playback", auth=False)[0] == 401, "playback without a token is refused (401)", results)

    if not args.keep:
        check(client.call("DELETE", video)[0] == 200, "owner can delete the clip", results)
        check(client.call("GET", video + "/status")[0] == 404, "deleted clip is gone", results)
    check(client.call("POST", "/api/auth/logout")[0] == 200, "sign-out succeeds", results)
    check(client.call("GET", "/api/me")[0] == 401, "token no longer works after sign-out", results)

    failed = [label for label, ok in results if not ok]
    print("SMOKE_RESULT " + json.dumps({"passed": len(results) - len(failed), "failed": len(failed), **timings}))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

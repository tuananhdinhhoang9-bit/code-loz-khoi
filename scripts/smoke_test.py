"""End-to-end smoke test against a RUNNING portal (API + worker behind Caddy or Azure Container Apps).

It signs in (local account, or an OIDC ID token taken from PORTAL_ID_TOKEN, whichever the portal reports),
uploads one real clip the way the server asks (PUT to the portal, or PUT to a Blob Storage SAS URL), waits for the worker, plays
the result back with HTTP Range, checks that unauthenticated/forged requests are refused, then deletes
the clip.

  python scripts/smoke_test.py --base-url https://localhost --email you@example.com --clip clip.mp4

The password comes from the SMOKE_PASSWORD environment variable or an interactive prompt; it is
never accepted on the command line. --insecure skips certificate checks and is only meant for
Caddy's internal (non-public) certificate on localhost. --resolve NAME=IP connects to IP while
keeping NAME for TLS and the Host header (test a load balancer before its DNS record exists).
"""

import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import time

from portal_client import Client, resolve_host, sign_in, tampered, upload


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
    parser.add_argument("--resolve", metavar="NAME=IP")
    parser.add_argument("--keep", action="store_true", help="do not delete the uploaded clip")
    args = parser.parse_args()
    password = os.getenv("SMOKE_PASSWORD") or getpass.getpass("Password: ")
    if args.resolve:
        resolve_host(args.resolve)
    client = Client(args.base_url, args.insecure)
    results, timings = [], {}
    content = args.clip.read_bytes()

    status, health, headers = client.call("GET", "/health", auth=False)
    check(status == 200 and health.get("database") == "ok", "health endpoint reports database ok", results)
    check("waitress" not in (headers.get("Server") or "").lower(), "server software is not advertised", results)
    status, config, _ = client.call("GET", "/api/config", auth=False)
    provider = config.get("auth_provider")
    check(status == 200 and provider in {"local", "oidc"}, f"portal reports its sign-in provider ({provider})", results)
    check(client.call("GET", "/api/videos", auth=False)[0] == 401, "listing without a token is refused (401)", results)
    if provider == "local":
        # Với OIDC mật khẩu không đi qua script này nên không có gì để thử sai.
        check(sign_in(client, args.email, "definitely-wrong-password") is None, "wrong password is refused", results)
    client.token = sign_in(client, args.email, password) or ""
    if not check(client.token and client.call("GET", "/api/me")[0] == 200, "sign-in succeeds and the API accepts the token", results):
        return 1

    started = time.monotonic()
    slot = {"title": "Smoke test clip", "mime_type": "video/mp4", "size_bytes": len(content)}
    status, created, _ = client.call("POST", "/api/videos", slot)
    if not check(status == 201, f"upload slot created ({len(content)} bytes)", results):
        print(created)
        return 1
    video = "/api/videos/" + created["video_id"]
    to_blob = "x-ms-blob-type" in (created.get("upload_headers") or {})
    timings["storage"] = "blob" if to_blob else "local"
    accepted, status = upload(client, created, content, "video/mp4")
    timings["upload_seconds"] = round(time.monotonic() - started, 2)
    check(accepted, f"private upload accepted (HTTP {status})", results)
    if not to_blob:
        # Với Blob Storage, SAS không giới hạn kích thước và việc chống ghi đè do quyền "create" của SAS lo; chưa kiểm ở đây.
        check(upload(client, created, content, "video/mp4")[1] == 409, "second upload to the same slot is refused (no overwrite)", results)
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
    check(client.call("GET", tampered(playback["url"]), auth=False, raw=True)[0] == 403, "tampered storage signature is refused (403)", results)
    check(client.call("GET", playback["url"].split("?")[0], auth=False, raw=True)[0] == 403, "storage URL without a signature is refused (403)", results)
    check(client.call("GET", video + "/playback", auth=False)[0] == 401, "playback without a token is refused (401)", results)

    if not args.keep:
        check(client.call("DELETE", video)[0] == 200, "owner can delete the clip", results)
        check(client.call("GET", video + "/status")[0] == 404, "deleted clip is gone", results)
    check(client.call("POST", "/api/auth/logout")[0] == 200, "sign-out succeeds", results)
    if provider == "local":
        check(client.call("GET", "/api/me")[0] == 401, "token no longer works after sign-out", results)
    else:
        # ID token OIDC không thu hồi được ở phía API; nó tự hết hạn theo cấu hình của nhà cung cấp.
        print("NOTE  OIDC ID tokens stay valid until they expire; sign-out revocation is not checked", flush=True)

    failed = [label for label, ok in results if not ok]
    print("SMOKE_RESULT " + json.dumps({"passed": len(results) - len(failed), "failed": len(failed), **timings}))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

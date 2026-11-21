"""Small API load test against a RUNNING portal: several signed-in users reading at the same time.

Each simulated user keeps one HTTPS connection open (like a browser) and repeats, without pausing:
library list -> status of a video -> playback URL of a video -> status of a video. Only READY videos of
the signed-in account are used, so every request should be answered 200. After a warm-up that is not
counted, every request is timed for the measurement period; p50/p95/p99 come from those real samples.

  python scripts/load_test.py --base-url https://video.example.com --email owner@example.com
  python scripts/load_test.py --base-url ... --email ... --users 10 --warmup 10 --duration 60

What it does not measure: uploads and transcoding (one video at a time by design) and the download of
the video bytes, which the browser fetches from storage, not from the API. The times include the
network between this machine and the portal. The password comes from LOAD_PASSWORD or a prompt.
"""

import argparse
import getpass
import http.client
import json
import os
import random
import ssl
import sys
import threading
import time
from urllib.parse import urlsplit

from portal_client import Client, sign_in


def percentile(sorted_values, percent):
    """Phân vị theo cách "nearest rank": giá trị thật trong mẫu, không nội suy."""
    if not sorted_values:
        return None
    rank = max(1, -(-len(sorted_values) * percent // 100))
    return sorted_values[int(rank) - 1]


def summary(samples):
    times = sorted(sample[2] for sample in samples)
    errors = sum(1 for sample in samples if sample[1] != 200)
    return {"requests": len(samples), "errors": errors, "error_rate_percent": round(100 * errors / len(samples), 2) if samples else None,
            "p50_ms": percentile(times, 50), "p95_ms": percentile(times, 95), "p99_ms": percentile(times, 99), "max_ms": times[-1] if times else None}


def connect(url, insecure):
    if url.scheme != "https":
        return http.client.HTTPConnection(url.netloc, timeout=30)
    context = ssl._create_unverified_context() if insecure else ssl.create_default_context()
    return http.client.HTTPSConnection(url.netloc, timeout=30, context=context)


def user(number, url, token, video_ids, measure_from, stop_at, samples, insecure):
    """Một người dùng: lặp bốn request cho tới hết giờ. Lỗi kết nối được ghi là mã 0 rồi nối lại."""
    choose = random.Random(number)
    headers = {"Authorization": "Bearer " + token}
    connection, step = connect(url, insecure), 0
    while time.perf_counter() < stop_at:
        video = choose.choice(video_ids)
        name, path = [("list", "/api/videos"), ("status", f"/api/videos/{video}/status"),
                      ("playback", f"/api/videos/{video}/playback"), ("status", f"/api/videos/{video}/status")][step % 4]
        step += 1
        started = time.perf_counter()
        try:
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            response.read()
            status = response.status
        except (OSError, http.client.HTTPException):
            status = 0
            connection.close()
            connection = connect(url, insecure)
        if started >= measure_from:
            samples.append((name, status, round((time.perf_counter() - started) * 1000, 1)))
    connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--users", type=int, default=10, help="concurrent users")
    parser.add_argument("--warmup", type=int, default=10, help="seconds that are not counted")
    parser.add_argument("--duration", type=int, default=60, help="seconds that are measured")
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()
    if not (1 <= args.users <= 50 and 0 <= args.warmup <= 120 and 1 <= args.duration <= 600):
        parser.error("keep it small: users 1-50, warmup 0-120, duration 1-600")
    password = os.getenv("LOAD_PASSWORD") or getpass.getpass("Password: ")
    client = Client(args.base_url, args.insecure)
    client.token = sign_in(client, args.email, password) or ""
    status, listing, _ = client.call("GET", "/api/videos")
    if not client.token or status != 200:
        print("Sign-in failed")
        return 1
    video_ids = [video["id"] for video in listing.get("videos", []) if video.get("status") == "READY"]
    if not video_ids:
        print("No READY video in this account's library; seed the reference clips first")
        return 1

    samples = []
    begin = time.perf_counter()
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + args.warmup))
    threads = [threading.Thread(target=user, args=(number, urlsplit(args.base_url), client.token, video_ids, begin + args.warmup,
                                                   begin + args.warmup + args.duration, samples, args.insecure))
               for number in range(args.users)]
    print(f"{args.users} users, warm-up {args.warmup} s, measuring {args.duration} s on {len(video_ids)} READY videos ...", flush=True)
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    ended_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for name in ("list", "status", "playback"):
        part = summary([sample for sample in samples if sample[0] == name])
        print(f"{name:9} {part['requests']:6} requests  {part['errors']:4} errors  p50 {part['p50_ms']} ms  p95 {part['p95_ms']} ms  p99 {part['p99_ms']} ms  max {part['max_ms']} ms", flush=True)
    codes = {}
    for sample in samples:
        codes[str(sample[1])] = codes.get(str(sample[1]), 0) + 1
    result = {"users": args.users, "warmup_seconds": args.warmup, "duration_seconds": args.duration, "videos": len(video_ids),
              "measured_from_utc": started_utc, "measured_to_utc": ended_utc, **summary(samples),
              "requests_per_second": round(len(samples) / args.duration, 1), "status_codes": codes}
    print("LOAD_RESULT " + json.dumps(result))
    return 0 if samples and result["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

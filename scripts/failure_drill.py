"""Failure drill against a RUNNING portal: kill the worker in the middle of a transcode and watch the recovery.

It uploads one clip, waits until the portal reports measured FFmpeg progress for it, then runs the command
given in --on-processing (the command must stop the worker: see scripts/azure/Stop-TranscodeExecution.ps1,
or stop the local worker process). After that it only watches: every change of status is printed with its
time, and at the end it checks that nothing was published while the worker was dead, that a retry
happened and that exactly one result can be played.

  python scripts/failure_drill.py --base-url https://video.example.com --email owner@example.com \
      --clip heavy.mp4 --on-processing "powershell -File scripts/azure/Stop-TranscodeExecution.ps1 -Apply"

Use a clip that takes the worker well over ten seconds, otherwise it finishes before it can be stopped
and the drill reports that honestly as a failure. The password comes from DRILL_PASSWORD or a prompt.
Recovery waits for the queue's message lock and the job's lease to expire, so allow several minutes.
"""

import argparse
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from portal_client import Client, sign_in, upload

results = []


def check(condition, label):
    results.append(bool(condition))
    print(("PASS  " if condition else "FAIL  ") + label, flush=True)
    return condition


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--clip", required=True, type=Path)
    parser.add_argument("--on-processing", required=True, help="command that stops the worker; run once, when progress is first reported")
    parser.add_argument("--timeout", type=int, default=1500, help="seconds to wait for the recovery")
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()
    content = args.clip.read_bytes()
    password = os.getenv("DRILL_PASSWORD") or getpass.getpass("Password: ")
    client = Client(args.base_url, args.insecure)
    client.token = sign_in(client, args.email, password) or ""
    if not client.token:
        print("Sign-in failed")
        return 1

    status, created, _ = client.call("POST", "/api/videos", {"title": "Failure drill clip", "mime_type": "video/mp4", "size_bytes": len(content)})
    if status != 201 or not upload(client, created, content, "video/mp4")[0]:
        print(f"Upload failed (HTTP {status})")
        return 1
    video = "/api/videos/" + created["video_id"]
    status, completed, _ = client.call("POST", video + "/complete")
    print(f"QUEUED video {created['video_id']} job {completed.get('job_id')} ({len(content)} bytes)", flush=True)

    started, timeline, killed_at, last = time.monotonic(), [], None, None
    during_outage, state = [], {}
    while time.monotonic() - started < args.timeout:
        _, state, _ = client.call("GET", video + "/status")
        elapsed = round(time.monotonic() - started, 1)
        key = (state.get("status"), state.get("error_code"))
        if key != last:
            last = key
            timeline.append({"t": elapsed, "status": key[0], "error_code": key[1], "progress_percent": state.get("progress_percent")})
            print(f"{time.strftime('%H:%M:%S', time.gmtime())}Z  +{elapsed:>6}s  {key[0]} {key[1] or ''} progress={state.get('progress_percent')}", flush=True)
        if killed_at is None and key[0] == "PROCESSING" and (state.get("progress_percent") or 0) > 0:
            # Tiến độ đo được > 0 nghĩa là FFmpeg đang chạy thật: đây là "giữa chừng".
            done = subprocess.run(args.on_processing, shell=True)
            killed_at = round(time.monotonic() - started, 1)
            timeline.append({"t": killed_at, "status": "WORKER_STOPPED", "error_code": None, "progress_percent": state.get("progress_percent")})
            print(f"{time.strftime('%H:%M:%S', time.gmtime())}Z  +{killed_at:>6}s  stop command exit code {done.returncode} at progress {state.get('progress_percent')}", flush=True)
            during_outage.append(client.call("GET", video + "/playback")[0])
        elif killed_at is not None and key[0] not in {"READY", "FAILED"} and len(during_outage) < 200:
            if int(elapsed) % 15 == 0:
                during_outage.append(client.call("GET", video + "/playback")[0])
        if key[0] in {"READY", "FAILED"}:
            break
        time.sleep(0.5)

    statuses = [step["status"] for step in timeline]
    stopped = "WORKER_STOPPED" in statuses
    check(stopped, "worker stopped while FFmpeg was running (measured progress above 0)")
    after = statuses[statuses.index("WORKER_STOPPED") + 1:] if stopped else []
    check(stopped and set(during_outage) == {409}, f"no playback URL while the result was not finished ({len(during_outage)} probes, all 409)")
    check("PROCESSING" in after, "the job was processed again after the stop (retry)")
    check(state.get("status") == "READY", f"final status {state.get('status')} {state.get('error_code') or ''}")
    status, playback, _ = client.call("GET", video + "/playback")
    whole = client.call("GET", playback.get("url", "/missing"), auth=False, raw=True)[1] if status == 200 else b""
    check(status == 200 and playback.get("duration_ms", 0) > 0 and whole[4:8] == b"ftyp", f"one playable result ({len(whole)} bytes, {playback.get('duration_ms')} ms)")
    repeat = client.call("POST", video + "/complete")
    check(repeat[0] == 200 and repeat[1].get("job_id") == completed.get("job_id"), "still the same single job for this video")

    recover = round(timeline[-1]["t"] - killed_at, 1) if stopped and state.get("status") == "READY" else None
    print("DRILL_RESULT " + json.dumps({"passed": sum(results), "failed": len(results) - sum(results), "video_id": created["video_id"],
                                        "job_id": completed.get("job_id"), "stopped_at_seconds": killed_at, "recovered_after_seconds": recover, "timeline": timeline}))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())

# Test plan

For each test save: ID, input, expected, actual, timestamp (UTC), logs/request ID/job ID, PASS/FAIL/BLOCKED. `docs/EVIDENCE.md` holds links and screenshots, never credentials.

| ID | Test | Expected |
| --- | --- | --- |
| T01 | 10 seeded <=30s <=50MB clips | Each one produces browser-playable MP4 + JPG + duration & correct profile |
| T02 | Unsupported/corrupt file | Rejected cleanly; no READY |
| T03 | File >50 MB | Rejected; cost controlled |
| T04 | Clip >30 seconds | Rejected under documented policy |
| T05 | Owner direct playback API | URL signed after authorization |
| T06 | Unauthenticated direct API | 401; no object location leaked |
| T07 | Unauthorized Viewer direct API | 403/404; cannot obtain data or bytes |
| T08 | Authorized Viewer direct API | Gets permitted URL and video |
| T09 | Same message twice | One logical output per version/profile |
| T10 | Kill transcode halfway | No partial published, retry succeeds; observed logs |
| T11 | Relay publish/DB failure simulation | Outbox eventual delivery; no lost business event |
| T12 | HTTPS/secrets/private storage/IAM | All restricted as documented |
| T13 | Terraform recreate + GitHub Actions | IaC/code deploy reproducible |
| T14 | Cloud Run revision rollback | Known earlier revision restores operation |
| T15 | API load test | Record duration, warm-up, concurrent users, request count, error rate, p95 from actual samples |
| T16 | Monitoring and failure alert | Alert condition/window/delay/action and actual evidence |

## Recommended tools

- `pytest` + Flask test client, mocks for GCP adapters; real ffmpeg subprocess integration test; `ffprobe` verifies output.
- Local Docker PostgreSQL integration test; unit tests remain runnable without cloud credentials.
- Locust or equivalent for API GET, e.g. 10 concurrent users, 10s warmup + 60s measurement; adapt to quota/budget before production.
- Manual cloud proof (CI run URL, screenshot, logs IDs). **Do not fabricate measurements.**

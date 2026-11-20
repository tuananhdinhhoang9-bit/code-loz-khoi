# Requirements — source of truth

**Primary**: `references/10_video_upload_and_processing_portal.pdf` (4 pages). This Markdown is a faithful checklist plus separate implementation assumptions, not a replacement for the PDF.

## From the brief

- Provider: **choose one** AWS / Azure / GCP; working cloud-hosted website. Suggested 3–4 students, 6–8 weeks.
- Users: video owner, authorized viewer. Private upload + job status; container-based transcoding; protected playback and thumbnail.
- Reference dataset: **10 clips**, each **<=30 seconds**, **<=50 MB**; titles, access permissions, **one** output profile; repeatable seed script and known expected results.
- Outputs: browser-playable MP4, thumbnail, duration metadata, statuses, authorized playback URLs.
- Core entities: `Video`, `TranscodeJob`, `OutputProfile`, `OutputObject`; outputs identified by **source version and profile**.
- Auth: OIDC provider or justified alternative; verify identity and permissions in API; workload identities; managed secrets; private objects; intended HTTPS entry points only; document DB/network paths.
- Durable messaging: handle redelivery; business DB effect + outbox event committed together; relay publishes afterward; idempotent consumer, stable operation key, ack after durable progress, bounded retries and dead-letter/failed-job/operator recovery.
- Failure drill: **stop transcode mid-execution**; safe incomplete output cleanup/overwrite on retry; honest progress.
- Metrics: processing duration, queue age, output bytes, estimated egress, cost/clip. Dashboard and actionable alert (condition, evaluation window, expected delay, first action), correlated request/job IDs, no sensitive logs.
- Tests: play each valid reference clip; reject unsupported/oversized/overlong; repeat event exactly one logical result; forbidden viewer cannot get video; directly test authorized/unauthorized API calls; HTTPS, secrets, storage; recreate infrastructure from code, CI/CD, rollback; load test duration/concurrency/warm-up/dataset/error rate/p95.
- Deliver: live URL and demo accounts, source & infrastructure code, seed data & tests, CI/CD, actual deployed architecture with network boundaries/failure domains, short design report, monitoring/failure evidence, workload-based monthly cost estimate, cleanup, 10–15-min demo.
- Optional: multiple quality profiles; **do not build** initially.

## Implementation assumptions (not necessarily in brief)

- **Provider: AWS** (ADR-021, 2026-11-20). Flask+Jinja+vanilla JS, PostgreSQL, FFmpeg; ALB, ECS on Fargate (API and worker containers), RDS for PostgreSQL, private S3, SQS + dead-letter queue, Cognito, Secrets Manager, Terraform. Where the lines below say GCS or "generation", read S3 and object VersionId. (Earlier assumptions, both superseded: GCP until 2026-11-17, a Windows VPS until 2026-11-20.)
- Use one H.264/AAC MP4 max-480p profile (preserve aspect ratio), JPG thumbnail. If input has no audio, output may omit audio; still browser playable.
- Only allow small demo files; reject invalid dimensions/codecs after probing, never trust extension or Content-Type alone. Upload URL has short TTL and bounded intended object path; final authoritative size/generation checked after upload.
- No financial actions: page 1 contains phrase “simulated financial actions” while the video scope has none; request instructor clarification rather than invent payment features.
- No CDN, live streaming, comments, subscriptions, recommendations, Kubernetes, or more profiles.

## Priority

1. Must meet **all** acceptance criteria, including reliability and cloud evidence.
2. Keep architecture small, cheap and easy to explain.
3. Polish UI only when core flow is correct.

# Queue, outbox, idempotency and failure drill

## Workflow invariant

```text
GCS upload complete -> validate object metadata and generation
-> transaction { Video + Job(QUEUED) + OutboxEvent }
-> relay publishes to Pub/Sub and marks event published
-> authenticated dispatcher receives event, validates stable job id
-> dispatch bounded Cloud Run Job execution
-> worker atomically CLAIMS job lease + attempt ID
-> ffprobe -> ffmpeg -> temp MP4 and JPG -> verify outputs
-> upload attempt-specific staging objects
-> in one DB transaction publish output pointers + mark READY
```

A crash can occur between **any** steps. Never assume Pub/Sub or worker is exactly-once.

## Delivery contract

- Outbox protects DB transaction vs message publish. Relay can publish twice; both messages carry same `job_id` + `source_generation` + `profile_id`.
- Dispatcher acknowledges Pub/Sub **only after** Cloud Run Job launch is confirmed or it has durably recorded a recoverable dispatch state. Failures must retry; successful launch + failed ack may duplicate execution, so worker dedupe remains necessary.
- Worker claims via PostgreSQL conditional update/row lock with a lease. Only successful claimant processes. Use bounded leases plus reconciliation when lease expires. Duplicate messages are NO-OP if READY.
- Retries capped (e.g., 3 logical tries), with explicit `RETRYING` state and next-attempt timing. Dead-letter or permanent `FAILED` after cap. Protect against Pub/Sub and Cloud Run double retry explosions; document effective bound.
- Output destination includes source GCS generation, profile and per-attempt UUID. Check MP4 and JPG are complete before publishing DB pointers. Cleanup incomplete orphan staging data later.
- Local Phase 06 uses compact outputs/<job UUID hex>/<attempt UUID hex> paths to avoid Windows MAX_PATH: the unique job already binds video/source-generation/profile, and immutable pointers retain those fields. Cloud object naming may include full GCS generation. Local files never become public just because upload finished.
- `READY` means MP4 + thumbnail exist and are validated, not merely that ffmpeg command was started.
- `progress` honest: `QUEUED`, `PROCESSING`, `RETRYING`, `READY`, `FAILED`, optionally real FFmpeg frame/time progress only if measured. Do not fake 10/30/70/100 percentages.

## Failure drill

1. Seed a sufficiently long **valid <=30-second** clip to make FFmpeg run long enough for demo; if processing too fast, add a controlled **test-only** delay before final publish. Never fake real progress.
2. Start transcode, record correlation/job/execution IDs and timestamps.
3. Cancel the actual Cloud Run Job execution while processing; collect logs/screenshots.
4. Confirm status not READY; playback denied; staging outputs ignored.
5. Reconciler finds expired lease, dispatches retry (or documented operator action) with bounded attempts.
6. New attempt succeeds; both outputs valid; **only one logical published result**; no leaked partial output; alert fires under documented rule.
7. Record actual evidence to `docs/EVIDENCE.md`. If GCP access unavailable, mark BLOCKED; local simulated kill test is useful but does not replace real cloud drill.

## Tests

- Duplicate message -> one logical result, same profile/version, no duplicate output pointers.
- Worker crash after writing MP4 but before thumbnail -> no READY; retry safe.
- Worker crash after upload outputs but before DB commit -> retry/reconcile safe.
- Relay crash after publish but before marking published -> redelivery safe.
- Unsupported/oversize/overlong -> predictable failure without corrupted status.

## Implemented local adapter (Phase 06)

FileBroker persists each stable OutboxEvent.id and payload by fsync + atomic rename. Relay locks job then event and marks published only after broker acceptance. Dispatcher claims under a PostgreSQL row lock; duplicate claims/no-op or processing outcomes are acked only after durable state exists. A failed DB transaction leaves delivery/lease for recovery; a relay crash after publish can redeliver safely. This is local process-restart durability, not a distributed broker or a power-loss guarantee for directory metadata.

Docker execution is synchronous inside the local dispatcher, one job per message. Unique attempt container runs with bounded resources/no network. PROCESSING lease 180 s exceeds container timeout 150 s; timeout cleanup targets only its UUID-named container. Final pointer publication requires matching unexpired lease + attempt ID + source generation. Both objects and READY commit together; staging/partial files are private and ignored by playback. No automatic orphan cleanup yet.

At most 3 logical attempts, retry delay 5 then 10 s; permanent media/source errors fail immediately. Relay failures and accepted-but-undispatched messages are bounded to 5 deliveries per retry campaign, then FAILED. Manual retry-job accepts only FAILED and deliberately opens a fresh bounded campaign. Malformed messages move to local dead letters. local-jobs and structured logs expose real IDs/status/error/timing/bytes, never tokens/URLs. local-process must be invoked again to reconcile; no background scheduler is claimed.

Tests use isolated real PostgreSQL schemas, fake transport only in tests, real host media and Docker. Covered duplicate/concurrent claims, relay crash after publish, partial MP4, crash after staging, DB output insert rollback, stale attempts, source tampering, bounded retry/publish/dispatch, ack failure, disk queue restart, permissions and actual kill while FFmpeg runs followed by successful retry. Cloud transport, IAM and live Cloud Run cancellation remain unverified.

## Windows VPS adapter (Phase 07) — replaces Pub/Sub, Cloud Scheduler and Cloud Run Jobs

The invariant at the top of this document is unchanged; only the transport and the runner differ.

| Concern | Mechanism | Verified by (real PostgreSQL + FFmpeg on Windows) |
| --- | --- | --- |
| Job created only with a committed transaction | Unchanged outbox: `Video` + `TranscodeJob` + `OutboxEvent` in one transaction | Phase 04/06 tests |
| Durable queue, no binary data | `queue_messages` rows written by `PgBroker.publish` | `test_pg_queue_visibility_restart_ack_and_dead_letter` |
| Two workers never take one message | `SELECT … FOR UPDATE SKIP LOCKED` in `receive` | `test_pg_queue_concurrent_receivers_never_share_a_message` |
| Worker dies before ack | Message hidden for 300 s then redelivered; job lease (180 s) expires and `reconcile` schedules the retry | `test_worker_restart_recovers_abandoned_job` |
| Lease + heartbeat | `claim_job` sets a 180 s lease and attempt UUID; `touch_lease` extends it every 3 s while FFmpeg runs and stops FFmpeg if the attempt no longer owns the job | `test_heartbeat_extends_lease_reports_progress_and_detects_loss`, `test_cancelled_job_stops_ffmpeg` |
| Bounded retry with backoff | 3 attempts, 5 s then 10 s; permanent media errors fail at once; publish/dispatch capped at 5; queue deliveries capped at 10 | Phase 06 tests + `test_pg_queue_delivery_cap_is_bounded` |
| Dead letters / failed jobs | `queue_messages.dead_at`, `transcode_jobs.status = FAILED`, operator `retry-job` | Phase 06 tests |
| Idempotency | Unique logical job key; duplicate message is a no-op once READY | `test_native_worker_real_pipeline_with_pg_queue` |
| Backlog on one worker | The worker relays one outbox event only when the queue is empty, so waiting jobs do not hit the 30 s dispatch deadline | `test_worker_loop_drains_backlog_one_at_a_time` |
| One encode at a time | Sequential loop + PostgreSQL advisory lock for a second worker process | same test (`peak == 1`), `test_single_worker_lock`, `test_worker_service_graceful_shutdown_and_single_instance` |
| Timeout and process cleanup | Windows Job Object: terminate on timeout/cancel, kill-on-close if the worker dies | `test_ffmpeg_timeout_stops_the_whole_process_tree`, `test_worker_death_does_not_leave_ffmpeg_running` |
| No partial output published | Attempt-specific output path; pointers + READY in one transaction; temporary folder removed afterwards | Phase 06 tests + native pipeline test |

Not covered by these local tests: a real failure drill on the VPS (Phase 09), behaviour under WinSW service stop while encoding, and disk-full during encoding.

## AWS mode (from 2026-11-20, Phase 07 code; not yet run on AWS)

The outbox, claim/lease, attempt fencing, bounded retries and reconcile logic above is unchanged. Only the transport and the object store differ:
- **SQS** (`app/queue_sqs.py`) replaces the PostgreSQL queue table. Delivery is at-least-once; a received message is hidden for 300 s and the worker heartbeat extends that while FFmpeg runs. A redelivered message for a job that is PROCESSING, READY or FAILED is acknowledged as a no-op. Malformed messages are copied to the dead-letter queue with a reason and removed; repeated deliveries are moved by the queue's redrive policy.
- **S3** (`app/storage_s3.py`): the worker downloads the exact input VersionId recorded in the job, so an object overwritten after `complete` cannot change the result. Outputs are written under `outputs/<job>/<attempt>/` and become visible only through the same single transaction that inserts both `OutputObject` rows.
- S3 or SQS errors are retryable: the attempt ends as RETRYING (bounded by `max_attempts`) or the worker cycle is retried after 5 s.
- Cleanup removes S3 output objects older than 24 hours that no `OutputObject` references and that do not belong to a PROCESSING job.

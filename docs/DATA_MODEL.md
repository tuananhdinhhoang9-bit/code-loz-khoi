# Database contract

Use **PostgreSQL** with SQLAlchemy and Alembic only if migrations become necessary; no extra ORM layer. Never generate uncontrolled schema drops.

## Required domain entities

- `Video`: `id` UUID, `owner_uid`, `title`, `input_object`, `source_generation`, `size_bytes`, `mime_type`, `created_at`, `status`.
- `OutputProfile`: `id`, `name`, `width_max=854`, `height_max=480`, `video_codec=h264`, `audio_codec=aac`, `created_at`. One profile only (`mp4-480p`).
- `TranscodeJob`: `id` UUID, `video_id`, `source_generation`, `profile_id`, `status`, `attempts`, `max_attempts`, `lease_until`, `current_attempt_id`, `last_error_code`, `queued_at`, `started_at`, `finished_at`, `duration_ms`. Unique (`video_id`, `source_generation`, `profile_id`).
- `OutputObject`: `id`, `transcode_job_id`, `source_generation`, `profile_id`, `kind` (`mp4`/`thumbnail`), `storage_object`, `storage_generation`, `bytes`, `duration_ms`, `created_at`. Unique (`transcode_job_id`, `kind`) for published outputs.

## Supporting entities

- `VideoPermission`: (`video_id`, `viewer_uid`) unique; Owner implicitly authorized. This table is essential for private playback.
- `OutboxEvent`: `id` UUID/stable operation key, `job_id`, `kind`, `payload_json`, `created_at`, `published_at`, `publish_attempts`, `last_error`. Insert **in same DB transaction** as logical Job creation.
- Optional `JobAttempt`: for detailed audit; skip initially if TranscodeJob + structured logs suffice.

## Integrity rules

- Public identifiers use UUID, not sequential integer IDs.
- Generation in storage and DB must match. A new source generation is a new logical job if re-upload allowed.
- Business state and outbox event are transactionally committed together.
- Claim job via atomic conditional update/DB transaction with lease timeout. Repeated event must not create two published results.
- Count attempts centrally. Failed and queued jobs remain operator visible. Never treat incomplete staging objects as published artifacts.
- Avoid storing tokens, Signed URLs, or raw passwords in database or logs.

Phase 06 reuses lease_until by state: PROCESSING = exclusive execution lease (180 s); RETRYING = next permitted retry time (5/10 s backoff); QUEUED after relay = dispatch deadline (30 s). A QUEUED NULL deadline means an unpublished event awaits relay. Only the reconciler resets due delivery; attempts are counted atomically at claim, capped at 3. duration_ms on TranscodeJob measures processing; duration_ms on OutputObject measures media duration. No schema migration was needed.

## Seed

Generate **10 short synthetic clips** reproducibly via FFmpeg testsrc/sine or save equivalent legal test clips with fixed metadata. Have at least two synthetic users Owner/Viewer configured with auth, permissions, durations and expected output checks. Inputs <=30s, <=50MB. Do not place copyrighted content or private real-user data in repo.

Phase 02 local fixtures use stable UUID5 IDs and `local-sha256:<hash>` content versions, explicitly not GCS generations. The generated manifest records expected media checks and viewer permissions. Authentication accounts are added in Phase 03; fixture UIDs alone do not authenticate users. No processed outputs or READY states are seeded. Cloud storage integration must use actual immutable GCS generations instead of fixture versions.

## Added in Phase 07 (Windows VPS)

All changes are additive; `flask init-db` creates what is missing and never drops or rewrites data.

| Table / column | Purpose |
| --- | --- |
| `transcode_jobs.progress_percent` (nullable integer) | Measured FFmpeg progress 0–99 while PROCESSING, 100 at READY, NULL when unknown. Added with `ADD COLUMN IF NOT EXISTS` |
| `queue_messages` (`id` bigserial, `operation_key` uuid, `payload_json` jsonb, `created_at`, `visible_at`, `deliveries`, `dead_at`, `dead_reason`) | Durable job queue replacing Pub/Sub. Holds only job identifiers, never media bytes. A row with `dead_at` set is a dead letter |
| `users` (`uid` = lower-case email, `password_hash`, `is_admin`, `is_active`, `failed_logins`, `locked_until`, `created_at`) | Local accounts for `AUTH_PROVIDER=local`. `videos.owner_uid` and `video_permissions.viewer_uid` hold this `uid`; there is deliberately no foreign key so Firebase UIDs and seed fixtures remain valid |
| `auth_sessions` (`token_hash` = SHA-256 hex, `uid`, `created_at`, `expires_at`) | Server-side sessions; the token itself is never stored |

`init-db` also inserts the single `mp4-480p` profile if it is missing, using the same deterministic ID as the seed so `seed-db` can still run afterwards.

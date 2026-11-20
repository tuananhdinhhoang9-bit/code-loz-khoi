---
name: video-job-reliability
description: Use when implementing, testing or reviewing video upload jobs, FFmpeg container processing, Pub/Sub events, outbox, retries, idempotency, dead-letter, or killed-job recovery in this project.
---

# Non-negotiable invariants
- Commit DB job and outbox event together; relay may publish duplicates.
- Treat Pub/Sub redelivery as normal. Stable logical key: (`video_id`, `source_generation`, `profile_id`).
- Atomically claim a lease and attempt ID before transcoding. Never assume an ack means processing finished.
- Use attempt-specific staging object paths. Output not visible until MP4+thumbnail verified and DB READY atomically committed.
- Check job status after crashes and reconcile stale leases; cap total logical attempts, document interaction with queue/job native retries.
- Source GCS generation is immutable identity, not filename. Never overwrite published output with partial files.

# Required tests
1. Duplicate delivery; 2. worker crash halfway; 3. successful MP4 but missing thumbnail; 4. relay crash after publish; 5. failed final attempt; 6. forbidden playback even if files physically exist.

See `docs/PIPELINE_RELIABILITY.md`. Do not implement a fake progress percentage.

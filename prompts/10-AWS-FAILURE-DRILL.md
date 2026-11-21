# Phase 10 — Failure drill on AWS

> **ARCHIVED (2026-11-21): AWS prompt, never executed, not to be run.** The deployment target is now Azure; follow `docs/PHASES.md` and the `prompts/*-AZURE-*.md` files instead.

Implement **only phase 10**. Read `docs/PIPELINE_RELIABILITY.md`, `docs/EVIDENCE.md`; use `$video-job-reliability`. With owner approval, upload a clip, then stop the worker task mid-transcode (`aws ecs stop-task`). Show with real IDs and timestamps: no partial output published, lease expiry and reconcile, bounded retry, exactly one logical READY result, honest progress shown to the user, and the message path (redelivery or dead-letter). Repeat a delivered event to prove one logical result. Mark BLOCKED if it cannot be run; never describe an unrun drill as done.

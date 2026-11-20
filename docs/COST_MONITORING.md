# Cost and monitoring

> **ARCHIVED (2026-11-17): Google Cloud is no longer the deployment target.** Nothing in this document was ever applied to GCP. The project now runs natively on a Windows Server VPS; see `docs/WINDOWS_VPS_ARCHITECTURE.md`. Kept unchanged below for reference only.

## Workload-based monthly estimate (NOT current provider prices)

Assume for demo: 10 clips <=50MB & <=30s, one 480p output, 3 plays per clip, arbitrary sample output size 10MB/video and thumbnail 0.1MB. Track **measured** bytes and timings; estimates use current GCP Calculator and region SKU at report date. These are illustrative workload assumptions, not bill measurements.

Cost categories: Cloud Run Service request/CPU/RAM time; Cloud Run Job CPU/RAM time; Cloud SQL instance-hours/allocated storage/backups; GCS GB-month and operations; Pub/Sub/Scheduler; artifact storage; Logging/Monitoring; **network egress** to browsers and potentially GCP services. Explain pricing/free-tier assumptions explicitly; a budget alert is **not** a hard spending cap.

## Required metrics

- `processing_duration_seconds` from actual start-to-finish timestamps
- `queue_age_seconds` = first worker claim minus queued_at
- `output_bytes` from published GCS objects
- `egress_estimate_bytes` = estimated streamed/downloaded data, clearly estimated
- `cost_per_clip_estimate` = allocation with declared resource usage and rate assumptions
- failure/retry count, job age, API HTTP failures, job correlation ID

## Actionable alert

Example: failed Cloud Run Job executions >0 over 5-min evaluation window, message includes job ID/log query and first action: inspect execution logs, determine if retry scheduled/lease expired and confirm no published partial output. Set realistic expected notification delay from sampling/evaluation; observe actual during drill.

Keep dashboard in GCP Cloud Monitoring. Portal admin monitor page can show job data for demo but **does not replace actual GCP monitoring**.

## Spend control

- No cloud apply until user approves budget.
- Low demo quotas, min instances 0 for Cloud Run API, bounded Job concurrency, short test periods.
- Cloud SQL is often an ongoing charge even if API scales to zero. Stop/delete when appropriate and approved.
- No made-up USD totals: use dated calculator estimates, separate actual invoice if available.

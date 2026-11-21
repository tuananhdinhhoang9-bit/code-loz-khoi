# Cloud setup + deployment gates

> **ARCHIVED (2026-11-17): Google Cloud is no longer the deployment target.** Nothing in this document was ever applied to GCP. The project now runs natively on a Windows Server VPS; see `docs/WINDOWS_VPS_ARCHITECTURE.md`. Kept unchanged below for reference only.

## Preflight (stop before billing)

- Confirm owner has GCP project ID, linked Billing Account, IAM permissions, chosen region, and acceptable **explicit** spending cap/usage policy.
- Check enabled API availability, Cloud SQL tier/quota, Cloud Run Jobs execution limits, Artifact Registry, GCS signed URL signing rights, private networking and service account impersonation.
- Region preference `asia-southeast1`, but verify tier/prices/quota first. No invented estimates or guarantees.

## Terraform minimal infrastructure

- Project APIs; single VPC/subnet and Direct VPC egress for private Cloud SQL path where supported; Private Services Access where required.
- 1 Cloud SQL PostgreSQL instance, DB + user with credentials in Secret Manager; backups/retention consistent with demo budget.
- Private GCS bucket with public access prevention and lifecycle for temporary objects.
- Pub/Sub topic/subscription/DLQ, Cloud Scheduler for relay/reconcile, Cloud Run API/dispatcher/relay, Cloud Run Job worker, Artifact Registry, IAM least privilege, Monitoring alert.
- Max instances / jobs / CPU / memory / timeouts / retries explicitly bounded. Avoid ALB, Cloud NAT, Cloud CDN unless required by tested routing.
- Cloud SQL may require additional networking and charges; plan and explain before apply.

## Gates

1. `terraform fmt -check`; `terraform init`; `terraform validate`; `terraform plan`. Show expected creations and cost risks. **No apply without user approval.**
2. Apply only after approval, verify real resource IDs/paths and update `docs/DECISIONS.md` + deployed architecture diagram.
3. GitHub Actions: automated tests -> images -> Artifact Registry -> Cloud Run deploy with Workload Identity Federation. Do not store service account JSON keys.
4. Prove prior revision rollback using actual revision IDs; do not confuse Cloud Run Service revision rollback with rolling back Cloud Run Jobs image.
5. `docs/EVIDENCE.md`: URL, timestamps, test accounts **without passwords**, screenshots/log links/IDs. Never commit secrets.
6. Cleanup with Terraform destroy only on explicit approval and verify leftovers: Cloud SQL, storage, LB (if any), Artifact Registry images, Cloud Run Jobs, topic/subscriptions, backups, logging and retained data. Note cleanup **can delete data**.

## Phase 07 — Terraform in `infra/` (written, NOT yet validated or planned)

Nothing below exists in GCP. `terraform fmt/validate/plan` have not run; see `docs/PROGRESS.md` for the blocker and exact commands.

### What the configuration would create

| File | Resources |
| --- | --- |
| `main.tf` | 11 project APIs; VPC `video-portal-vpc` + subnet `10.10.0.0/24`; Private Services Access range (/20) and peering; Cloud SQL `video-portal-db` (PostgreSQL 16, zonal, private IP only, 10 GB fixed disk, 3 retained backups, no PITR); database + user `video_portal`; random DB password stored in Secret Manager `video-portal-db-password`; private bucket `<project_id>-video-portal`; Artifact Registry `video-portal` |
| `run.tf` | Cloud Run services `video-api` (public ingress, max 2 instances), `video-relay` and `video-dispatcher` (internal ingress, max 1 instance each), all min 0, 1 CPU / 512 Mi, 60 s timeout; Cloud Run Job `video-worker` (1 task, parallelism 1, 1 CPU / 1 Gi, 300 s timeout, `max_retries = 0`) |
| `messaging.tf` | Topic `video-jobs`, OIDC push subscription to the dispatcher (5 delivery attempts, 10–300 s backoff), dead-letter topic + 7-day pull subscription; two Cloud Scheduler jobs (relay, reconcile), **paused by default** |
| `iam.tf` | Six service accounts and the bindings in the table below; no JSON keys |

### IAM (least privilege, resource-level only — no project-level roles)

| Identity | Granted | Why |
| --- | --- | --- |
| `video-api` | Secret accessor on the DB secret; `objectViewer` on the bucket; `objectCreator` only under `input/`; `serviceAccountTokenCreator` on itself | DB login, check uploaded object metadata, signed upload URLs, keyless URL signing |
| `video-relay` | Secret accessor; `pubsub.publisher` on `video-jobs` | Read outbox, publish events |
| `video-dispatcher` | Secret accessor; `run.jobsExecutorWithOverrides` on `video-worker` only | Claim state, launch one worker execution per job |
| `video-worker` | Secret accessor; `objectViewer` on the bucket; `objectCreator` only under `staging/` and `published/` | Read source, write outputs; cannot overwrite or delete objects |
| `video-pubsub-push` | `run.invoker` on `video-dispatcher` | Authenticated push |
| `video-scheduler` | `run.invoker` on `video-relay` and `video-dispatcher` | Authenticated ticks |
| Pub/Sub service agent | Publisher on the dead-letter topic, subscriber on the push subscription, token creator on `video-pubsub-push` | Required for dead-lettering and OIDC push |
| `allUsers` | `run.invoker` on `video-api` only | Public HTTPS entry; the app verifies Firebase ID tokens itself. This is a public grant and is part of what an apply approval must cover |

### Networking assumptions (unverified until a real plan/apply)

- Cloud SQL has **no public IP**. Cloud Run reaches it through Direct VPC egress (`PRIVATE_RANGES_ONLY`) into the subnet and the Private Services Access peering. Only private-range traffic enters the VPC, so Google APIs (Storage, Pub/Sub, Secret Manager, Firebase certificate fetch) use the normal Cloud Run path and no Cloud NAT, load balancer or VPC connector is created.
- No firewall rules are defined: the path relies on the default implied egress-allow rule. An organisation policy or custom deny rule would break it.
- Direct VPC egress for both services and jobs in `asia-southeast1`, and permission to create the service-networking peering, are assumed and must be confirmed against the real project.
- Because the database is private-only, `init-db`/`seed-db` cannot run from a laptop. Phase 08 must run them from inside GCP (for example a one-off `video-worker`-style job execution using the app image).
- Relay and dispatcher use internal ingress. Pub/Sub push and Cloud Scheduler from the same project are expected to be accepted as internal traffic; verify with a real authenticated call in Phase 08.
- Direct browser upload/playback needs bucket CORS for the API origin, which is only known after the first deploy: set `cors_origins` and re-plan.

### Contracts this configuration expects Phase 08 to implement

- Env names: `APP_ENV=gcp`, `GOOGLE_CLOUD_PROJECT`, `GCP_REGION`, `POSTGRES_*`, `FIREBASE_*`, `GCS_BUCKET`, `PUBSUB_TOPIC`, `WORKER_JOB_NAME`. The current app refuses to start on Cloud Run (`K_SERVICE`) until real adapters exist, so the default images are Google's sample containers.
- Internal routes: `POST /internal/relay`, `POST /internal/dispatch` (Pub/Sub push), `POST /internal/reconcile`. They do not exist yet; the schedulers stay paused until they do.
- Bucket prefixes `input/`, `staging/`, `published/`. The lifecycle rule deletes `staging/` objects after 1 day, so published outputs **must** live under `published/` (the local Phase 06 layout publishes by DB pointer to the attempt path — that must not be mapped onto `staging/`).
- The DB lease must be longer than the 300 s job timeout (local values are 180 s / 150 s).
- Cloud Run has no per-job cap on concurrent executions here; the dispatcher must bound how many worker executions it launches.

### Cost risks (no prices asserted — use the official calculator for the chosen region/date)

- **Cloud SQL runs and bills continuously** once created (instance hours, 10 GB disk, backups), even when Cloud Run is scaled to zero. `db-f1-micro` is an assumed tier, not a verified price or quota; it is shared-core and has a low connection limit, so SQLAlchemy pool size × instances must stay small.
- Cloud Run services scale to zero, but enabled schedulers wake relay and dispatcher on every tick (default every 2 minutes).
- Storage, Artifact Registry images (no cleanup policy yet), Secret Manager versions, Pub/Sub, Scheduler jobs, logs and browser egress all accrue with use. Published outputs and inputs are never auto-deleted.
- A budget alert is not created by this Terraform and is not a hard cap. Create one manually in Billing before any apply.
- `deletion_protection = true` by default: `terraform destroy` will fail on Cloud SQL and Cloud Run until it is deliberately set to `false`. A deleted Cloud SQL instance name cannot be reused immediately.
- Terraform state is local and contains the generated DB password. Keep it off Git and off shared drives; a remote state backend is undecided (needed before CI applies in Phase 11).

Calculator: https://cloud.google.com/products/calculator

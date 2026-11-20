# Architecture — target GCP

> **ARCHIVED (2026-11-17): Google Cloud is no longer the deployment target.** Nothing in this document was ever applied to GCP. The project now runs natively on a Windows Server VPS; see `docs/WINDOWS_VPS_ARCHITECTURE.md`. Kept unchanged below for reference only.

## Logical flow

```text
Browser -> HTTPS Cloud Run (Flask API) -> Cloud SQL (metadata/permissions/outbox)
   |                    |
   | signed URL         | Scheduler -> private outbox relay -> Pub/Sub
   v                    |                                  |
Private Cloud Storage <-+                              private dispatcher
 (source + outputs)                                         |
                                                       Cloud Run Job
                                                       (Docker + FFmpeg)
                                                           |
                                            outputs -> private Storage
                                            status/lease -> Cloud SQL

Viewer -> Flask API (OIDC token + VideoPermission) -> short-lived playback URL -> private GCS
```

## Trust boundaries

1. **Public boundary:** only website/API HTTPS, authorization on every sensitive endpoint. The browser uploads/downloads by short-lived scoped Signed URLs, never by public bucket.
2. **Internal Cloud Run boundary:** Dispatcher/relay restricted IAM invocation; event delivery is authenticated. Workload identities (different service accounts) with minimal permissions.
3. **Data boundary:** PostgreSQL privately reachable only through supported Cloud Run-to-Cloud SQL paths. Prefer private-IP via Direct VPC egress/Private Services Access if budget/permissions allow; actual method must be documented with region, subnet and firewall paths. Never expose DB credentials in browser.
4. **Object boundary:** private bucket, uniform bucket-level access, prohibit public access, separate prefixes for input/staging/published outputs. A signed URL alone does not prove viewer authorization — API authorizes first.
5. **Failure boundary:** Pub/Sub can redeliver, dispatcher can duplicate job launch, worker can crash; DB lease + unique keys and atomic READY transition prevent duplicate logical results.

## Suggested resources

- Cloud Run `video-api` (Flask UI/API), min instances 0.
- Cloud Run `video-dispatcher` (internal, authenticated Pub/Sub push).
- Cloud Run `video-relay` or authenticated private handler for outbox publication, called by Cloud Scheduler periodically; prefer reuse of a bounded service when simpler.
- Cloud Run Job `video-worker` with FFmpeg. One video per execution, max parallel executions bounded.
- Cloud SQL PostgreSQL one instance in the selected region, planned as zonal (single zone for class demo, not regional high availability); tier/cost and private database/network path must be verified in Phase 07.
- Cloud Storage single private bucket, input/staging/published prefixes; lifecycle policies for orphaned outputs.
- Pub/Sub topic + subscription + dead-letter topic; retries configured with limits and visibility.
- Identity Platform/Firebase Authentication; Secret Manager; Cloud Logging/Monitoring; Artifact Registry.
- Terraform source in `infra/`; GitHub Actions deployment with short-lived federated auth.

## Data/operational correctness

- `source_generation` is the immutable GCS object generation, not just the original filename.
- A job logical key is (`video_id`, `source_generation`, `profile_id`); multiple attempts share the same logical result.
- No output published until all objects verify and the DB marks READY atomically.
- Long processing must not run in the web request; Cloud Run Job must respect timeout, CPU/memory, disk and concurrency bounds.
- The deployed architecture diagram must name actual GCP resources, trust boundaries, request paths, region/zone and single-zone failure domain. PDF page 2 is only a reference diagram, not final evidence.

## Pending decisions to validate during Phase 07

- Account permission to create private Cloud SQL and service networking; Cloud Run Direct VPC egress availability in selected region.
- Whether `asia-southeast1` and the chosen Cloud SQL tier are available and within student budget.
- Configured quotas and authorized GitHub repository.
Document departures in `docs/DECISIONS.md` and approval if security/cost changes.

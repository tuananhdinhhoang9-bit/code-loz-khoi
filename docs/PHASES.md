# Phases — implement in order

Read `AGENTS.md` + only the referenced docs. Do not build future phases early. Each phase ends with test commands, result (PASS/FAIL/BLOCKED), updated PROGRESS and a focused Git commit.

**Deployment target changed on 2026-11-21:** phases 07–13 now target **Azure** (ADR-024, `docs/AZURE_ARCHITECTURE.md`). The AWS phases (2026-11-20), the Windows VPS phases (2026-11-17) and the GCP phases are archived at the bottom of this file. Phases 00–06 are unchanged. **Azure phase 07 is done (code and local tests only, see `docs/PROGRESS.md`). Phase 08 is done: account checked read-only, `infra/azure/` validated and planned (32 resources for the foundation step, 35 in full), nothing applied. Phases 09–13 have not been started; phase 09 needs the owner's approval for every paid step.**

| Phase | Work | Acceptance |
| --- | --- | --- |
| 00 | Verify source requirements, environment/repo; concise plan | Docs consistent; blockers identified; no paid cloud actions |
| 01 | Local Flask skeleton, Jinja, Docker Compose PostgreSQL, `.env` gitignore, health | Local home, health and DB connection; tests pass |
| 02 | DB schema and seed / test fixtures | Four domain tables + support tables, unique keys, repeatable seed tests |
| 03 | Auth and permissions local | Owner/Viewer, server-side verification, unauthorized API tests |
| 04 | Private upload + listing + signed playback contracts | Mock/local storage adapter, validation, permission tests |
| 05 | FFmpeg container worker and metadata | One real <=30s clip -> valid MP4+JPG+duration; bad input tests |
| 06 | Local outbox, dispatcher abstraction, idempotency, retry | Duplicate/crash tests pass using fake transport |
| 07 | **Azure adapters, local only**: Blob Storage adapter (user delegation SAS, version ID as generation), Service Bus broker, Entra External ID settings for the existing OIDC verifier, authorization code + PKCE sign-in and `PUT` upload in the page, run-once worker mode and a one-cycle maintenance command, API relay after commit, Linux images for `api` and `worker`; remove the AWS adapters, their tests and `boto3` | Existing tests still pass in local mode; new adapters tested with stubs/fakes; **no Azure resource created, no Azure call made** |
| 08 | **Azure preflight + Terraform plan**: confirm subscription type, region, quotas, permission to create an external tenant, and every item under "Chưa đối chiếu được" in `docs/AZURE_ARCHITECTURE.md`; write `infra/azure/`; `terraform validate` and `plan` only | Open points decided and recorded; plan output reviewed; nothing applied |
| 09 | **Azure deploy + integrate** (owner approves every paid action): apply, push images, `init-db`, demo accounts, seed and process the 10 reference clips | Live HTTPS URL; 10 clips play in the browser and match the profile; direct authorized/forbidden API calls; private container and DB path verified |
| 10 | Failure drill on Azure | Stop the transcode job execution mid-conversion; no partial output published; bounded retry; exactly one logical READY result; real execution/job IDs and timestamps recorded |
| 11 | Monitoring, alert and cost | Azure Monitor dashboard (processing duration, queue age, output bytes, egress estimate, cost per clip); one alert tied to the failure drill with condition, window, observed delay and first action; workload-based monthly estimate from real prices and measured durations |
| 12 | CI/CD + rollback | GitHub Actions: tests on push, build, deploy; rollback to a previous revision/image demonstrated with real revision and commit IDs |
| 13 | Final verification/docs/demo/cleanup | Tests 1–3 of the brief, load test with p95, actual deployed architecture diagram, design report, demo script, cleanup instructions and a check for remaining billable resources |

If the user needs to stop after a phase, keep unfinished acceptance **BLOCKED**, not silently declared complete.

## Open requirement risks

- The brief suggests "App Service API"; the design puts the API on Container Apps (ADR-024). Confirm with the instructor or move the same image to App Service.
- If the subscription cannot create a Microsoft Entra external tenant, the fallback is local accounts, which is not an OIDC provider; that deviation must be written down and agreed, not hidden.
- A SAS cannot limit upload size, so an oversized upload is rejected only at `complete`, after it reached storage.

## Archived AWS phases (code and plan only)

Target from 2026-11-20 to 2026-11-21 (ADR-021 to ADR-023), dropped by the owner. Phase 07 (S3, SQS and Cognito adapters, tested with stubs) and phase 08 (`infra/aws/`, validated and planned: 56 resources to add) were completed; one resource, an ACM certificate, was applied. Phases 09–13 were never started. `docs/AWS_ARCHITECTURE.md`, `infra/aws/` and `prompts/*-AWS-*.md` are reference material; the AWS adapters and `deploy/aws/` were removed from `main` in Azure phase 07, and the frozen `aws` branch holds the last complete AWS edition.

## Archived Windows VPS phases (executed up to service installation)

Target from 2026-11-17 to 2026-11-20 (ADR-015). Phase 07 (preparation) was completed; phase 08 reached "three services installed and running on the VPS, smoke test 22/22 on the VPS itself" (see `docs/PROGRESS.md`). VPS phases 09–12 (failure drill, monitoring, CI/CD, final) were never started. The VPS keeps running unchanged until the cloud deployment passes phase 09. `prompts/07-VPS-WINDOWS-INFRA.md`, `prompts/08-VPS-DEPLOY.md`, `docs/WINDOWS_VPS_*.md` and `scripts/windows/` are reference material.

## Archived GCP phases (not executed beyond planning)

Old phase 07 (Terraform plan) was completed as plan-only on 2026-11-17 (`infra/`, 57 resources planned, nothing applied). Old phases 08–12 (GCP integration, cloud failure drill, Cloud Monitoring, Workload Identity CI/CD, cloud acceptance) were never started. Their prompt files in `prompts/` carry an ARCHIVED banner.

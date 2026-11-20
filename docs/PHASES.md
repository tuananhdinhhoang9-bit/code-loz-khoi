# Phases — implement in order

Read `AGENTS.md` + only the referenced docs. Do not build future phases early. Each phase ends with test commands, result (PASS/FAIL/BLOCKED), updated PROGRESS and a focused Git commit.

**Deployment target changed on 2026-11-20:** phases 07–13 now target **AWS** (ADR-021, `docs/AWS_ARCHITECTURE.md`). The Windows VPS phases (2026-11-17) and the GCP phases are archived at the bottom of this file. Phases 00–06 are unchanged.

| Phase | Work | Acceptance |
| --- | --- | --- |
| 00 | Verify source requirements, environment/repo; concise plan | Docs consistent; blockers identified; no paid cloud actions |
| 01 | Local Flask skeleton, Jinja, Docker Compose PostgreSQL, `.env` gitignore, health | Local home, health and DB connection; tests pass |
| 02 | DB schema and seed / test fixtures | Four domain tables + support tables, unique keys, repeatable seed tests |
| 03 | Auth and permissions local | Owner/Viewer, server-side verification, unauthorized API tests |
| 04 | Private upload + listing + signed playback contracts | Mock/local storage adapter, validation, permission tests |
| 05 | FFmpeg container worker and metadata | One real <=30s clip -> valid MP4+JPG+duration; bad input tests |
| 06 | Local outbox, dispatcher abstraction, idempotency, retry | Duplicate/crash tests pass using fake transport |
| 07 | **AWS adapters, local only**: S3 storage adapter, SQS broker, generic OIDC (Cognito) token verifier, backend selection by configuration, sign-in and upload changes in the page, Linux container images for `api` and `worker` | Existing tests still pass in local mode; new adapters tested with stubs/fakes; **no AWS resource created, no AWS call made** |
| 08 | **AWS preflight + Terraform plan**: confirm account type, region, quotas and permissions; write `infra/aws/`; `terraform validate` and `plan` only | Open points in `docs/AWS_ARCHITECTURE.md` decided and recorded; plan output reviewed; nothing applied |
| 09 | **AWS deploy + integrate** (owner approves every paid action): apply, push images, `init-db`, demo accounts, seed and process the 10 reference clips | Live HTTPS URL; 10 clips play in the browser and match the profile; direct authorized/forbidden API calls; private bucket and DB path verified |
| 10 | Failure drill on AWS | Stop the worker task mid-transcode; no partial output published; bounded retry; exactly one logical READY result; real task/job IDs and timestamps recorded |
| 11 | Monitoring, alert and cost | CloudWatch dashboard (processing duration, queue age, output bytes, egress estimate, cost per clip); one alarm tied to the failure drill with condition, window, observed delay and first action; workload-based monthly estimate from real prices |
| 12 | CI/CD + rollback | GitHub Actions: tests on push, build, deploy; rollback to a previous task definition demonstrated with real revision/commit IDs |
| 13 | Final verification/docs/demo/cleanup | Tests 1–3 of the brief, load test with p95, actual deployed architecture diagram, design report, demo script, cleanup instructions and a check for remaining billable resources |

If the user needs to stop after a phase, keep unfinished acceptance **BLOCKED**, not silently declared complete.

## Open requirement risks

- The always-on Fargate worker is one bounded container processing one job at a time, not one task launched per conversion (brief: "Use bounded Fargate tasks for conversion"). Confirm with the instructor or switch to `RunTask` per job.
- If the AWS account is an AWS Academy Learner Lab, separate workload identities, Cognito and GitHub OIDC may be unavailable; each resulting deviation must be written down, not hidden.

## Archived Windows VPS phases (executed up to service installation)

Target from 2026-11-17 to 2026-11-20 (ADR-015). Phase 07 (preparation) was completed; phase 08 reached "three services installed and running on the VPS, smoke test 22/22 on the VPS itself" (see `docs/PROGRESS.md`). VPS phases 09–12 (failure drill, monitoring, CI/CD, final) were never started. The VPS keeps running unchanged until the AWS deployment passes phase 09. `prompts/07-VPS-WINDOWS-INFRA.md`, `prompts/08-VPS-DEPLOY.md`, `docs/WINDOWS_VPS_*.md` and `scripts/windows/` are reference material.

## Archived GCP phases (not executed beyond planning)

Old phase 07 (Terraform plan) was completed as plan-only on 2026-11-17 (`infra/`, 57 resources planned, nothing applied). Old phases 08–12 (GCP integration, cloud failure drill, Cloud Monitoring, Workload Identity CI/CD, cloud acceptance) were never started. Their prompt files in `prompts/` carry an ARCHIVED banner.

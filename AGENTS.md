# Project instructions for coding agents

Project: Cloud Computing Final Project 10 — **Video Upload and Processing Portal**. Read `docs/REQUIREMENTS.md` first; the original PDF is in `references/` and takes precedence over our chosen implementation details.

## Branch `aws` (read first)

**FROZEN (2026-11-21): the owner dropped AWS; the cloud target is Azure (ADR-024 on `main`). Do not develop on this branch and do not run Terraform or AWS commands from it unless the owner asks.**

This branch is the **AWS edition**, cut from `main`. The Windows VPS tooling (`scripts/windows/`, `deploy/windows/`, `docs/WINDOWS_VPS_*.md`, the two VPS prompts) is not on this branch; it lives on `main` and `vps`. The VPS services described below still exist on the owner's server and the rule not to touch them still applies. Change application code on `main` and merge it into this branch; do not let `app/`, `worker/` or `tests/` diverge.

## Deployment target (changed 2026-11-20)

Production target is **AWS** (owner decision, ADR-021): ALB, ECS Fargate (`api` and `worker` containers), RDS for PostgreSQL, private S3, SQS + dead-letter queue, Cognito, Secrets Manager, Terraform in `infra/aws/`, GitHub Actions. Read `docs/AWS_ARCHITECTURE.md` and `docs/PHASES.md`. **Do not use Google Cloud**, Redis or Kubernetes. Where the rules below mention GCP, apply the AWS equivalent: IAM task roles instead of long-lived access keys, secrets in Secrets Manager, `terraform plan` freely but ask before `apply`/`destroy`, before anything that generates a bill, and before privileged IAM changes. Never write AWS access keys, account IDs with credentials, or presigned URLs into the repository or logs.

The previous target, a self-managed **Windows Server VPS**, is still running (`C:\VideoPortal`, services `VideoPortal-API/Worker/Caddy`). Its documents (`docs/WINDOWS_VPS_*.md`), `scripts/windows/` and VPS prompts are ARCHIVED reference material, as are the GCP documents, the top-level `infra/*.tf` files and GCP prompts. Do not change, stop or redeploy the VPS services, its firewall, RDP/Defender or its data unless the owner asks. The local mode (private folder, PostgreSQL queue, local accounts) must keep working for development and tests. Scripts that change a system must default to plan-only and act only with `-Apply`.

## Always

1. Work on **one file in `prompts/` / one phase** per request. Read only its linked docs and related code. No out-of-scope features. Follow `docs/PHASES.md` acceptance checks.
2. Code for a student team: **simple, human-readable, minimal dependencies**, small functions, descriptive short names, ordinary control flow. Avoid unnecessary interfaces, abstract classes, microservices, React, Celery, Redis and Kubernetes. Never sacrifice correctness/security for shorter code.
3. Code + tests should run locally before cloud integration. Use type hints where helpful, not everywhere. Explain non-obvious logic in brief Vietnamese; code comments only when genuinely useful.
4. Respect the fixed design in `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/API_CONTRACT.md`, `docs/SECURITY.md`, `docs/PIPELINE_RELIABILITY.md`. If a change is necessary, write its trade-off in `docs/DECISIONS.md` and keep docs/code consistent.
5. Preserve the required features: private upload, authorization, H.264 MP4 + thumbnail + duration, containerized transcode, durable messaging/outbox, idempotency, bounded retries/dead-letter, actual failure drill, monitoring/alert, IaC, CI/CD rollback, cost and test evidence.
6. **No fabricated success.** Test what can be tested. Mark unrun/cloud-blocked work as BLOCKED with cause and exact next command in `docs/PROGRESS.md`. Never invent Cloud URLs, bills, quotas, p95, alert firings or screenshots.
7. **Secrets:** runtime uses a real, gitignored `.env` locally (not `.env.example`); do not commit, paste or log secrets/tokens/signed URLs/contents. In GCP use workload identity and Secret Manager; no permanent service-account JSON key.
8. **Cloud safety:** `terraform plan` is OK with valid access; ask the user before applying paid infra, deleting resources/data, granting privileged IAM, stopping production jobs or generating bills. Keep resources bounded and budget-conscious.
9. **Git:** after every completed task or independently completed code/file/fix step, run appropriate checks, update `docs/PROGRESS.md`, commit the scoped changes and immediately push to the configured upstream. Do not wait for the entire phase/project. Inspect the diff and staged files before committing; never stage `.env`, secrets, tokens, credentials, or unrelated user changes. Verify the remote branch SHA after pushing. Never force-push or overwrite others' work. If push fails, inspect the cause and remote state, recover without losing work, and report any required user action with the exact next command. For documentation-only changes, use whitespace/content checks; do not claim application tests ran.
10. End each phase with: completed files, commands and test results, blockers, next phase. Update `docs/PROGRESS.md` and `docs/DECISIONS.md` (only when design changes).

## Project docs and skill policy

- Reusable workflows live in `.agents/skills/`; do not duplicate them in every prompt. Load a skill only if the current phase matches it.
- For GCP, check installed official Google skills before producing CLI/Terraform instructions. Use official docs if anything might have changed.
- For security review use `security-best-practices` when installed. For UI use `frontend-design` when installed.
- Local project skills: `student-simple-code`, `video-job-reliability`, `cloud-budget-guard`.
- No unverified changes to provider pricing or service features; keep assumptions labeled.

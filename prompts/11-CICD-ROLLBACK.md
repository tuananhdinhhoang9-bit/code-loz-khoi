# Phase 11 — CI/CD + rollback

> **ARCHIVED (2026-11-17): GCP prompt, not to be executed.** The deployment target is now a Windows Server VPS; follow `docs/PHASES.md` and the `prompts/*-VPS-*.md` files instead.
Implement **only phase 11**. Read `docs/CLOUD_DEPLOY.md` and `docs/TEST_PLAN.md`. Add GitHub Actions: pytest -> Docker build -> Artifact Registry -> deploy Cloud Run via Workload Identity Federation. Test secrets hygiene. Demonstrate real Cloud Run Service revision rollback and worker image rollback procedure; require approval for cloud changes. Record evidence, test results and update PROGRESS. Push to existing GitHub upstream if configured.

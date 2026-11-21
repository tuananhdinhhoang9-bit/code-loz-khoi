# Phase 12 — CI/CD and rollback on AWS

> **ARCHIVED (2026-11-21): AWS prompt, never executed, not to be run.** The deployment target is now Azure; follow `docs/PHASES.md` and the `prompts/*-AZURE-*.md` files instead.

Implement **only phase 12**. Needs a GitHub repository. GitHub Actions: run tests on every push; on the main branch build both images, push to ECR tagged with the commit SHA, register new task definitions and update the ECS services, wait for stability. Authenticate with GitHub OIDC and a narrowly scoped role; if the account forbids that, document the short-lived-credential alternative and never store permanent keys. Demonstrate a rollback to the previous task definition and record real commit and revision IDs. Database changes stay additive so a code rollback is safe.

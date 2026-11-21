# Phase 08 — AWS preflight and Terraform plan

> **ARCHIVED (2026-11-21): AWS prompt, already executed, not to be run again.** The deployment target is now Azure; follow `docs/PHASES.md` and the `prompts/*-AZURE-*.md` files instead.

Implement **only phase 08**. Read `docs/AWS_ARCHITECTURE.md` (open points table), `docs/SECURITY.md`; use `$cloud-budget-guard`. First settle with the owner: account type (run the read-only check commands), region, domain or CloudFront front, where images are built, budget. Write `infra/aws/` (VPC, security groups, ALB, ECS cluster/services/task definitions, RDS, S3 with Block Public Access + versioning + CORS, SQS + DLQ, Cognito, Secrets Manager, ECR, IAM task roles or `LabRole`, CloudWatch log groups). Run `terraform fmt`, `validate` and `plan` only; never `apply`. Record resource count, assumptions and every deviation forced by the account in `docs/PROGRESS.md` and `docs/DECISIONS.md`.

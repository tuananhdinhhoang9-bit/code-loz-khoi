---
name: cloud-budget-guard
description: Use before Terraform/GCP deployment, service creation, load tests, cloud monitoring, destructive cleanup, or cost-impacting configuration changes for this student project.
---

# Checklist
1. Identify target project, region, tier, runtime hours, quotas, and expected chargeable resources.
2. Prefer local-first development, `terraform fmt/validate/plan` before `apply`, and low fixed Cloud Run instance/job limits.
3. Ask user for explicit approval **before** any potentially chargeable provision, permission escalation, deletion, cloud failure drill or `terraform destroy`.
4. No unverified statements about cloud free tier or prices. Provide itemized illustrative cost formula and official calculator link.
5. Never hide ongoing Cloud SQL, storage, backup or log retention costs; budget alerts are not caps.
6. After permitted deployment, capture real resource names; after cleanup, verify residual billable services and state.

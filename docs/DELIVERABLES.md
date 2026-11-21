# Final deliverables / grade checklist

Source: PDF pages 3–4.

- [x] Deployed HTTPS application URL (Azure default hostname, `docs/EVIDENCE.md`; the custom domain is not switched)
- [ ] Demo Owner and Viewer accounts; credentials handed privately to instructor (never committed)
- [x] Source code and Docker images/build instructions (`deploy/azure/Dockerfile`, built by the `ci` workflow)
- [x] Terraform + reproducible infrastructure steps (`infra/azure/`, README)
- [ ] 10 reference clips with titles/permissions/profile + deterministic seed script + expected results
- [x] Automated tests, invalid/oversize/overlong, actual forbidden API calls, idempotency (`tests/`, and `scripts/acceptance_test.py` run on Azure)
- [x] GitHub Actions CI/CD, proof of deploy and rollback (runs and revisions in `docs/EVIDENCE.md`)
- [ ] **Actual deployed** architecture diagram including GCP names, region, trust boundaries, network paths, failure domains
- [ ] Short design report explaining decisions, limitations and recoveries
- [ ] Monitoring dashboard and actionable alert, actual Cloud Run Job cancel/restore evidence
- [x] Real recorded load-test conditions, p95, error rate and timestamps (Azure run of 2026-11-21 in `docs/EVIDENCE.md`)
- [ ] Dated monthly cost estimate by workload/region/tier/backup/egress and distinction from actual bills
- [ ] Cleanup and verification steps
- [ ] 10–15 minute demo script: normal flow, protected playback, correctness, failure+recovery, monitoring, CI/CD

Grade weights from brief: architecture 25%, deployment+automation 20%, security+correctness 15%, reliability+observability 15%, app completeness 15%, cost+communication 10%.

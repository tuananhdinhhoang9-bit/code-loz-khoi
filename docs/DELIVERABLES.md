# Final deliverables / grade checklist

Source: PDF pages 3–4.

- [ ] Deployed HTTPS application URL
- [ ] Demo Owner and Viewer accounts; credentials handed privately to instructor (never committed)
- [ ] Source code and Docker images/build instructions
- [ ] Terraform + reproducible infrastructure steps
- [ ] 10 reference clips with titles/permissions/profile + deterministic seed script + expected results
- [ ] Automated tests, invalid/oversize/overlong, actual forbidden API calls, idempotency
- [ ] GitHub Actions CI/CD, proof of deploy and rollback
- [ ] **Actual deployed** architecture diagram including GCP names, region, trust boundaries, network paths, failure domains
- [ ] Short design report explaining decisions, limitations and recoveries
- [ ] Monitoring dashboard and actionable alert, actual Cloud Run Job cancel/restore evidence
- [x] Real recorded load-test conditions, p95, error rate and timestamps (Azure run of 2026-11-21 in `docs/EVIDENCE.md`)
- [ ] Dated monthly cost estimate by workload/region/tier/backup/egress and distinction from actual bills
- [ ] Cleanup and verification steps
- [ ] 10–15 minute demo script: normal flow, protected playback, correctness, failure+recovery, monitoring, CI/CD

Grade weights from brief: architecture 25%, deployment+automation 20%, security+correctness 15%, reliability+observability 15%, app completeness 15%, cost+communication 10%.

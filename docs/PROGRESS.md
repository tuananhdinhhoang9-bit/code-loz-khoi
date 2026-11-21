# Progress log

Short record of what was done, in order, and what each step showed. Dated measurements with IDs are in `docs/EVIDENCE.md`; design decisions and their trade-offs are in `docs/DECISIONS.md`. Rule kept throughout: nothing is reported as done unless it was run; anything not run is listed as not verified.

## Status (2026-11-22)

- **Azure edition (main):** running at `https://azure.uploadmdm.id.vn` (default hostname `https://videoportal-api.bravecoast-ef9b0b40.malaysiawest.azurecontainerapps.io` still works). Region `malaysiawest`, 48 resources managed by Terraform, deployed by GitHub Actions on every push to `main`.
- **Windows VPS edition (fallback):** separate system at `https://video.uploadmdm.id.vn`, unchanged.
- **Brief's tests on Azure:** Tests 1–3 pass (76 of 76 checks), failure drill passes for a graceful stop, load test recorded with p95, deploy and rollback through CI/CD demonstrated, workbook and one alert in place and the alert has fired once.

### Not verified or still open

- Sign-in uses local accounts in PostgreSQL, not Microsoft Entra External ID; the OIDC code path was tested only against a fake provider.
- Hard kill of the worker (recovery through lease expiry), the dead-letter path and the three-attempt limit were not triggered on Azure; they are covered by automated tests and by the local drill below.
- Load test: one run, read-only API mix, one 0.5 vCPU replica.
- Real cost: Cost Management had almost no data on the first day (0.0125 USD month-to-date); to be re-read and compared with the list-price table in `docs/AZURE_MONITORING_COST.md`.
- Sign-in, upload and playback through the custom domain were not exercised after the domain was bound (the hostname-dependent pieces were: certificate, redirect, CORS).
- Arrival of the alert e-mail is not recorded; no workbook screenshot; the demo script has not been rehearsed end to end; `docs/CLEANUP.md` is written but not executed.
- Demo Owner and Viewer accounts and sharing of reference clips are prepared outside this log.

## Timeline

| Date | Step | Result |
| --- | --- | --- |
| 2026-11-11 | Phases 00–06, local: requirement audit, local stack, schema and ten reference clips, authentication and authorization, private upload, FFmpeg transcode in a container, outbox, queue, bounded retries, idempotency | Local acceptance gates passed (first table of `docs/EVIDENCE.md`) |
| 2026-11-17 | GCP design: Terraform validated and planned only (57 resources), nothing applied | Archived; target changed |
| 2026-11-17 to 11-20 | Windows VPS edition (ADR-015 to ADR-020): Waitress, Caddy, PostgreSQL, native FFmpeg worker, local accounts, account management, redesigned interface | Installed and running; smoke test 22 of 22 on the VPS |
| 2026-11-20 | AWS design (ADR-021 to ADR-023): adapters and Terraform validated and planned (56 resources); one ACM certificate created | Dropped on 2026-11-21; adapters removed from `main` |
| 2026-11-21 | Azure phase 07: Blob Storage, Service Bus and OIDC adapters, run-once worker, maintenance command (ADR-024, ADR-025) | Local tests only: 181 passed, 7 skipped |
| 2026-11-21 | Azure phase 08: Terraform in `infra/azure/`, account preflight (ADR-026, ADR-027) | Plan only: 32 resources for the foundation, 35 in full. Region `malaysiawest` because the subscription policy excludes Singapore |
| 2026-11-21 | Azure phase 09: foundation applied; images built by GitHub Actions through OIDC because ACR Tasks and small VMs are refused on the student subscription (ADR-028); app and two jobs created; schema initialised | 38 resources; `/health` 200 with `database: ok` |
| 2026-11-21 | First real upload on Azure | Browser `PUT` to Blob Storage, Service Bus, KEDA-started job, FFmpeg, playback, delete all worked; 38.5 s from `complete` to `READY` |
| 2026-11-21 | Azure SDK request logging silenced (`app/logs.py`) | 182 passed, 7 skipped; 0 SDK lines afterwards |
| 2026-11-21 | `scripts/acceptance_test.py` for the brief's Tests 1–3 | Local 76 of 76, then Azure 76 of 76 |
| 2026-11-21 | Azure phase 10: `scripts/failure_drill.py` and `scripts/azure/Stop-TranscodeExecution.ps1` | Local drill passed; Azure drill passed, recovery 60.2 s after a graceful stop |
| 2026-11-21 | `scripts/load_test.py` | Azure: 10 users, 60 s, 3,479 requests, 0 errors, p95 285.9 ms |
| 2026-11-21 | Azure phase 12: deploy job, rollback workflow, six role assignments for the deploy identity (ADR-029) | Revision 1 -> 2 (pipeline) -> 3 (rollback, 87 s) -> 4 (pipeline); `terraform plan` shows no drift |
| 2026-11-21 | Azure phase 11: workbook "Video Portal", alert `videoportal-transcode-system-failure`, cost table; `complete` logs job, video and request IDs together | 185 passed, 7 skipped; second drill: alert fired 3 min 19 s after the stop |
| 2026-11-21 | Phase 13 documents: deployed architecture, design report, demo script, cleanup guide | Written; Mermaid diagram not render-tested |
| 2026-11-21 | Repository tidy-up: `vps` and `aws` branches removed from GitHub (history kept in a private bundle) | `main` is the only branch |
| 2026-11-22 | Repository history squashed into one commit; earlier commit IDs survive as image tags and on the Actions run pages | `main` restarted from a single commit |
| 2026-11-22 | Custom domain for Azure (ADR-030): `azure.uploadmdm.id.vn` bound with a managed certificate; the VPS keeps `video.uploadmdm.id.vn` | Both sites answer 200 on their own names |

## Local runs referred to from the evidence

These validated the scripts before they were pointed at Azure. They are not Azure evidence.

- **Acceptance script, local** (development server on localhost, local storage, PostgreSQL queue, real FFmpeg worker): `ACCEPTANCE_RESULT {"passed": 76, "failed": 0, "skipped": 0, "storage": "local"}`.
- **Failure drill, local, hard kill** (4K 29-second clip of 36.6 MB; the worker process and its FFmpeg child were killed at 5 % progress and a new worker was started by hand): `PROCESSING` at +2.0 s, killed at +8.8 s, `RETRYING lease_expired` at +190.1 s (181 s after the kill), `PROCESSING` again at +199.8 s, `READY` at +235.5 s; 12 playback probes during the outage all answered 409; result 1,592,709 bytes, 29,000 ms; `DRILL_RESULT` 6 passed, 0 failed. This is the lease-expiry path that the graceful stop on Azure does not exercise.
- **Load test, local:** 10 users, 15 s, 2,291 requests, 0 errors, p95 115.4 ms.
- **Automated tests:** `RUN_DB_TESTS=1 pytest -q` against a throwaway PostgreSQL cluster with real FFmpeg: 185 passed, 7 skipped at the last run that changed code; the same suite runs in the `ci` workflow on every push.

## Findings worth keeping

- One transcode at a time by design (`max_executions = 1`); a container needs about 25 s to start, so ten clips took about ten minutes and the last one waited 560 s. During that run the maintenance job re-published three events and the three duplicate messages each ended `no_op`: real evidence that a repeated event gives one result.
- An interactive `az containerapp exec … --command sh` session dropped while a password was being typed; passing the command directly (`--command "flask --app app.main create-user EMAIL --admin"`) worked.
- `az containerapp job stop` ends the container with SIGTERM, so the worker records `RETRYING worker_failed` itself; recovery time then depends on when the 5-minute maintenance schedule falls (60 s and 123 s were observed).
- A Container Apps environment in a custom VNet brings a Standard load balancer and public IP (about 22 USD/month at list price) that the first estimate missed.
- Blob Storage answers 409, not 403, for a URL without a SAS when anonymous access is disabled on the account.
- GitHub's OIDC subject now carries numeric owner and repository IDs; the federated credential must use the full subject string.

## Working rules used

Each step ended with its checks, an entry here, a scoped commit and a verified push. `terraform plan` was run before every `apply`; paid or irreversible steps were agreed first. Secrets, keys, SAS URLs and subscription or tenant IDs are kept out of the repository; Terraform state and `terraform.tfvars` stay on the operator's machine.

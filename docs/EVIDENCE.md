# Evidence — append real records after running

No actual test/deployment evidence at the time of starter creation.

| Test ID | Timestamp UTC | Input or command | Expected | Actual | Evidence (link/path/log/job ID) | Result |
| --- | --- | --- | --- | --- | --- | --- |

Store screenshots in `evidence/` only when produced by real tests; redact emails, private URLs, keys and tokens.

## 2026-11-11 local gates through Phase 06

Recorded at 13:01 UTC after actual execution; no cloud evidence claimed.

| Test ID | Input or command | Actual | Result |
| --- | --- | --- | --- |
| LOCAL-05 | RUN_DB_TESTS=1 RUN_DOCKER_TESTS=1 pytest -q before Phase 06 | 70 passed in 21.85 s, zero skips; real bounded worker image sha256:754331da7c50ae5423a313a6e290c8c548c17887907db50e4ef95daf8780e2ba | PASS |
| LOCAL-06 | Same full regression with Phase 06 tests | 86 passed in 50.31 s, zero skips; PostgreSQL + host media + Docker | PASS |
| LOCAL-KILL | tests/test_pipeline.py::test_kill_actual_ffmpeg_container_then_retry | Observe actual ffmpeg process; kill own container; RETRYING/0 pointers; new attempt READY/2 pointers/attempts=2 | PASS |
| LOCAL-10-CLIP | flask --app app.main local-process --limit 10 | 10 published and 10 READY outcomes; SQL: 10 MP4, 10 JPG, 0 unpublished events; disk queue empty | PASS |
| CLOUD-08-09 | Live private GCS/PubSub/Cloud Run integration and job cancellation | Not run; resources/access/approval absent, local tests do not replace this evidence | BLOCKED |

For exact commands use README and PROGRESS; generated media/private queue files remain under ignored .local, never attached as public evidence. Test retry clocks are advanced deterministically; real media/container execution is not mocked.

## Azure deployment — first evidence (2026-11-21, Phase 09 part 2)

Collected by commands run on the day; times are UTC unless marked local (UTC+7). Nothing here covers signed-in use: no account exists on the Azure deployment yet.

| What | Evidence |
| --- | --- |
| Live URL (default hostname) | `https://videoportal-api.bravecoast-ef9b0b40.malaysiawest.azurecontainerapps.io` |
| Foundation | `terraform apply` 12:57:04–13:04:45 local: `Apply complete! Resources: 32 added, 0 changed, 0 destroyed` (region `malaysiawest`, PostgreSQL 18 on B1ms) |
| Images | GitHub Actions run `44875944686` on commit `3e0ca6d`: job `test` success (78 s), job `images` success (110 s); both tags found in the registry afterwards. First run `44875542870` failed at `azure/login` with `AADSTS700213` (subject format), fixed in `infra/azure/github.tf` |
| App and jobs | `terraform apply` 13:37:30–13:38:22 local: `Apply complete! Resources: 3 added`; app revision `videoportal-api--cduuq77`, provisioning `Succeeded`, running |
| Health | `GET /health` -> 200 `{"database":"ok","status":"ok"}`: the API reaches the private PostgreSQL server with the password delivered from Key Vault |
| HTTPS only | `GET http://…/health` -> 301 to the same URL on `https`; the certificate of the default hostname validated in PowerShell and in the embedded browser; no `Server` header. No `Strict-Transport-Security` header is sent (open point) |
| Unauthenticated API | `GET /api/videos` -> 401; `GET /api/config` -> `auth_provider: local`, `max_upload_bytes: 50000000` |
| Page | `GET /` -> 200; `portal.js` byte-identical to the repository; in the embedded browser the guest page renders, no console errors, no private data. CSP lists only `'self'` and the storage account origin |
| Schema | Job execution `videoportal-maintenance-8m9qfkk` (command override `flask --app app.main init-db`): `Succeeded`, 06:39:16–06:39:49 |
| Scheduled maintenance | Execution `videoportal-maintenance-29920720`: `Succeeded`, 06:40:00–06:40:29; Log Analytics line `{"event": "maintenance", "recovered": 0, "published": 0, "work": 0, "uploads": 0, "outputs": 0}` — the job read the database and listed Blob Storage with its managed identity |
| Transcode job | Created, never executed (no message has been sent) |

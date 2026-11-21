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

Collected by commands run on the day; times are UTC unless marked local (UTC+7). This first table stops before sign-in; the signed-in flow is in the next section.

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
| Transcode job | Created; first executions are in the next section |

## Azure deployment — first real upload, transcode and playback (2026-11-21, Phase 09 part 3)

The owner created the administrator and used the page themselves; I did not sign in. Everything below is read from Azure afterwards (Container Apps job executions, Log Analytics, Service Bus counters). Times are UTC. The account's e-mail address is left out on purpose.

| What | Evidence |
| --- | --- |
| First administrator | Created by the owner with `az containerapp exec … --command "flask --app app.main create-user EMAIL --admin"` (hidden prompt). A first try through an interactive `sh` session lost its connection while the password was being repeated; no account was created by it |
| Sign-in | 12:35:51 `POST /api/auth/login` 200 (204 ms); then `/api/me`, `/api/videos`, `/api/users` 200 with the administrator's `uid` in the access log |
| Upload 2 (the good one) | 12:46:21 `POST /api/videos` 201 (19 ms); browser `PUT` straight to Blob Storage (source blob 3,325,726 bytes, `video/mp4`, read back by the worker with a pinned `versionid`); 12:46:22 `POST …/complete` 202 (100 ms, includes the Service Bus send) |
| KEDA starts the job | Execution `videoportal-transcode-vvrs2` started 12:46:27, 5 s after `complete`; `worker_started` 12:46:52 (about 25 s to pull the image and start the container) |
| Transcode | `PROCESSING` attempt 1, `queue_age_seconds` 32.5; FFmpeg process exit 0 in 5.2 s; `READY` at 12:47:00, `processing_seconds` 5.98, `output_bytes` 1,304,864 = `video.mp4` 1,280,336 (`video/mp4`) + `thumbnail.jpg` 24,528 (`image/jpeg`); execution `Succeeded` 12:47:02. From `complete` to `READY`: 38.5 s |
| Playback | 12:47:01 `GET …/playback` 200 and `GET …/thumbnail` 200; the owner reports that the video plays in the browser. The browser's own request to Blob Storage is not in our logs |
| Upload 1 (rejected on purpose) | 12:43:30 `POST /api/videos` 201 (3.5 s, first call fetches the user delegation key), 12:43:33 `complete` 202; source 5,799,032 bytes. Execution `videoportal-transcode-pfg55` 12:43:57–12:44:26 `Succeeded`: validation exit code 2, job `FAILED` with `input_too_long` after attempt 1, no retry (permanent error) |
| Delete | 12:46:29 `DELETE /api/videos/{id}` 200 for upload 1; Blob Storage answered 202 to the delete of the source blob version |
| Queue afterwards | `transcode-jobs`: `activeMessageCount` 0, `deadLetterMessageCount` 0 |
| Container is private | `HEAD` on the output blob URL without a SAS: 409 (public access is not permitted on the account) |
| Managed identity only | Worker log: `DefaultAzureCredential acquired a token from ManagedIdentityCredential` for both Service Bus and Blob Storage; no key or connection string is configured |

Not shown by this run: a second user being refused, HTTP range requests, retry and dead-letter on Azure, the failure drill, cost figures.
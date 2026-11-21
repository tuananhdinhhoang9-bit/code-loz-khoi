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

## Azure deployment — instructor's Tests 1–3 run by script (2026-11-21, Phase 09 part 4)

`scripts/acceptance_test.py` run by the owner from the VPS against the Azure URL (the owner typed the administrator's password; image `4a6353e`). Sign-in 13:42:43 UTC, last line about 13:58. Result line, copied from the terminal:

`ACCEPTANCE_RESULT {"passed": 76, "failed": 0, "skipped": 0, "storage": "blob"}` — exit code 0.

| Instructor's test | What the script checked on Azure | Result |
| --- | --- | --- |
| Test 1: valid videos play and match the output profile | Ten reference clips (1–3 s, 39–112 KB) uploaded to Blob Storage; each `READY`; playback URL 200 with duration within 350 ms (1022 / 2021 / 3019 ms); `GET` with `Range` -> 206 and the whole file as `video/mp4`; the downloaded output read with `ffprobe`: MP4, one H.264 yuv420p stream, at most 854x480, AAC; thumbnail is a JPEG | 50 of 50 PASS |
| Test 2: wrong format, too long, too large are refused cleanly | `text/plain` -> 400 `unsupported_content_type`; declared 50,000,001 bytes -> 413 `upload_too_large`; a real file of 50,000,001 bytes sent to Blob Storage (the SAS accepts it, 201) -> `complete` 413 `upload_too_large`, playback 409; text bytes declared as MP4 -> worker `FAILED invalid_media`; a 35-second clip -> worker `FAILED input_too_long`; for each: no playback URL (409), then deleted | 13 of 13 PASS |
| Test 3a: repeating an event gives one result | `POST …/complete` twice on a `READY` video -> 200 and the same `job_id` both times; the playback URL still points at the same blob | 2 of 2 PASS |
| Test 3b: no access without permission | No token -> 401 on metadata, status, playback, thumbnail; made-up token -> 401; blob URL without SAS -> 409, with a changed signature -> 403, neither returns video bytes; a second signed-in user: video not in their list, 404 on all four routes, cannot grant themselves access or delete; after the owner grants -> playback URL and bytes (206), still cannot delete; after revoke -> 404 | 11 of 11 PASS |

Read from Azure afterwards (not from the script):

| What | Evidence |
| --- | --- |
| Job executions | 15 executions of `videoportal-transcode` between 13:43:00 and 13:56:00, all `Succeeded`. Worker outcomes in Log Analytics: `READY` 10, `FAILED` 2 (`invalid_media`, `input_too_long`), `no_op` 3 |
| **Duplicate delivery on the real queue** | The scheduled maintenance run at 13:50:26 logged `"published": 3`: it sent three events again because their jobs had waited longer than the 300-second dispatch deadline (queue wait reached 447–560 s). Service Bus Basic has no duplicate detection, so both copies were delivered. The three extra executions (13:52:54, 13:53:25, 13:54:23) each ended `no_op`; there are 10 `READY` lines for 10 videos and every video has exactly one playback object. Not traced: which three jobs the duplicates belonged to (a `no_op` line carries no job ID) |
| Queue afterwards | `activeMessageCount` 0, `deadLetterMessageCount` 0 |
| API access log | `POST /api/videos` 201 x13, 400 x1, 413 x1; `complete` 202 x12, 413 x1, 200 x2; refusals 401 x5 and 404 x9 on the routes above; helper account created (201) and disabled again (200) |
| Throughput | One video at a time by design (`max_executions = 1`, about 25 s to start a container): ten clips took about ten minutes; `queue_age_seconds` 34 for the first, 560 for the last |
| Log fix | Since the new image: 1,525 console lines from `app.*` loggers, 0 from `azure.*` |

Not covered by this run: a worker killed half-way and its retry (failure drill); a load test; CI/CD rollback. The duplicate above happened by itself, not as a planned drill.

## Azure deployment — failure drill: transcode stopped mid-conversion (2026-11-21, Phase 10)

`scripts/failure_drill.py` run by the owner against the Azure URL (they typed the password) with a 1080p 29-second clip of 29,239,992 bytes; the stop was `az containerapp job stop` through `scripts/azure/Stop-TranscodeExecution.ps1 -Apply`. Video `4ad7bbd8-abe7-422c-b99c-a3658a4cfe36`, job `721d6dc1-f343-491b-ba5b-50a606a2f0c9`. Times UTC. Script result: `DRILL_RESULT` 6 passed, 0 failed, exit code 0.

| Time | Source | Event |
| --- | --- | --- |
| 14:29:29 | script | upload finished, `complete` accepted, status `QUEUED` |
| 14:29:30–31 | Container Apps system log | KEDA: metric `azure-servicebus-transcode-jobs` = 1, `Created 1 jobs`; execution `videoportal-transcode-t9fs5` |
| 14:29:42–53 | system log | image pulled in 9.8 s (257 MB); container `worker` started |
| 14:29:55.5 | worker log | `PROCESSING`, attempt 1, attempt ID `00fa0708-…`, `queue_age_seconds` 28.2 |
| 14:30:05 | script | status showed measured progress 22 %; stop requested for `t9fs5` (exit code 0) |
| 14:30:06.0 | worker log | FFmpeg process `exit_code: -15` (SIGTERM) after 9.9 s |
| 14:30:06.1 | worker log | job -> `RETRYING`, error `worker_failed`; the script saw `RETRYING worker_failed` 0.9 s after the stop |
| 14:30:06.8 | system log | `Job suspended`, pod deleted; execution status `Stopped` |
| 14:30:23–27 | maintenance log, script | scheduled maintenance: `"recovered": 1, "published": 1`; the script saw `QUEUED` again |
| 14:30:31 | system log | KEDA created execution `videoportal-transcode-h2js8` |
| 14:30:53.2 | worker log | `PROCESSING`, **attempt 2**, new attempt ID `e9c09793-…` |
| 14:31:05.8 | worker log | FFmpeg exit 0 in 11.7 s; `READY`, `output_bytes` 2,267,809; execution `Succeeded` 14:31:12 |

| Claim | Evidence |
| --- | --- |
| No partial output was published | Nine playback requests between the stop and `READY` all answered 409; the published objects belong to attempt 2 only |
| Honest progress | The status showed the measured 22 % while FFmpeg ran, then no percentage during `RETRYING` and `QUEUED` |
| Bounded retry, one result | Attempt 2 of at most 3 succeeded; one playable file (2,241,064 bytes, 29,002 ms); `complete` repeated afterwards still returns the same job |
| Recovery time | 60.2 s from the stop to `READY` (96.7 s after the upload). The maintenance schedule (every 5 minutes) happened to run 20 s after the stop; in the worst case this wait is about 5 minutes longer |
| Queue afterwards | `activeMessageCount` 0, `deadLetterMessageCount` 0 |

What this drill did **not** exercise on Azure: `az containerapp job stop` ends the container with SIGTERM, so the worker had time to record the failure and settle its message. A hard kill, where nothing is recorded and recovery must wait for the Service Bus lock and the job's lease to expire, was shown only locally (`RETRYING lease_expired` 181 s after the kill, see `docs/PROGRESS.md`). The dead-letter path and the three-attempt limit were not triggered on Azure either; they are covered by the automated tests.

## Azure deployment — API load test with p95 (2026-11-21)

`scripts/load_test.py` run by the owner from the VPS against the Azure URL (they typed the password). Client and server numbers are both from real samples of this one run.

| Condition | Value |
| --- | --- |
| Measured window | 2026-11-21 14:37:12 – 14:38:13 UTC (60 s), after a 10 s warm-up that is not counted |
| Load | 10 concurrent signed-in users, one keep-alive HTTPS connection each, no pause between requests |
| Requests | `GET /api/videos`, `GET …/status`, `GET …/playback`, `GET …/status`, repeated; 12 `READY` videos in the library (the ten reference clips and two others) |
| Client | The project's VPS, over the public internet to `malaysiawest` |
| Server | One replica of `videoportal-api` (0.5 vCPU, 1 GiB, Waitress with 6 threads), image `4a6353e`; PostgreSQL B1ms; `max_replicas = 1` |

| Result (client side) | Requests | Errors | p50 | p95 | p99 | Max |
| --- | --- | --- | --- | --- | --- | --- |
| All | 3,479 (58.0 per second) | 0 (0.00 %) | 178.6 ms | **285.9 ms** | 317.7 ms | 481.5 ms |
| `list` | 869 | 0 | 137.2 ms | 277.1 ms | 317.3 ms | 390.7 ms |
| `status` | 1,738 | 0 | 168.7 ms | 260.7 ms | 307.9 ms | 381.4 ms |
| `playback` | 872 | 0 | 201.6 ms | 301.6 ms | 382.4 ms | 481.5 ms |

Result line: `LOAD_RESULT {"users": 10, "warmup_seconds": 10, "duration_seconds": 60, "videos": 12, "measured_from_utc": "2026-11-21T14:37:12Z", "measured_to_utc": "2026-11-21T14:38:13Z", "requests": 3479, "errors": 0, "error_rate_percent": 0.0, "p50_ms": 178.6, "p95_ms": 285.9, "p99_ms": 317.7, "max_ms": 481.5, "requests_per_second": 58.0, "status_codes": {"200": 3479}}`

| Server side, same window | Evidence |
| --- | --- |
| Access log (Log Analytics) | 3,532 requests to `/api/videos…`, all 200, from 1 replica; handler time p50 85 ms, p95 186 ms, p99 234 ms, max 401 ms. Per 10 seconds: 574–585 requests, p95 182–190 ms (steady, no drift) |
| By route (handler time p95) | list 190 ms, status 119 ms, playback 200 ms |
| Container Apps metrics | `UsageNanoCores` maximum 505,095,336 (0.505 vCPU of the 0.5 allocated): the replica was CPU-bound; `RestartCount` 0; `Replicas` 1; working set about 225 MB. The metric minutes were still being ingested when read, so only the maximum is quoted |

Reading: about 58 requests per second is what one 0.5 vCPU replica gives for this read mix; the roughly 100 ms between handler p95 and client p95 is network plus waiting for one of the six worker threads. Not measured: uploads and transcoding under load (one video at a time by design), video bytes (served by Blob Storage, not by the API), more than one replica, a longer run.

## Azure deployment — deploy and rollback through GitHub Actions (2026-11-21, Phase 12)

Repository `main`; identity `videoportal-deploy` through OIDC, no stored password or key. Times UTC. Run pages: `https://github.com/tuananhdinhhoang9-bit/code-loz-khoi/actions/runs/<run id>`.

| Step | Evidence |
| --- | --- |
| Before | Revision `videoportal-api--0000001`, image tag `4a6353e…` (deployed earlier by Terraform from this machine) |
| **Deploy by pipeline** | Push of commit `ea2ceac4147cad337de9414ef45f522e7138a5b1`; `ci` run `44916112596`: `test` success 14:51:46–14:52:55, `images` success 14:52:58–14:54:42, `deploy` success 14:54:45–14:56:27 |
| After the deploy | Revision `videoportal-api--0000002` created 14:55:24, Healthy, 100 % of traffic, image tag `ea2ceac…`; `0000001` inactive; both jobs on `ea2ceac…`; `/health` 200 `database: ok`; `/api/videos` 401. `terraform plan` afterwards: `No changes` (Terraform does not pull the image back) |
| **Rollback** | Started by the owner in the GitHub UI: workflow `rollback`, input `image_tag = 4a6353eba63eb22c690f35bf31c4e1b28222e0a0`; run `44916720116` (`workflow_dispatch` on `main`): job `rollback` success 14:59:08–15:00:35 (87 s), no tests and no build |
| After the rollback | Revision `videoportal-api--0000003` created 14:59:42, Healthy, 100 % of traffic, image tag `4a6353e…`; `0000002` inactive; both jobs back on `4a6353e…`; `/health` 200 `database: ok`; `/api/videos` 401 |
| Roll forward | The push of the commit that records this table starts `ci` again and deploys that commit; its result is in `docs/PROGRESS.md` |

Not shown: the script's automatic restore when a new revision never becomes healthy (no broken image was deployed on purpose); a rollback across a database schema change (there was none; schema changes are additive by rule, ADR-020).

## Azure deployment — second failure drill: alert fired, request linked to job (2026-11-21, Phase 11)

Same script and clip as the first drill, run by the owner after the alert rule existed and after the pipeline deployed commit `2903d76` (run ID not read (GitHub API rate limit); revision `videoportal-api--0000005`). Video `2c8dd22d-922e-41fb-b77e-48802bfeeb75`, job `138ff53f-4402-4cd6-9ca7-cb201a47e769`. Times UTC. `DRILL_RESULT`: 6 passed, 0 failed.

| Time | Source | Event |
| --- | --- | --- |
| 15:28:34 | API log | `app.pipeline` line `QUEUED` with `job_id`, `video_id` and `request_id` `35dd0e8b-1cee-4a24-9c7f-809f96d4c6c4` — the new line that links a request to a job |
| 15:29:06.8 | worker log | `PROCESSING`, attempt 1 (execution `videoportal-transcode-dqxjm`), `queue_age_seconds` 32.7 |
| 15:29:15 | script | stop requested at 24 % measured progress |
| 15:29:16.1 | worker log | `RETRYING`, error `worker_failed` |
| 15:30:25 | maintenance log | `"recovered": 1, "published": 1` |
| 15:31:06.4 | worker log | `PROCESSING`, attempt 2 (execution `videoportal-transcode-vzrvp`) |
| 15:31:18.6 | worker log | `READY`, `processing_seconds` 12.2, `output_bytes` 2,267,809; recovered 123.1 s after the stop |
| **15:32:35** | Azure Monitor (`Microsoft.AlertsManagement/alerts`) | alert of rule `videoportal-transcode-system-failure`: severity `Sev2`, monitor condition **`Fired`**, state `New` |

| Claim | Evidence |
| --- | --- |
| Alert delay | 3 min 19 s from the `RETRYING` line (15:29:16) to `Fired` (15:32:35); inside the expected 3–10 minutes. One measurement |
| Alert is tied to the drill | It is the only alert in the resource group; the rule was created at 15:17 and had nothing to fire on until this stop |
| No partial output | 10 playback probes between the stop and `READY`, all 409 |
| Request -> video -> job | The `QUEUED` line above gives all three IDs; the worker lines carry the same `job_id` with one `attempt_id` per attempt |

Not confirmed here: that the e-mail reached the owner's mailbox (only the owner can see it); the automatic resolution of the alert (it was still `Fired` when read at 15:38); a screenshot of the workbook.
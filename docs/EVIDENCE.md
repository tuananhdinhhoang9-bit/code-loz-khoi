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

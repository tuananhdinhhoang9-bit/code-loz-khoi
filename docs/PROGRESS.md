# Progress checkpoint

**Status:** Deployment target changed on 2026-11-17 from GCP to a **Windows Server VPS** (owner decision, ADR-015). Phase 07 (VPS preparation) is implemented and tested on a Windows 11 development machine with real PostgreSQL 16.4 and FFmpeg 9.0.1: **126 tests passed, 6 skipped** (Docker-only tests; Docker is excluded by decision). **Nothing has been installed on the VPS**; service installation, NTFS ACLs, firewall, public HTTPS and off-VPS backup are UNVERIFIED and belong to Phase 08. The earlier GCP Terraform (plan only) is archived.

## Current phase
- Completed: prompts/01 through prompts/06 (local), prompts/07-VPS-WINDOWS-INFRA (preparation only, local commit). Next: prompts/08-VPS-DEPLOY, not started. No cloud or VPS changes made.

## Completed
- [x] Starter instructions, assignment requirement checklist and phase prompts prepared.
- [x] Phase 00: original PDF read, starter pack audited, local environment and Git remote checked, implementation plan recorded.
- [x] Phase 01 minimal local Flask/Jinja skeleton (future application phases not implemented).
- [x] Phase 01/02 tests: 20 passed with RUN_DB_TESTS=1; real HTTP home/health checks passed.
- [x] Phase 01 real PostgreSQL/Compose acceptance: 6 tests passed; actual home and DB health HTTP 200.
- [x] Phase 02: six PostgreSQL tables, constraints, repeatable media/DB seed and isolated-schema tests.
- [x] Phase 03: server-side Firebase SDK and Owner/Viewer API authorization; offline signature tests passed.
- [x] Phase 04: private local upload/list/status/permissions/signed output contract and responsive Jinja portal.
- [x] Phase 05: bounded real FFmpeg Docker worker, MP4/JPG/duration and invalid-media checks.
- [x] Phase 06: durable local outbox/queue, lease/attempt fencing, bounded retry/reconcile, real container kill recovery; all 10 existing seed jobs processed locally.
- [x] (archived) GCP Phase 07: Terraform fmt/init/validate/plan PASS, never applied.
- [x] Phase 07 (Windows VPS preparation): code, scripts, docs; real tests on a Windows dev machine. VPS itself untouched.
- [ ] Phase 08: deploy to the VPS (not started).
- [ ] Live Firebase account/project verification (BLOCKED: configuration not supplied).
- [ ] Cloud configuration/deployment.
- [ ] Failure/monitoring/CI evidence.

## Blockers
- Phase 05 worker/container blocker resolved by actual container tests below. Firebase/GCS production integration and cloud failure drill still unverified.
- Phases 07–12 cloud acceptance BLOCKED pending GCP project, billing/budget approval, IAM, region/tier/quota and tooling verification. No cloud access checks were run in Phase 00.
- Phase 07 plan blocker resolved on 2026-11-17 (see last Phase 07 entry). Phase 08 remains BLOCKED: needs explicit apply approval, a confirmed deployment project with billing and budget, real images and Firebase configuration.
- Current working copy is a ZIP snapshot without `.git`; commit/push BLOCKED until it is reattached to the repository (commands in the Phase 07 entry).
- GitHub repository is connected and push verified; it is no longer a blocker. CLI login remains separate from working Git credentials.

## Handoff template — Codex updates after EACH phase

### YYYY-MM-DD — Phase XX
- Scope completed:
- Files changed:
- Test command/result (PASS/FAIL/BLOCKED):
- Cloud operations done? Any cost impact?:
- Git commit hash and push verification (or reason blocked):
- Open issues with exact reproduction:
- Next phase:

Don't delete older checkpoint history. Keep summary compact and factual.

### 2026-11-11 — Skill installation (preparation only)
- Scope completed: installed the five core skills from docs/SKILLS_INSTALL.md into .agents/skills; retained all three existing local skills. Monitoring and optional skills deferred as documented.
- Sources pinned: google/skills@64d010629e61e4a7d59fc21e042362f370b5888b (cloud-run-basics, cloud-sql-basics, google-cloud-storage-basics); openai/skills@49f948faa9258a0c61caceaf225e179651397431 (security-best-practices); anthropics/skills@2c5958ecac7cee2b583967a2c4981d0f4a75c579 (frontend-design).
- Commands/results: official skill-installer install-skill-from-github.py with --repo, --ref, --path and --dest .agents/skills: PASS for all five. Verified SKILL.md files after installation. Application tests not applicable.
- Cloud operations/cost: none.
- Git commit/push: BLOCKED; this folder is not a Git repository. Next command after the team repository is ready: git init (if this folder is intended to become the repository).
- Next phase: 00-START.md; newly installed skills become available on the next turn.


### 2026-11-11 — GitHub connection and per-task delivery
- Scope: connect this folder to https://github.com/binzvn/DTDM.git (existing private repository, main); verified stored Git account binzvn and repository admin/push permission through GitHub API.
- Files: AGENTS.md now requires appropriate checks, progress update, scoped commit and immediate push after each completed task/step; .gitignore also excludes common private key files.
- Validation: documentation/skill files only; project-owned staged whitespace checks PASS; sensitive-file/content pattern scan PASS; ignore rules for .env, secrets, credentials and private keys PASS. Full whitespace check reports pre-existing formatting in vendored upstream skills; retained upstream files unchanged. No application exists yet, so application tests are not applicable.
- Cloud operations/cost: none.
- Git: initial commit and remote SHA verification performed as part of this setup; see Git history for commit identity. No existing remote commits were present at initial inspection.
- Next phase: prompts/00-START.md.

- Verified delivery: initial commit ddc89a62f4b5561cd45cb37f46a731b65e498576 pushed to origin/main; git ls-remote confirmed identical SHA and working tree was clean.
- Tooling limitation: Git 2.45.2.windows.1 available; GitHub CLI initially absent. Official winget/portable downloads did not finish and were stopped. CLI installation BLOCKED by incomplete download; retry: `winget install --id GitHub.cli --exact --source winget --accept-package-agreements --accept-source-agreements --silent`, then `gh auth login --hostname github.com --git-protocol https --web` and `gh auth status`. Git credential manager account binzvn and GitHub API permissions were verified without exposing tokens; Git push works independently of gh.


### 2026-11-11 — Phase 00: read, audit and prepare

#### Completed scope and requirement audit
- Read AGENTS.md, REQUIREMENTS.md, PHASES.md, 00-START.md and all four original PDF pages, including visual inspection of both figures. Audited the linked architecture/data/API/security/reliability/test/deployment/cost/deliverable documents. PDF SHA256: dda5df6976fe78ed6f60073090a9d90df96e63e4f3fee5bc13a61ed52a25113c.
- Core scope matches the PDF: Owner/authorized Viewer; 10 legal/synthetic clips <=30s and <=50 MB; repeatable seed; four domain entities; MP4/thumbnail/duration; private upload/playback; container conversion; source-version/profile identity.
- Reliability and final acceptance remain mandatory: transactional outbox, deduplication/stable operation keys, ack after durable progress, bounded retries/failed-job recovery, actual interrupted-cloud-transcode drill, dashboard/actionable alert, direct forbidden API tests, IaC recreation, CI/CD rollback, measured load results and workload cost estimate.
- GCP, Flask/Jinja/vanilla JS, PostgreSQL, FFmpeg, Terraform and one H.264/AAC 480p/JPG profile are project choices, not additional technologies required by the PDF. Keep the fixed stack; no React/Celery/Redis/Kubernetes/CDN/payment features or multiple profiles.
- PDF page 1 explicitly says “synthetic identities and simulated financial actions”; there is no financial workflow elsewhere. NEEDS INSTRUCTOR CLARIFICATION: ask whether this is template text. Keep synthetic identities, do not implement payments or silently declare this phrase satisfied. It does not block local bootstrap.
- Clarified ARCHITECTURE.md wording “regional instance (single zone)”: intended demo setup remains one zonal instance in a chosen region, not regional HA. This is wording clarification, not a design change; DECISIONS.md unchanged. Region/tier/private network and cost remain unverified until Phase 07.
- PDF suggests calendar milestones; project phases 00–12 are acceptance gates, not a claim that anything is deployed. Cloud prerequisites must be verified before cloud implementation; local work needs no GCP credentials.

#### Environment observed (read-only checks)

| Item | Actual result | Consequence |
| --- | --- | --- |
| Python | 3.12.4; `python -m pip --version`: pip 25.1.1 | Usable for Phase 01; use python -m pip, standalone pip is absent from PATH |
| Python packages | Global Flask/SQLAlchemy present; pytest/psycopg absent | Global packages are not project readiness; create .venv and install reviewed requirements in Phase 01 |
| Docker / Compose | docker not found in PATH or checked default Docker Desktop path | BLOCKED: cannot test DB/container flow; no daemon/Compose check was possible |
| FFmpeg / ffprobe | Not found in PATH | Real transcoding untested; Phase 05 should use the required container, host installation is optional |
| Terraform / gcloud | Not found in PATH | Deferred to Phase 07; no GCP commands, login, plan or resource creation performed |
| PostgreSQL client | psql not found in PATH | Host client optional; use Compose database in Phase 01 |
| Node / npm | v24.14.1 / 11.11.0 via npm.cmd | Available; not required for Flask/Jinja application runtime |
| Git | 2.45.2.windows.1; main tracks origin/main | Working tree clean before task; remote SHA matched 871722206c3bccd14abc75f8886b86dc324dd8b7 |
| GitHub CLI | 2.103.3 exists at C:/Program Files/GitHub CLI/gh.exe, absent from current PATH; auth status says not logged in | Earlier installer eventually completed; previous download blocker superseded. Git credential manager lists binzvn and Git remote works independently |
| Local configuration | No .venv or .env yet; no app/tests/infra/workflow code | Expected starter state; create only Phase 01 files next |
| Skills | Eight directories have SKILL.md (five external and three local) | Correct phase-specific skills available; no additional installation needed now |
| PDF tools | Bundled pypdf extracted 4 pages; Poppler rendered all 4 | PASS; pypdf emitted repair warnings, text and rendered pages were readable |

#### Implementation plan (one prompt/phase per future request)

| Phase | Work and gate before moving on |
| --- | --- |
| 01 | Minimal Flask/Jinja, isolated .venv, real gitignored .env, Compose PostgreSQL, home/DB health checks and passing local tests |
| 02 | Four domain tables plus permissions/outbox; uniqueness constraints; deterministic, repeatable seed and fixtures (real generated media verified by Phase 05) |
| 03 | Owner/Viewer authentication and server-side permissions; direct valid/missing/expired/forbidden API tests |
| 04 | Local/mock private storage, upload validation, listing, scoped playback/thumbnail contracts and permission tests |
| 05 | Bounded FFmpeg worker container; real valid clip produces verified MP4/JPG/duration; invalid/oversize/overlong tests |
| 06 | Local transactional outbox, fake transport, dispatch/lease/reconcile, idempotency and bounded retry; duplicate/crash tests |
| 07 | Verify GCP account/project/budget/region/tier/quota/IAM/private networking; Terraform fmt/validate and authorized plan; no apply |
| 08 | Only after explicit cloud approval: GCP integration, actual HTTPS/private storage/DB/PubSub/Job and ten-clip end-to-end run |
| 09 | Explicitly authorized real job termination, bounded recovery and one published result; save evidence |
| 10 | Measured dashboard, actionable alert tied to drill, dated workload cost estimate; install monitoring skill when needed |
| 11 | GitHub Actions test/build/deploy via workload federation and actual rollback evidence; no permanent service-account key |
| 12 | Full API/security/playback/load verification, actual architecture diagram, report/demo/cleanup instructions; deletion only with approval |

After each completed task/step: appropriate checks -> update this file -> inspect staged files/secrets -> scoped commit -> push -> compare local and remote SHA. Do not skip blocked gates or claim cloud evidence from local mocks.

#### First commands / unblock instructions (not executed here)
- To install the missing local container tool when starting Phase 01: `winget install --id Docker.DockerDesktop --exact`. Start Docker Desktop and satisfy its WSL2/virtualization prerequisites if requested; then verify `docker --version`, `docker compose version`, `docker info`. Installation may require a terminal restart/reboot; no success assumed.
- Phase 01 isolated Python setup: `python -m venv .venv`.
- Only after Phase 01 creates requirements and Compose files: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`, `docker compose up -d db`, `.\.venv\Scripts\python.exe -m pytest -q`, `.\.venv\Scripts\python.exe -m flask --app app.main run --debug`. These are planned commands, not results.
- Optional CLI verification after a fresh terminal: `gh --version`, `gh auth status`; if still absent from PATH, use `& 'C:/Program Files/GitHub CLI/gh.exe' auth status`. Optional separate CLI login: `& 'C:/Program Files/GitHub CLI/gh.exe' auth login --hostname github.com --git-protocol https --web`. Git push does not depend on it.
- First cloud action is the future user request to execute `prompts/07-TERRAFORM-PREFLIGHT.md`, after local gates pass and the project ID, spending policy and access are supplied. Do not invent runnable gcloud/Terraform resource commands before that preflight.

#### Validation and handoff
- PASS: four PDF pages extracted/rendered/read; phase prompts 00–12 present; required outputs/reliability/security/final evidence mapped above; repository/upstream checked; eight skill entrypoints present.
- PASS: no tracked .env/secrets/credentials (`git ls-files .env '.env.*' secrets credentials` returned empty); ignore rules checked again before commit.
- Documentation validation: `git diff --check`, inspect scoped diff and staged paths before commit. No application tests run: there is no application/test suite yet. Docker/DB/worker/cloud acceptance is BLOCKED or deferred as identified above, not PASS.
- Files changed: docs/PROGRESS.md and one wording clarification in docs/ARCHITECTURE.md. No application, dependencies, CI or infrastructure files created; no cloud operations or bills generated by this phase.
- Git delivery: scoped Phase 00 commit to existing main; verify push using `git rev-parse HEAD` and `git ls-remote origin refs/heads/main` (commit identity is available in Git history).
- Remaining input: instructor clarification on financial wording; Docker readiness for Phase 01; project/budget/access and demo identities before cloud integration. Team calendar, region/tier and quota have not been verified.
- Next phase: prompts/01-LOCAL-BOOTSTRAP.md. Do not start it in this request.


### 2026-11-11 — Phase 01: local bootstrap
- Scope implemented: app/main.py application factory, Jinja home, GET /health with real SQLAlchemy SELECT 1, request IDs and no-store responses. Returns 503 for missing/unreachable DB and avoids logging connection exceptions/credentials. No auth/upload/schema/seed/worker/cloud behavior implemented.
- Local PostgreSQL: compose.yaml uses postgres:16-bookworm, loopback-only published port, persistent named volume, healthcheck, 1 CPU / 512 MB limits and mandatory POSTGRES_PASSWORD. No password committed or generated. Real gitignored .env created with empty local placeholders; user must fill password privately. No .env.example runtime fallback.
- Dependencies: requirements.txt pins Flask 3.1.3, SQLAlchemy 2.1.8, psycopg[binary] 3.3.8 and python-dotenv 1.2.4; requirements-dev.txt adds pytest 9.2.0. README gives PowerShell setup, real DB test and safe stop commands. pytest.ini registers integration tests.
- Tests added: Jinja page, missing DB -> 503, successful SELECT 1 and connection cleanup via mock, failed connection without exception leak, real psycopg connection failure -> 503, opt-in real PostgreSQL health integration test.
- Commands/results: `python -m venv .venv` initially failed ensurepip under sandbox; retried with elevated execution successfully. Dependency install completed in .venv. An early check before install completion reported missing modules; rerun after successful install passed.
- PASS: `.\.venv\Scripts\python.exe -m pytest -q` -> 5 passed, 1 skipped in 4.03s. Initial sandbox cache warning disappeared on rerun outside restricted execution. Skip is explicitly the real PostgreSQL integration test, not a passed DB test.
- PASS: `.\.venv\Scripts\python.exe -m pip check` -> no broken requirements; Flask route discovery -> / and /health present.
- PASS: temporary Werkzeug server on loopback with actual urllib HTTP requests: GET / -> 200 and rendered Jinja text/link; GET /health with unset DB password -> 503, sanitized JSON and matching request-ID header. Server stopped after checks. This does not prove a successful DB connection.
- BLOCKED: `docker compose config --quiet`, `docker compose up -d --wait db` and real DB-success/health tests could not run: docker executable/Desktop absent and `wsl --status` says WSL is not installed. Compose file inspected but not validated by the Docker CLI. Do not mark Phase 01 fully accepted or proceed to Phase 02 yet.
- Exact unblock: install Docker Desktop/WSL2, complete any OS-required restart and start the Linux engine; privately fill POSTGRES_PASSWORD in .env; run `docker info`, `docker compose version`, `docker compose config --quiet`, `docker compose up -d --wait db`, then `$env:RUN_DB_TESTS='1'; .\.venv\Scripts\python.exe -m pytest -q; Remove-Item Env:RUN_DB_TESTS`. Verify /health -> 200 against that DB. No automatic system-level WSL installation/reboot or data deletion performed.
- Files: app/__init__.py, app/main.py, app/templates/index.html, compose.yaml, requirements.txt, requirements-dev.txt, pytest.ini, tests/test_app.py, tests/test_database.py, README.md, .gitignore (pytest temporary cache directories), docs/PROGRESS.md; local .env and .venv remain ignored. Existing architecture unchanged; no DECISIONS update needed.
- PASS: Compose YAML parsed with local YAML library and loopback port assertion; this static check does not replace Docker config/engine validation.
- Validation before commit: whitespace check, inspect staged scope and sensitive-file/token/key patterns, verify .env/.venv excluded. No fabricated cloud URLs/results or DB-success claims.
- Cloud operations/cost: none. Git: scoped Phase 01 commit/push to existing main, remote SHA compared after push; commit ID available in Git history.
- Next action: unblock and finish Phase 01 real DB acceptance; only then request prompts/02-DATABASE-SEED.md.


### 2026-11-11 — Requested local tool installation
- Requested scope only: WSL, GitHub CLI, Node.js LTS and FFmpeg Essentials; no Docker installation, app changes, cloud or Phase 02 work.
- GitHub CLI: winget GitHub.cli already at latest available 2.103.3; executable version verified. Existing Git credentials unaffected; CLI login not changed.
- Node.js: winget OpenJS.NodeJS.LTS upgraded 24.14.1 -> 26.13.0; node/npm executable checks performed after install.
- WSL: winget Microsoft.WSL 2.7.14 installed successfully with Administrator authorization. WSL version command confirms 2.7.14.0 and kernel 6.18.33.2-2. Enabled Microsoft-Windows-Subsystem-Linux and VirtualMachinePlatform; both DISM operations succeeded with exit 3010 (reboot required). No automatic reboot performed. Linux runtime/distribution execution remains BLOCKED pending reboot; no Linux user account was configured. Next command after reboot: `wsl --status`; if a Linux distribution is desired and none is present, run `wsl --install -d Ubuntu` and complete its user setup. Docker Desktop is still missing.
- FFmpeg: winget Gyan.FFmpeg.Essentials 9.0.1 installed successfully. Slow download and unsuccessful mixed-source/range checksum attempts were discarded without execution. Final archive downloaded in full from the exact GitHub URL in winget manifest; SHA256 matched FEC81AE03971D9DD4BE3EBE02E263BD2EC1D789483F931BDBA5F5715E65DA2E9; winget independently verified installer hash before extraction/install.
- PASS: ffmpeg and ffprobe both report 9.0.1; real smoke run generated a one-second synthetic MP4, ffprobe confirmed h264 and duration 1.000000. This is host-tool verification, not Phase 05 worker/container acceptance. Initial alias-path check used an absent Links location; retried successfully with the actual winget package bin path.
- Open a new terminal after installation for updated PATH; reboot Windows to activate WSL features. Follow with `gh --version`, `node --version`, `npm.cmd --version`, `ffmpeg -version`, `ffprobe -version`, `wsl --version`, `wsl --status`.
- Files changed: docs/PROGRESS.md only. Downloads/logs/synthetic smoke media reside in ignored .tmp/tools-install. No secrets/.env values logged or committed. Existing application tests were not rerun because application/dependency files were unchanged; actual tool smoke checks and documentation whitespace check are appropriate here.
- Git delivery: commit progress update, push main and compare remote/local SHA. Next project action remains finish Phase 01 Docker/PostgreSQL verification after reboot and Docker setup.


### 2026-11-11 — Phase 01 acceptance completed
- Resumed after interrupted image pull. Docker Desktop 4.99.0 / engine 29.9.3 and Compose 5.7.0 work with the running WSL2 docker-desktop distribution. Initial engine-startup API 500 resolved once startup completed; no application workaround required.
- Initialized new local PostgreSQL volume using a random password saved only in ignored .env; no existing container/volume was deleted. Windows refused binding port 5432, so set local POSTGRES_PORT=55432 after checking it was available. Compose still publishes loopback only; container uses 5432. Existing application supports this setting unchanged.
- PASS: docker compose config --quiet; docker compose --progress quiet up -d --wait db; container running/healthy at 127.0.0.1:55432. PostgreSQL reports 16.15 (Debian 16.15-1.pgdg12+2).
- PASS: RUN_DB_TESTS=1 with .venv/Scripts/python.exe -m pytest -q -> 6 passed in 4.90s, no skips. Real SQLAlchemy SELECT 1 passed; temporary local HTTP server returned GET / -> 200 and GET /health -> 200 with database=ok. Verified at 2026-11-11T12:06:17.446326+00:00 (UTC). Temporary HTTP server stopped; PostgreSQL remains running.
- Changes: docs/PROGRESS.md, README local-port troubleshooting; local .env excluded from Git. No code/design change, no cloud operation, no data deletion.
- Git: separate Phase 01 acceptance commit/push and remote SHA check before beginning Phase 02. Prior historical BLOCKED entries are superseded by this verified result.
- Next: implement only prompts/02-DATABASE-SEED.md as explicitly requested in this chat.


### 2026-11-11 — Phase 02 data model and reference seed completed
- Scope: SQLAlchemy models for Video, OutputProfile, TranscodeJob, OutputObject, VideoPermission and OutboxEvent. UUID public IDs; logical-job/version/profile uniqueness; unique output kind per job; composite FK prevents publishing output against a different job source/profile; permission/outbox FKs; bounded/nonnegative attempts, sizes/durations and valid states.
- Minimal Flask init-db and seed-db commands registered. init-db only creates missing tables; no automatic drops/migrations. Seed transaction commits videos/jobs/outbox/permissions together and preserves existing rows; conflicting seed values abort without overwriting user data. No queue transport, lease execution, processing, storage or authentication implemented.
- Real dataset: ten synthetic testsrc2/sine clips, 320x180 H.264/AAC, durations 1–3 seconds; actual sizes 39161–111697 bytes. Generated manifest includes title, SHA256, expected duration/profile/output properties and viewer permissions. Owner fixture owns ten; Viewer permitted on five even-numbered clips. Fixture UIDs are not real login accounts.
- Determinism: stable UUID5 seed IDs; generating dataset twice using installed FFmpeg produced identical manifests/hashes. Cross-FFmpeg-version bitstream equality is not promised. local-sha256 content versions are explicitly local fixture identifiers, never fabricated GCS generations; documented in DATA_MODEL and ADR-009. No READY videos, output objects or fake playback evidence seeded.
- Commands PASS: .venv/Scripts/python.exe -m app.seed_media --output-dir .local/seed; Flask init-db twice; Flask seed-db twice; pip check -> no broken requirements. Docker PostgreSQL 16.15 remains running and healthy at loopback port 55432.
- Real public-schema counts after both seeds: videos=10, output_profiles=1, transcode_jobs=10, output_objects=0, video_permissions=5, outbox_events=10. Job/outbox payload versions match; no output pointers published.
- Tests PASS: RUN_DB_TESTS=1 .venv/Scripts/python.exe -m pytest -q -> 20 passed in 6.91s. Tests cover actual ffprobe metadata for all ten clips, repeatable hashes/IDs/counts, tampered input hash rejection, duplicate logical-job/output/permission constraints, new source-version jobs, invalid attempts/status, wrong output version/profile, orphan rows, transaction rollback and seed conflict after earlier inserts. These are local DB/media checks, not delivery/failure-drill/cloud evidence.
- Isolation: every DB-model test creates its own test_phase02_<UUID> schema and removes only that schema; public demo data preserved. Verified no test schemas left behind; post-seed health returned 200. Verification UTC: 2026-11-11T12:11:58.629976+00:00.
- Files: app/models.py, app/seed.py, app/seed_media.py, app/db_cli.py, app/main.py; tests/conftest.py, tests/test_models.py, tests/test_seed.py; .gitignore, README.md, docs/DATA_MODEL.md, docs/DECISIONS.md, docs/PROGRESS.md. No new Python dependency. Local .env, generated .local media and test caches excluded from Git.
- Checks before commit: whitespace/diff scope and staged secret-pattern scan; no secrets or generated clips staged. Cloud actions/cost: none. No remaining Phase 01/02 blocker; authentication, real private storage, transcode/reliability and cloud acceptance belong to later phases.
- Git: Phase 01 acceptance committed/pushed separately as 4f3802200a7849c125d5d954f70ba2f5550817ea with remote SHA verified. Separate Phase 02 commit/push follows these checks, compare local/remote SHA; final hash is in Git history and chat handoff.
- Next phase: prompts/03-AUTH.md, only on a subsequent request. No Phase 03 implementation in this task.


### 2026-11-11 — Phase 03 local auth gate
- Implemented official Firebase Admin SDK 7.7.0 verification; only verified UID is trusted. Test verifier requires TESTING=True; runtime rejects emulator bypass. Sanitized API errors/request IDs; /api/me and private video metadata with Owner/explicit Viewer access. Missing/invalid/expired credentials -> 401; forbidden video -> 404; missing project/ADC/certificate connectivity -> safe 503.
- PASS: RUN_DB_TESTS=1 .venv/Scripts/python.exe -m pytest -q -> 36 passed in 8.16s. Direct API tests cover Owner/Viewer/stranger, permission revocation, forged UID body/header, absent/bad/expired tokens and blocked runtime test hooks. Actual Firebase SDK verifies locally RSA-signed tokens with test certificate transport: valid signature accepted; wrong signature/audience/issuer/expiry rejected. These are cryptographic/offline tests, not Firebase project login evidence.
- Files: app/auth.py, app/main.py, requirements.txt, tests/test_auth.py, tests/test_firebase_sdk.py, README.md, docs/PROGRESS.md. No DB data/schema reset; no cloud resources or fake runtime login.
- BLOCKED external verification: Firebase project, ADC and real demo-user ID tokens not provided. Next: configure FIREBASE_PROJECT_ID privately in .env and authorized ADC/workload identity, then call GET /api/me with a real client-issued Firebase ID token (do not paste/log it). Never use a permanent JSON service-account key. SDK default does not check token revocation on each call; ID token expiry limits that window; permission revocation is checked every request.
- Local Phase 03 acceptance complete; external identity integration explicitly unverified. Separate commit/push and SHA verification before Phase 04; user explicitly authorized proceeding with local Phase 04 storage tests. No UI polishing or upload worker in this phase.


### 2026-11-11 — Phase 04 local portal and private storage gate
- Implemented clean Jinja/CSS/vanilla-JS desktop/mobile portal. Email/password browser sign-in calls official Firebase REST; server verifies ID token with SDK. No password handled by portal server, no token persistence in browser storage, no fake runtime login. Missing auth configuration remains safe 503; public config only exposes Firebase client Web API key.
- Implemented authenticated create/list/status/complete/permission/playback/thumbnail/admin-monitor routes. Owner is verified UID, not client body. Every private endpoint authorizes on server; unauthorized viewers receive no signed URL/object bytes. List bounded to 100 permitted rows.
- LocalStorage keeps objects/metadata/persistent signing key under ignored .local/objects, never static/public. Random object paths, generation/size checks, 120-second operation-scoped signed URLs, write-once input, real byte limit, range playback, path traversal rejection, atomic concurrent signing-key initialization, log ticket redaction, no-store/no-referrer/nosniff/CSP. Local adapter deliberately blocked on Cloud Run; GCS deferred.
- Complete uses PostgreSQL row lock + unique key + one transaction for Job/Outbox. Duplicate/concurrent completions yield the same logical job. Playback requires both output pointers/files and matching source/profile/generation; QUEUED/failed/partial outputs denied. Already issued URLs are capabilities valid until TTL after permission revocation; new URL requests denied immediately.
- PASS: RUN_DB_TESTS=1 .venv/Scripts/python.exe -m pytest -q -> 55 passed in 11.60s, no skips. Includes earlier 36 Phase 03 tests, signed URL expiry/tampering/cross-operation, actual upload limits/type/metadata, concurrent complete, event-insert rollback, forbidden/allowed/revoked viewing, missing/changed outputs, Range responses, admin access and parallel signing key creation. READY byte fixtures are storage-contract fixtures, not real transcode evidence.
- PASS: node --check app/static/portal.js; pip check -> no broken requirements; whitespace checks. Only Firebase Admin SDK added as direct dependency in Phase 03; formatter was a temporary dev command, no Node app/dependency added.
- Browser QA PASS: Browser plugin not available; used bundled Playwright + installed Edge headless against temporary TESTING-only loopback server, isolated PostgreSQL schema and actual FFmpeg source clip. Official Firebase REST request intercepted only by QA harness and test verifier restricted to TESTING=True. Desktop 1366x900 and mobile 390x844: page/title/content, no overlay, no JS error, no horizontal overflow, screenshot inspection; owner email/password form -> upload real clip -> grant Viewer -> Viewer sees permitted item/owner form hidden -> QUEUED playback/thumbnail correctly 409. Expected 409 and favicon 404 were not counted as app errors. No production provider or GCS claims.
- Screenshots and QA scripts outside repository: C:/Users/Deli/.codex/visualizations/2026/11/11/01a1c806-a613-7300-8f46-e5faf4f3c5e6/phase04-desktop.png, phase04-interaction.png, phase04-mobile.png. Server stopped; QA-only schemas removed, zero remaining test schemas; public 10-video demo dataset unchanged. PostgreSQL remains healthy.
- Files: app/storage.py, app/videos.py, app/auth.py, app/main.py, app/templates/index.html, app/static/portal.css, app/static/portal.js; tests/test_portal.py and auth config test; README, API_CONTRACT, DECISIONS, PROGRESS. Real .env only received blank Firebase config keys if missing; secrets/keys/media excluded from Git. ADR-010/011 record local adapter and provider sign-in tradeoffs.
- BLOCKED external integration: provide project/client Web API key privately in .env (FIREBASE_PROJECT_ID/FIREBASE_WEB_API_KEY), authorized ADC/workload identity and configured Email/Password demo accounts; then run the local Flask command and sign in via portal. No permanent service-account key; no cloud resources provisioned. Real GCS signed URL/privacy/IAM tests belong to Phase 08, not this gate.
- Remaining local boundary: corrupt/overlong/unsupported media may be privately uploaded then must fail worker probing in Phase 05; only MIME/byte/metadata validated now. No orphan cleanup task yet; incomplete upload metadata requires a new upload. No worker progress, READY outputs, live failure drill or Cloud evidence fabricated.
- Git: Phase 03 pushed separately as 3cdd2a6e861bd52912766734779562b552eb5139 with matching remote SHA. Phase 04 scoped commit/push follows final staged diff/secret scan; verify remote SHA. Next: Phase 05 only after a new user request.


### 2026-11-11 — Phase 05 local FFmpeg worker PASS
- Files: worker/__init__.py, worker/transcode.py, worker/Dockerfile, .dockerignore, tests/test_transcode.py, pytest.ini, README, DECISIONS, PROGRESS. Standalone stdlib converter only; no DB READY/pipeline implementation yet, no new Python runtime dependency.
- ffprobe enforces actual bytes <=50 MB, duration <=30 s, bounded dimensions/fps, square pixels, allowlisted formats/codecs/stream counts. MP4 H.264/yuv420p + optional AAC, max 854x480/30 fps, aspect ratio preserved and no-audio accepted; real JPG generated and both outputs probed before metadata.json. Refuses nonempty attempt directories; catches encode/probe timeouts with bounded execution and sanitized error codes. On ordinary failures, partial attempt output files are removed; killed-process recovery belongs to Phase 06.
- Docker build PASS: video-worker:phase05, image ID sha256:754331da7c50ae5423a313a6e290c8c548c17887907db50e4ef95daf8780e2ba. .dockerignore sends only worker sources; no .env, storage keys or app dataset in image. Non-root uid 10001; actual tests used network none, readonly root/input, 1 CPU/512 MB, 64 pids and tmpfs 32 MB.
- PASS: host real FFmpeg cases including all ten reference clips, audio/no-audio, portrait ratio, corrupt/oversized/31-second/dimension/unsupported-codec rejection, existing-output preservation and thumbnail failure after MP4. PASS actual Docker conversions audio/no-audio and corrupt/overlong rejection. No simulated output used for this gate.
- Final command: RUN_DB_TESTS=1 RUN_DOCKER_TESTS=1 .venv/Scripts/python.exe -m pytest -q -> 70 passed in 21.85s, zero skips. Build and regression completed before Phase 06 began. No cloud resources, paid tests, service-account keys or real Cloud Run failure drill.
- Limits/tradeoff documented in ADR-012 and README; source codec/raster bounds are explicit demo rejection policy, not claimed support for every video format. Production Firebase/GCS remain BLOCKED independently of this local gate.
- Git: scoped Phase 05 commit/push and local/remote SHA comparison before starting Phase 06. Next: Phase 06 local DB outbox/lease/retry, authorized by user; no Phase 07 work.

### 2026-11-11 — Phase 06 local reliability PASS; requested stopping point
- Prior gate: Phase 05 delivered as 67cab639736eeb198f2aaac60eda7f6e65965c71; local and origin/main SHA matched before Phase 06 started.
- Files: app/pipeline.py, app/queue_local.py, app/worker_runner.py, app/pipeline_cli.py, app/main.py, tests/test_pipeline.py; README, DATA_MODEL, PIPELINE_RELIABILITY, DECISIONS, EVIDENCE, PROGRESS. No new dependency/schema/service. Existing transactional job/outbox creation retained and regression tested.
- Implemented stable event UUID, local file queue fsync/rename, row-locked central claim, 180-second lease + attempt UUID fencing, bounded Docker execution, immutable private staging and atomic two-output/READY publication. Source version and both output formats checked against actual files. Structured logs record measured timings/bytes without secrets. Compact job/attempt paths fix Windows MAX_PATH; ADR-013 explains mapping to immutable source/profile identity.
- Retries: max 3 logical attempts with 5/10-second backoff; permanent invalid media/source errors FAILED immediately; max 5 relay/dispatch deliveries per campaign; malformed messages to local dead letters. local-jobs shows operator state; retry-job explicitly resets only FAILED for a new bounded campaign. Reconcile requires another local-process invocation, not an unattended service. Orphan scratch/output files remain private; automated cleanup/disk quota not implemented.
- Final regression PASS: RUN_DB_TESTS=1 RUN_DOCKER_TESTS=1 .venv/Scripts/python.exe -m pytest -q -> **86 passed in 50.31s, zero skips**. Real PostgreSQL isolated schemas, real host FFmpeg and actual Docker image. Includes duplicate/concurrent delivery; relay crash after publish; crash after partial MP4 and after staging; output DB transaction rollback; source tampering; stale attempt fence; bounded retry/publish/lost dispatch; failed ack; queue restart; production adapter/auth guards; authorized viewer playback and forbidden outsider.
- Actual local kill PASS: test_kill_actual_ffmpeg_container_then_retry observed ffmpeg via docker top pid,comm, killed only its UUID-named test container, verified RETRYING/zero published pointers, then real Docker retry produced READY with exactly 2 pointers and attempts=2. Retry deadlines advanced through injected test clock; no claim of waiting 180 seconds or performing a Cloud Run drill.
- Actual operator smoke PASS: .venv/Scripts/python.exe -m flask --app app.main local-process --limit 10 -> published=10 and ten READY outcomes. Read-only SQL verification: 10 READY jobs, 10 MP4 + 10 thumbnail rows, 0 unpublished events; FileBroker.receive() is None. Generated outputs remain ignored under .local. No fake account login used by CLI. Fixture demo-owner/demo-viewer still are not real Firebase accounts.
- Additional checks PASS: pip check; scoped whitespace/content/secret-file checks before commit. .env and .local/objects/.local/queue ignored. Runtime rejects APP_ENV other than local and Cloud Run K_SERVICE with current adapters. Fake broker/verifier exist only in tests; no production mock deployed. No cloud resources, billing, IAM changes or data deletion.
- Git: scoped Phase 06 commit/push follows staged review; verify HEAD equals origin/main via git ls-remote. Commit identity is available from git log -1; final response records verified SHA. No force push.
- **STOP:** local acceptance through Phase 06 complete; Phase 07–08 remain unstarted/BLOCKED by external setup below. Cloud failure drill/alerts/p95/cost/CI deployment remain unverified; local kill does not satisfy Phase 09.

#### Missing before Phase 07–08 (no cloud operations performed)
- Terraform and gcloud not found in current PATH. Next local check after installing/reopening shell: `Get-Command terraform,gcloud`; then `terraform version` and `gcloud version`. Tool installation alone does not authorize deployment.
- Need approved GCP project ID, region choice, billing/budget ceiling, quotas/tier and permitted IAM principal. No Terraform configuration/plan/apply for these phases has been executed. Next task: read prompts/07-TERRAFORM-PREFLIGHT.md and linked cloud-safety skills before writing infra/preflight commands. Paid apply requires explicit approval.
- Need real Firebase project/client Web API key privately configured in .env, Email/Password provider + demo Owner/Viewer accounts, authorized ADC/workload identity; then run `.venv/Scripts/python.exe -m flask --app app.main run --host 127.0.0.1 --port 5000` and verify actual sign-in /api/me and permissions. Do not paste tokens, store permanent JSON keys or replace auth with fixtures.
- Phase 08 must implement real GCS private storage/signing adapter, Pub/Sub authenticated dispatcher + dead-letter, Cloud Run Job integration, and test deployed private upload/playback. Current adapters intentionally refuse production. Infrastructure still needed per fixed architecture: Artifact Registry, Cloud SQL PostgreSQL/connectivity, private buckets, Pub/Sub delivery, Cloud Run service/job, Secret Manager, appropriate service identities/IAM and later scheduler/monitoring/CI identity. No resource URL, price or permissions are assumed provisioned.

### 2026-11-11 — User-requested frontend redesign (local UI scope only)
- Applied frontend-design and student-simple-code; used frontend-testing-debugging for rendered QA. User explicitly authorized this UI refinement after Phase 06; no Phase 07 implementation or architecture change.
- Files: app/templates/index.html, app/static/portal.css, app/static/portal.js, docs/PROGRESS.md. Palette: navy #14223c, ink #17233b, canvas #f5f7fa, cobalt #315de4 and quiet borders. Local Bahnschrift/Segoe UI font stack; no external fonts, packages or image requests. Desktop sidebar, responsive navigation, compact account form, native file selection, clear library empty state/status badges, improved spacing and short Vietnamese copy. Abstract CSS video illustration is decorative, not a fabricated output thumbnail.
- Real in-page anchors with active/aria-current state, keyboard skip link/focus outlines, explicit input labels, reduced-motion preference and mobile stacking. Login fields hide only after verified identity; logout/error restores them. Upload/status/permissions/playback contracts remain unchanged; removed stale copy claiming worker is a future phase. No new feature, frontend framework or fake runtime login.
- Regression PASS: RUN_DB_TESTS=1 RUN_DOCKER_TESTS=1 .venv/Scripts/python.exe -m pytest -q -> 86 passed in 41.28 s, zero skips. node --check app/static/portal.js PASS; final formatter and scoped whitespace checks PASS. Final navigation refinement separately verified in real browser after formatting.
- Browser plugin not available; used installed Edge + existing bundled Playwright without adding dependencies. Isolated TESTING-only Flask server on 127.0.0.1:5017 with separate PostgreSQL schema: desktop 1366x900/mobile 390x844, page identity/content, no framework overlay/JS errors/overflow, account sign-in via test-intercepted Firebase REST, actual clip upload, grant Viewer, logout/login Viewer, owner controls hidden, queued playback safely denied (expected HTTP 409). Test server stopped and only its temporary schema removed. This is not a live Firebase sign-in claim.
- Real runtime browser PASS at http://127.0.0.1:5000/: keyboard skip link, anchor/active navigation, widths 320/390/768/1366 without horizontal overflow, no JS errors, missing Firebase configuration gives understandable error and retains login form. Real local Flask server left running for preview; no test verifier on this server. Live Firebase remains BLOCKED pending prior configuration; no Cloud resources/bills.
- Screenshots/scripts outside repository: C:/Users/Deli/.codex/visualizations/2026/11/11/01a1c806-a613-7300-8f46-e5faf4f3c5e6/redesign-desktop.png, redesign-mobile-entry.png, redesign-interaction.png, redesign-mobile.png; redesign_browser_qa.cjs and redesign_runtime_qa.cjs. Desktop/mobile screenshots visually inspected; all visible assets loaded.
- Git: review scoped diff/staged names, verify secrets ignored, commit and push immediately; compare HEAD with remote main. Next phase remains 07 preflight only when requested; prior cloud/auth blockers unchanged.

### 2026-11-17 — Phase 07: Terraform written; fmt/validate/plan BLOCKED
- Context: work resumed on a different machine from the GitHub ZIP of `main` (no `.git`, `.venv`, `.env` or `.local`). Checked tools: Python 3.12.10, Git 2.56.0, Node, winget and WSL present; `docker`, `ffmpeg`, `terraform`, `gcloud`, `gh`, `psql` NOT found. The 86-test local result above was therefore not rerun here; no application code was changed in this phase.
- Scope completed: minimal Terraform for the documented topology in `infra/` (35 resources + 1 data source, as written): APIs, VPC/subnet + Private Services Access, private-IP zonal Cloud SQL PostgreSQL 16 with DB/user and Secret Manager password, private bucket with public access prevention and `staging/` lifecycle, Artifact Registry, Pub/Sub topic + OIDC push subscription + dead-letter, two paused Cloud Scheduler jobs, Cloud Run `video-api`/`video-relay`/`video-dispatcher`, Cloud Run Job `video-worker`, six service accounts with resource-level least-privilege bindings. All instance counts, CPU/memory, timeouts and retries are explicit. No ALB, NAT, CDN or VPC connector.
- Deliberately NOT included (later phases or needs access): monitoring dashboard/alert (Phase 10), GitHub Workload Identity Federation and remote state (Phase 11), billing budget (needs billing-account permission; create manually before any apply), Firebase/Identity Platform configuration, Artifact Registry cleanup policy.
- Files changed: infra/versions.tf, variables.tf, main.tf, iam.tf, run.tf, messaging.tf, outputs.tf, terraform.tfvars.example; docs/CLOUD_DEPLOY.md (Phase 07 section: resources, IAM table, networking assumptions, Phase 08 contracts, cost risks), docs/DECISIONS.md (ADR-014), docs/PROGRESS.md.
- Test command/result:
  - `terraform fmt -check`, `terraform init`, `terraform validate`: **BLOCKED** — Terraform is not installed. The HCL has never been parsed by Terraform; provider argument names (google `~> 6.0`) are unverified and may need fixes on first validate.
  - `terraform plan`: **BLOCKED** — no Terraform, no gcloud, no project ID, no credentials.
  - Only check actually run: a text scan of the `.tf` files for balanced braces/brackets/quotes, tabs, trailing whitespace and duplicate block addresses — clean. This is not a substitute for `fmt`/`validate`.
  - Application tests: not run (no app change; Docker/FFmpeg/.venv absent on this machine).
- Known risks to check on the first real validate/plan: Pub/Sub service agent may not exist until the API is first used (IAM bindings to it would fail once, then succeed on re-apply); Direct VPC egress for jobs/services and `db-f1-micro` availability in `asia-southeast1`; organisation policy may reject the `allUsers` invoker on `video-api`; internal-ingress acceptance of Pub/Sub push and Scheduler; enabling APIs requires Service Usage and Cloud Resource Manager to be enabled already.
- Cloud operations done? None. No login, no plan, no apply, no resources, no cost.
- Git commit hash and push verification: **BLOCKED** — the working copy has no `.git`. To reattach without losing the new files (run inside the project folder, needs access to the private repo):
  `git init -b main` ; `git remote add origin https://github.com/binzvn/DTDM.git` ; `git fetch origin main` ; `git reset origin/main` ; `git status` (should list only `infra/` and the three docs) ; then stage those paths, commit, `git push origin main`, and compare `git rev-parse HEAD` with `git ls-remote origin refs/heads/main`.
- Exact next commands to clear the Phase 07 gate:
  1. `winget install --id Hashicorp.Terraform --exact` then, in a new terminal, `terraform version`.
  2. `terraform -chdir=infra fmt -check -recursive` ; `terraform -chdir=infra init` ; `terraform -chdir=infra validate`. Commit the generated `infra/.terraform.lock.hcl`.
  3. For a plan only: `winget install --id Google.CloudSDK --exact`, `gcloud auth application-default login`, copy `infra/terraform.tfvars.example` to `infra/terraform.tfvars` with the approved project ID, then `terraform -chdir=infra plan`. Review the creations and the cost risks in docs/CLOUD_DEPLOY.md.
  4. **Do not run `terraform apply`** until the owner explicitly approves the project, budget and the public `allUsers` invoker grant.
- Next phase: finish the Phase 07 gate (steps 1–3). Phase 08 only after that and after explicit cloud/billing approval.

### 2026-11-17 — Phase 07 follow-up: fmt/init/validate PASS; plan still BLOCKED
- Supersedes the fmt/init/validate BLOCKED lines in the entry above. User approved installing Terraform: `winget install --id Hashicorp.Terraform --exact --source winget` -> Terraform v1.17.1 (winget verified the installer hash). The winget alias needs a new terminal; this session called the package executable directly.
- PASS: `terraform -chdir=infra fmt -check -recursive -diff` -> exit 0, no diff.
- PASS: `terraform -chdir=infra init -input=false` -> exit 0; selected hashicorp/google v6.50.0 and hashicorp/random v3.9.1 (both signed by HashiCorp); created `infra/.terraform.lock.hcl` (commit it). `infra/.terraform/` is gitignored.
- PASS: `terraform -chdir=infra validate` -> "Success! The configuration is valid." No `.tf` file needed changes after the first write.
- What validate does and does not prove: argument names, types and references match the provider schema. It does not contact GCP, so region/tier availability, quotas, organisation policy, IAM permissions, the Pub/Sub service-agent timing and all networking assumptions in docs/CLOUD_DEPLOY.md remain unverified.
- BLOCKED: `terraform plan` — gcloud not installed, no approved project ID, no credentials. Next commands: `winget install --id Google.CloudSDK --exact` ; new terminal ; `gcloud auth application-default login` ; copy `infra/terraform.tfvars.example` to `infra/terraform.tfvars` and set the approved `project_id` ; `terraform -chdir=infra plan`. No apply without explicit approval.
- Files changed: infra/.terraform.lock.hcl (new), docs/PROGRESS.md. Cloud operations/cost: none. Application tests: not run (no app change; Docker/FFmpeg/.venv absent here).
- Git: still BLOCKED (no `.git` in this working copy); reattach commands are in the entry above.

### 2026-11-17 — Phase 07 follow-up: gcloud installed; plan BLOCKED on login and project ID
- User approved installing the SDK: `winget install --id Google.CloudSDK --exact --source winget` -> Google Cloud SDK 593.0.0 (winget verified the installer hash; the installer requested administrator rights). Installed at `%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd`; `gcloud version` -> exit 0.
- Observed state (read-only checks, no login attempted): `gcloud auth list` -> no accounts; `gcloud config get-value project` -> unset; no application-default credentials file. No GCP API was called.
- BLOCKED: `terraform plan`. Remaining steps need the project owner personally: (1) in a new terminal run `gcloud auth application-default login` and sign in through the browser; (2) supply the approved GCP project ID; (3) copy `infra/terraform.tfvars.example` to `infra/terraform.tfvars` and set `project_id`; (4) `terraform -chdir=infra plan`. The signed-in identity needs read access to the project for the plan to refresh. No apply without explicit approval.
- Files changed: docs/PROGRESS.md only. Cloud operations/cost: none. Git: still BLOCKED (no `.git`).

### 2026-11-17 — Phase 07 follow-up: ADC login done; plan BLOCKED on project choice only
- The owner completed `gcloud auth application-default login` in a terminal tab (browser sign-in by the owner; no credentials handled by the assistant). Application-default credentials file now exists. gcloud warned that no quota project is set for ADC.
- Read-only check with ADC: Cloud Resource Manager project list returned two projects, one ACTIVE (an auto-created default project) and one in DELETE_REQUESTED. Neither has been confirmed by the owner as the approved project for this course work; project IDs are intentionally not recorded here until one is approved.
- BLOCKED: `terraform plan` — waiting for the owner to name the target project ID. Then: create `infra/terraform.tfvars` with `project_id`, run `terraform -chdir=infra plan`. Billing link, budget and quotas of the chosen project remain unverified. No apply without explicit approval.
- Files changed: docs/PROGRESS.md only. Cloud operations: one read-only project list; no resources, no cost. Git: still BLOCKED (no `.git`).

### 2026-11-17 — Phase 07 gate PASS: terraform plan (plan only, nothing applied)
- Owner chose project `gen-lang-client-0845795618` (auto-created "Default Gemini Project", ACTIVE) as the **plan-only** target. It is not approved for apply; a dedicated project may replace it by changing one line in the gitignored `infra/terraform.tfvars` (created this step: `project_id`, `region = asia-southeast1`).
- PASS: `terraform -chdir=infra plan -input=false -lock=false` -> exit 0, no errors or warnings: **Plan: 57 to add, 0 to change, 0 to destroy.** (35 resource blocks expand to 57 instances through `for_each`: 11 APIs, 6 service accounts, 3 services, etc.) No `-out` file and no state file were written.
- Planned creations, by type: 11 project services; VPC, subnet, PSA range + service-networking connection; Cloud SQL instance, database, user; random password, secret + version, 4 secret accessors; bucket + 4 bucket IAM members; Artifact Registry repo; 2 topics, 2 subscriptions, 3 Pub/Sub IAM members; 6 service accounts + 2 service-account IAM members; 3 Cloud Run services + 4 invoker bindings (one is `allUsers` on `video-api`); 1 Cloud Run job + 1 executor binding; 2 Cloud Scheduler jobs (paused).
- What this plan proves: credentials work, the project is readable, the configuration resolves against the live provider. What it does **not** prove: that the project has billing linked, that `db-f1-micro`/Direct VPC egress/quotas are available in `asia-southeast1`, that organisation policy allows the `allUsers` grant or the peering, or any cost figure. Those surface only at apply and remain unverified. gcloud also warned that ADC has no quota project; the plan did not need one.
- Phase 07 acceptance per docs/PHASES.md (`fmt`, `validate`, plan if allowed; no apply): met. Cost risks and networking assumptions are in docs/CLOUD_DEPLOY.md.
- Files changed: docs/PROGRESS.md; local-only infra/terraform.tfvars (gitignored). Cloud operations: read-only plan refresh; no resources created, no cost.
- Git: still BLOCKED (no `.git` in this working copy); reattach commands are in the first Phase 07 entry. Files to commit: infra/*.tf, infra/terraform.tfvars.example, infra/.terraform.lock.hcl, docs/CLOUD_DEPLOY.md, docs/DECISIONS.md, docs/PROGRESS.md.
- Next phase: prompts/08-GCP-INTEGRATION.md — only on a new request and only after explicit approval of the deployment project, billing/budget and the public invoker grant. **No `terraform apply` has been run.**

### 2026-11-17 — Phase 07 (new): Windows Server VPS infrastructure and migration — preparation only

Owner decision: no Google Cloud; production runs natively on an existing Windows Server VPS (3 vCPU, 4 GB). This entry supersedes the GCP Phase 07 entries above for planning purposes; they remain as history. Owner also chose: install test tools on the dev machine, local accounts instead of Firebase, and **commit locally without pushing**.

#### Task 1 — audit of the repository as found (before changes)
| Area | Found | Classification |
| --- | --- | --- |
| Flask app (`app/main.py`), Jinja portal, request IDs, security headers | Working, tested | Keep |
| Models: 6 tables, constraints; "migration" = `init-db` (`create_all`, no drops) | Working, tested | Keep; extended additively |
| Auth: Firebase Admin SDK verification, never configured against a real project; test verifier hook | Offline tests only | Adapter switch: local accounts added, Firebase kept as option |
| Upload/list/status/permissions/playback APIs, Range via `send_file` | Working, tested | Keep; delete API and progress added |
| Local private storage with signed tickets, write-once, traversal check | Working, tested | Keep; hardened for Windows (names, junctions, free space, streamed hashing) |
| Outbox + relay + claim/lease + reconcile + bounded retry (`app/pipeline.py`) | Working, tested with fake transport | Keep unchanged in logic |
| Transport: `FileBroker` (file queue), dev-only | Working | Keep for dev; production adapter added (`PgBroker`) |
| Runner: `run_container` (Docker) | Working where Docker exists | Keep for dev; production adapter added (`run_native`) |
| Worker media code `worker/transcode.py` | Working | Needed Windows changes: tool paths, thread/timeout/size settings, progress, error detail |
| Runtime guard refusing every non-local `APP_ENV` | By design for Cloud Run | Changed: production allowed with explicit private absolute paths |
| No production server, no service definitions, no logging config, no backup, no delete, no cleanup | Missing | Not implemented before; added now |
| `init-db` did not create the output profile (only `seed-db` did) | Latent defect: a fresh production DB could not accept uploads | Fixed (found by the rehearsal) |
| Dockerfile, compose.yaml, `infra/` Terraform, GCP docs/prompts | Present | Archived / dev-only; untouched in content |
| Risk to Phase 01–06 | `storage.py`, `pipeline.py`, `transcode.py`, `main.py`, `videos.py` were edited | Mitigated: all pre-existing tests still pass unmodified |

#### What was built
- Storage: strict object-name pattern, Windows device names and symlink/junction refusal, free-space check (507), configurable limit, fsync, streamed SHA-256 with a verified-hash cache, `delete`.
- API: `DELETE /api/videos/{id}`, measured `progress_percent`, `/api/config`, richer admin monitor, structured access log without query strings.
- Local accounts: `users` + `auth_sessions`, scrypt, lockout, per-IP limit, login/logout, CLI `create-user`/`set-password`/`disable-user`/`enable-user`.
- Queue: `queue_messages` + `PgBroker` (SKIP LOCKED, visibility timeout, delivery cap, dead rows).
- Worker: `run_native` (Job Object: kill-on-close, memory cap, CPU affinity, low priority, timeout, cancellation), heartbeat + progress, `python -m app.worker_service` loop with single-instance advisory lock, graceful stop, hourly cleanup.
- Serving: `python -m app.serve` (Waitress, loopback, trusted-proxy handling), `deploy/windows/Caddyfile`.
- Operations: rotating redacted JSON logs, cleanup of temporary/abandoned/orphan data, `system-status`.
- Scripts (`scripts/windows/`): preflight, install-prerequisites, setup-database, install-services, start/stop/restart-services, status, healthcheck, register-tasks, backup, restore, rehearsal; plus `scripts/smoke_test.py`.
- Docs: six `WINDOWS_VPS_*.md`, PHASES, AGENTS, README, DECISIONS (ADR-015–020), DATA_MODEL, API_CONTRACT, PIPELINE_RELIABILITY, SECURITY, `.env.example`, archive banners.

#### Test evidence (all real, Windows 11 Pro build 26300 dev machine, Python 3.12.10, PostgreSQL 16.4 portable on 127.0.0.1:55432, FFmpeg 9.0.1, Caddy 2.11.9)
- `RUN_DB_TESTS=1 .venv\Scripts\python.exe -m pytest -q --basetemp=D:\VideoPortalDev\pytest-tmp` -> **126 passed, 6 skipped in 150.64 s**. The 6 skips are the Docker-image tests (4 in test_transcode, 2 in test_pipeline); Docker is not installed and is excluded by decision, so `run_container` was NOT re-verified on this machine.
- All 80 pre-existing non-Docker tests pass without modification. New file `tests/test_windows_vps.py`: 46 tests covering Windows paths, upload limits, storage full, junction refusal, authorization on every private API, Range seeking, delete, queue concurrency/visibility/dead letters/delivery cap, native pipeline with real FFmpeg, backlog on one worker, worker restart recovery, heartbeat/lease loss, FFmpeg timeout and cancellation killing the process tree, worker death not leaving FFmpeg, 2-CPU confinement, single-worker lock, additive migration, cleanup, production path guard, log redaction/rotation, CLI account management, backup+restore scripts round trip, worker service graceful shutdown and Waitress as real subprocesses.
- Bugs found by real runs and fixed: advisory lock not released (pooled connection); `flask` auto-loading a stray `.env` over the explicit config file; missing default profile on a fresh DB; `-threads 2` not bounding CPU (3.2 cores measured -> affinity cap, 1.8 cores); three PowerShell strict-mode bugs (preflight port checks, status folder sizes, rehearsal argument quoting).
- `scripts\windows\rehearsal.ps1` (APP_ENV=production, least-privilege DB role, Caddy internal TLS on https://localhost:8443 -> Waitress -> PostgreSQL queue -> native FFmpeg): **REHEARSAL OK**, smoke test 20/20. 30 s 1280x720 clip (19.94 MB): upload 1.61 s, processing 14.25 s, progress seen 17/47/73/99, output 3.23 MB. Peak working set: api 98 MB, worker 123 MB, ffmpeg 113 MB, caddy 49 MB, postgres 146 MB. 215 MB body -> 413 at the proxy; no ticket in the Caddy access log; HSTS/X-Frame-Options present, Server header absent. These are dev-machine numbers (8 logical CPUs), **not VPS measurements**.
- Browser check on the dev server: local sign-in, library, playback 854x480 with seek to 20 s, delete with confirmation, sign-out; no application console errors. Driven through page scripts because the browser pane was hidden.

#### Script verification matrix
| Script | What actually ran | Not verified |
| --- | --- | --- |
| preflight.ps1 | Real run, 35 checks, correct FAILs for this machine (C: 0.7 GB free, no PostgreSQL Windows service), `-AllowNetwork`, JSON report | Windows Server edition; elevated run |
| install-prerequisites.ps1 | Plan; `-Apply -SkipVenv` on `D:\VideoPortalDev\rehearsal` (folders + config template) | `-Download`, venv creation, any run on the VPS |
| setup-database.ps1 | Plan; `-Apply -SkipInitDb` against real PostgreSQL: role `NOSUPERUSER NOCREATEDB NOCREATEROLE`, limit 20; re-run changed nothing | Interactive password prompt; `init-db` step inside the script (run separately) |
| backup.ps1 / restore.ps1 | Real dump, verification, restore into a new DB, counts, drop of the drill DB; tamper and live-DB refusals (pytest) | `-OffsitePath`, `-IncludeStorage`, retention deletion of old files |
| rehearsal.ps1, smoke_test.py | Real end-to-end run | Run on the VPS |
| status.ps1, healthcheck.ps1 | Real runs (report missing services correctly) | With installed services |
| install-services.ps1, register-tasks.ps1 | Plan mode; refusal without elevation | **Actual service installation, virtual accounts, NTFS ACLs, WinSW XML, scheduled tasks — UNVERIFIED** |
| start/stop/restart-services.ps1 | Parse + refusal without elevation | With real services |
| Caddyfile | `caddy validate` -> Valid configuration; served the rehearsal with `tls internal` | Public certificate with a real domain |

#### Not done / unresolved
- **Nothing was deployed.** No VPS access was used. No firewall, Defender, RDP, service or scheduled-task change anywhere.
- Requirement risk: the brief asks for AWS/Azure/GCP, container-based transcoding and infrastructure from code; the VPS design departs from this (ADR-015). Needs instructor confirmation.
- Off-VPS backup destination not chosen; a same-disk dump is not a recovery plan.
- No domain yet: only Caddy's internal certificate was exercised; that is not valid public HTTPS.
- Graceful stop while encoding under WinSW, disk-full during encoding, and recovery after an OS reboot are untested.
- Native worker has no network/filesystem isolation (unlike the container).
- No self-service password reset; IP rate limit is per-process memory.
- Load test, p95, real failure drill, alert firing: later phases, on the VPS.

#### Dev-machine side effects of this work (not the VPS)
- Installed with owner approval: FFmpeg 9.0.1 and Caddy 2.11.9 via winget (user scope); PostgreSQL 16.4 portable binaries + data directory in `D:\VideoPortalDev` (no Windows service; started manually, loopback port 55432); earlier Terraform and Google Cloud SDK (now unused).
- `D:\VideoPortalDev` also holds the rehearsal root, pytest temp files and the PostgreSQL superuser password file. `.env` (gitignored) points the repo at that database.
- `caddy validate` created an empty `C:\VideoPortal\logs\caddy-access.log` (0 bytes); removal of `C:\VideoPortal` was blocked by the session's safety policy, so it is still there and can be deleted by hand.
- Drive C: had under 1 GB free during this work.

#### Cost
Software added: Waitress, Caddy, WinSW, FFmpeg, PostgreSQL, Python — all free. No paid service is required by this design. The VPS itself is already paid. A public certificate through Caddy is free but needs a domain name, which may cost money if the owner does not have one.

#### Git
Local commit only (owner's choice); **not pushed**. Commit identity is in `git log -1`. Previously uncommitted GCP Phase 07 files (`infra/`, GCP doc edits) are included in the same local history.

#### Next phase
`prompts/08-VPS-DEPLOY.md`: run preflight on the VPS, fix FAILs, install prerequisites, set up the database, rehearse, then install services — each system change with owner approval. Do not start it without a new request.

### 2026-11-17 — Phase 08 start: first preflight on the VPS (read-only) and script fixes
- Owner copied the Phase 07 archive (commit 6d88df9) to the VPS and ran `preflight.ps1 -AllowNetwork`. Reported result: **PASS=19 WARN=8 FAIL=5**. Nothing was installed or changed on the VPS.
- VPS facts as reported: Windows Server 2022 Standard build 20348, 3 logical processors, 4 GB RAM (1.9 GB free), C: 27.6 GB free, elevated session, ports 80/443/8000 free, DNS and outbound HTTPS working, Defender running.
- FAIL: Python is 3.11.9 (3.12+ required; `Path.is_junction` and the tested dependency set); no PostgreSQL service or client tools; no FFmpeg/ffprobe. WARN: Caddy, WinSW and Git missing; long paths disabled.
- **Security finding: Windows Firewall is disabled on all three profiles.** Not changed (owner decision pending). Until it is enabled or a provider-level firewall is confirmed, every listening port is reachable; PostgreSQL must be set to `listen_addresses = 'localhost'` immediately after installation. Enabling the firewall without an enabled RDP rule can lock the owner out.
- Defects in my Phase 07 scripts exposed by this run and fixed locally:
  - preflight printed "Firewall inbound 5432/8000: Not allowed from outside — PASS" while the firewall was off, which is wrong. It now reports the rules as not evaluated and adds the RDP port/rule state. The disabled-firewall branch could not be executed on the dev machine (its firewall is on): parse-checked only.
  - preflight and install-prerequisites took the first `python` on PATH. New `Find-Python` prefers an all-users 3.12+, then the `py` launcher, then PATH; install-prerequisites accepts `-Python`.
  - install-prerequisites `-Download` failed on FFmpeg: `Expand-Archive` in PowerShell 5.1 rejects files without a `.zip` extension. Now uses the .NET extractor and always removes its two temporary items.
- Newly verified on the dev machine (scratch root `D:\VideoPortalDev\rehearsal2`): `install-prerequisites.ps1 -Apply -Download` end to end — venv with Python 3.12.10, packages installed, `pip check` clean, FFmpeg 9.0.2 (published SHA-256 matched, libx264 present), Caddy 2.11.9, WinSW 2.12.0; a second run changed nothing. New `install-services.ps1 -WriteConfigOnly` wrote the three WinSW definitions and WinSW parsed each one (state NonExistent); no service was installed. Still unverified: actual service installation, virtual accounts, NTFS ACLs, scheduled tasks.
- Next on the VPS (owner actions, in order): decide the firewall question; install Python 3.12 for all users (side by side); install PostgreSQL 16 and restrict it to localhost; copy the updated archive to `C:\VideoPortal\app`; re-run preflight; then `install-prerequisites.ps1` (plan, then `-Apply -Download`).

### 2026-11-17 — Phase 08 in progress: prerequisites, database and rehearsal on the VPS (results reported by the owner)
All commands were run by the owner on the VPS (Windows Server 2022 Standard build 20348, 3 vCPU, 4 GB) from archive commit 5fe7f93 in `C:\VideoPortal\app`; outputs were pasted back and are summarised here. No service is installed yet; firewall, Defender and RDP untouched.
- Installed by the owner: Python 3.12.0 for all users (side by side with the existing 3.11.9) and **PostgreSQL 18.7** (not 16 as planned). `ALTER SYSTEM SET listen_addresses = 'localhost'` + service restart; `SHOW listen_addresses` -> `localhost`.
- Second preflight: **PASS=21 WARN=7 FAIL=2** (FAILs: ffmpeg/ffprobe not yet downloaded). Python 3.12.0 selected by `Find-Python`; `TCP 5432: PostgreSQL listens on loopback only`. The disabled-firewall branch added in 5fe7f93 ran correctly there: RDP port 3389, built-in Remote Desktop inbound rules enabled 3 of 3. Windows Firewall is still disabled on all profiles; the owner states the provider has its own firewall (its rules were not shown to me — unverified).
- `install-prerequisites.ps1 -Apply -Download`: PASS. Folders, venv, `No broken requirements found.`, config template; FFmpeg, Caddy and WinSW downloaded with the same SHA-256 values as on the dev machine (60F467…, F2EF05…, 05B82D…).
- `setup-database.ps1 -Apply` (interactive superuser password prompt): PASS on PostgreSQL 18.7. Created role `video_portal` and database `video_portal`, generated password stored in `C:\VideoPortal\config\.env`, `init-db` ran as the application role. Server `max_connections` is still 100 (suggestion printed, not applied).
- `rehearsal.ps1`: **REHEARSAL OK**, smoke test **22/22** (includes delete), through Caddy internal TLS on https://localhost:8443 -> Waitress -> PostgreSQL 18 queue -> native FFmpeg. First real VPS measurements: 30 s 1280x720 clip (19.85 MB) upload 0.39 s, **processing 17.08 s**, progress seen 20/39/64/84, output 3.23 MB. Peak working set: api 102 MB, worker 129 MB, ffmpeg 109 MB, caddy 68 MB, postgres 197 MB (about 605 MB together). **FFmpeg averaged 1.6 cores** of the 3 vCPUs under the 2-CPU cap. 215 MB body -> 413; no ticket in the Caddy access log; HSTS and X-Frame-Options present, Server header hidden.
- This is one clip, one run: not a load test, and not the ten reference clips.
- Leftovers on the VPS from the rehearsal: folder `C:\VideoPortal\rehearsal` (test clip, a 215 MB dummy file, logs, Caddy's internal CA) and one `rehearsal-…@example.com` account with a random password in the `users` table.
- Still not done: first real account, Caddyfile for the real site address (domain decision pending), service installation and NTFS ACLs (never executed anywhere), scheduled tasks, off-VPS backup, ten-clip run, public HTTPS.

### 2026-11-18 — Phase 08 in progress: services installed and running on the VPS (results reported by the owner)
Owner-run on the VPS; outputs pasted back. The public IP and account e-mail are deliberately not recorded in this file.
- First real account created with `flask create-user … --admin` (interactive hidden password prompt worked on a real console).
- No domain: `C:\VideoPortal\config\Caddyfile` generated from the template with the site address `https://<public IP>`, `tls internal` and `default_sni <public IP>`. The same shape was first checked on the dev machine (TLS handshake by IP without SNI succeeded). `caddy validate` on the VPS reported by the owner as done (output not pasted). **This is a self-signed certificate from Caddy's internal CA, not valid public HTTPS; browsers warn.**
- `install-services.ps1 -WriteConfigOnly`: three definitions written, WinSW parsed each, dependency resolved to `postgresql-x64-18`.
- **`install-services.ps1 -Apply`: PASS — first real execution of this script anywhere.** Root ACL locked down; WinSW reported all three services installed successfully. `Win32_Service.StartName`: `NT SERVICE\VideoPortal-API`, `NT SERVICE\VideoPortal-Worker`, `NT SERVICE\VideoPortal-Caddy` (virtual accounts, not LocalSystem).
- `start-services.ps1`: all three `OK … started`. `status.ps1`: four services Running (incl. `postgresql-x64-18`), `/health` HTTP 200 `database: ok`, queue `pending 0, dead 0`, C: 25.6 GB free; one attention item: no backup yet.
- **End-to-end through the installed services, running under the restricted virtual accounts**: `scripts/smoke_test.py --base-url https://<public IP> --insecure` with the real admin account -> **22/22 PASS**. Upload 0.39 s, processing 15.0 s for the 30 s 1280x720 clip, progress 24/48/76/99, output 3.23 MB, Range 206, tampered ticket 403, delete and sign-out verified. This exercises the NTFS grants for the API (storage write), the worker (storage, temporary folder, FFmpeg) and Caddy (config, data, logs). A first attempt failed at sign-in because the placeholder e-mail had not been replaced; no system fault.
- The smoke test ran on the VPS against its own public IP. **Reachability from the Internet (provider firewall for 80/443) is not yet verified.**
- Not verified yet: access from an outside machine; behaviour after a reboot (automatic start); service stop while encoding; scheduled tasks (`register-tasks.ps1` not run); backup on the VPS and any off-VPS copy; the ten reference clips; load test; failure drill. Windows Firewall remains disabled (owner relies on the provider firewall, whose rules I have not seen).

### 2026-11-18 — UI redesign and account management (owner request after first use on the VPS)
Owner feedback: the interface was plain, playback was hard to find after upload, only the CLI could create accounts, and the navigation was too thin.
- **Interface rewritten** (`app/templates/index.html`, `app/static/portal.css`, `app/static/portal.js`): space theme with an animated starfield canvas (twinkling stars, occasional meteor), drifting nebula glows, an orbiting "planet" hero, glass panels; one section visible at a time through hash routing. Sidebar grouped as Khám phá (Tổng quan), Video (Thư viện, Tải video lên), Tài khoản (Tài khoản của tôi, Quản lý người dùng for admins), Trợ giúp (Giới thiệu, Hướng dẫn). `prefers-reduced-motion` is respected; no inline styles or scripts, no external fonts or assets (CSP unchanged). Vanilla JS only, DOM built with `textContent` (no `innerHTML`).
- **Viewing fixed**: library is a card grid with real thumbnails; clicking a READY card opens a modal player straight away; the library polls every 2.5 s while anything is queued or processing and shows measured progress; the player renews the 2-minute playback link and resumes at the same position.
- **Upload**: drag-and-drop, real upload percentage (XMLHttpRequest progress), a five-step tracker that follows the video to READY on the same page and then offers "Xem ngay"; failed videos show the reason (for example longer than 30 seconds).
- **Accounts**: new `app/accounts.py` API (see API_CONTRACT) and an admin page to create accounts, reset passwords and disable/enable users; every user can change their own password. Backend enforces admin rights; no public sign-up; an admin cannot disable themselves.
- Tests: `RUN_DB_TESTS=1 pytest -q` -> **129 passed, 6 skipped** (Docker-only). Three new tests cover the account API (admin-only, validation, session revocation, self-disable refusal, absent under the Firebase provider, own password change). One existing new-file test was made independent of a dev `.env` that sets `FFPROBE_BIN`. `node --check app/static/portal.js` PASS.
- Browser verification on the dev server (real PostgreSQL, worker and FFmpeg): sign-in; library with thumbnail; modal player 854x480, 30 s, seek to 18 s; upload of a real MP4 through the page with tracker states create/send/queue/process (29 %, 66 %)/ready and the "Xem ngay" button; user creation, duplicate refusal, disable (sign-in then 401), self-disable button inactive; help pages; no application console errors. Narrow layout: no horizontal overflow at 375 px and the menu button appears, but the embedded browser froze CSS animations in its emulated mobile viewport, so the mobile look was **not visually confirmed**; entrance animations were changed to move-only so content stays readable if an animation never runs.
- Not verified: other browsers (only the embedded Chromium), real phones, the new interface on the VPS (not deployed there yet).

### 2026-11-20 — Deployment target changed to AWS (design and plan only)
Owner re-read the brief, has an AWS account, and chose **full migration to AWS** over a hybrid or database-only move. Work was done in `C:\VideoPortal-update-v3` on the VPS machine itself; the running VPS deployment in `C:\VideoPortal` was not touched (services `VideoPortal-API/Worker/Caddy` and `postgresql-x64-18` observed Running, read-only check).
- Brief re-checked: the PDF in the owner's Downloads folder has the same SHA-256 as `references/10_video_upload_and_processing_portal.pdf`. No PDF renderer on this machine; text was extracted with a small script and is partly garbled by the font encoding, so `docs/REQUIREMENTS.md` remains the readable checklist. The AWS row (ALB, ECS on Fargate API, RDS for PostgreSQL, S3, SQS, Lambda or Fargate workers, Cognito) was legible.
- Documents only: new `docs/AWS_ARCHITECTURE.md`; ADR-021; `docs/PHASES.md` phases 07–13 rewritten for AWS with the VPS phases archived; `AGENTS.md` deployment target; `docs/REQUIREMENTS.md` provider line; seven `prompts/*-AWS-*.md`; ARCHIVED banners on the two VPS prompts and on `docs/WINDOWS_VPS_ARCHITECTURE.md`.
- **No application code changed, no test run, no AWS resource created, no AWS call made.** Nothing here is evidence of a working AWS deployment.
- BLOCKED / open (owner input needed, see the table in `docs/AWS_ARCHITECTURE.md`): account type (owner answered "not sure"; run the read-only check commands in CloudShell and paste the output), region, domain name, where images are built, GitHub repository, budget.
- Tooling on this machine: AWS CLI, Docker, Terraform and Git are **not installed**. Phase 07 (adapters with stubs) needs none of them; phases 08+ need Terraform and AWS access somewhere (CloudShell is an option).
- Git: `C:\VideoPortal-update-v3` is not a git repository and `git` is not installed, so nothing was committed or pushed. Next command once Git is available and the owner names the remote: `git init`, or clone the existing repository and copy this tree over it.
- Not updated yet (still describe GCP or the VPS): `docs/SECURITY.md`, `docs/PIPELINE_RELIABILITY.md`, `docs/API_CONTRACT.md`, `docs/TEST_PLAN.md`, `docs/COST_MONITORING.md`, `README.md`. They are to be brought in line in the phase that changes the matching code.

#### Next phase
`prompts/07-AWS-ADAPTERS.md`. Do not start it without a new request.

### 2026-11-20 — Phase 07 (AWS adapters, local only): code and tests done; images not built
Owner asked to start Phase 07. Scope: `prompts/07-AWS-ADAPTERS.md`. **No AWS resource was created and no request was sent to AWS.** The running VPS deployment in `C:\VideoPortal` was not changed.

#### Completed files
- New: `app/storage_s3.py` (`S3Storage`: presigned POST upload, presigned GET pinned to VersionId, `head`, `download`, `write`, `delete` of every version, `old_objects`), `app/queue_sqs.py` (`SqsBroker`: `publish/receive/ack/dead_letter`, `extend`, `counts`), `app/auth_oidc.py` (Cognito ID-token verification through JWKS), `deploy/aws/Dockerfile` (+ `.dockerignore`; targets `api` and `worker`), `tests/test_aws_adapters.py`.
- Changed: `app/main.py` (settings `STORAGE_BACKEND`, `QUEUE_BACKEND`, `AWS_REGION`, `S3_BUCKET`, `SQS_*`, `COGNITO_*`; startup validation; CSP built from the backends in use; 503 `storage_unavailable`), `app/storage.py` (`upload_target`, `read_url`, `StorageUnavailable`, backend factory), `app/videos.py` (uses the two new storage methods; `/local-storage/*` is 404 with S3; honest `null` in `/api/monitor`), `app/pipeline.py` (`fetch_source`, queue heartbeat hook), `app/maintenance.py` (S3 cleanup), `app/queue_pg.py` + `app/worker_service.py` + `app/admin_cli.py` (`make_broker`), `app/auth.py` (Cognito provider), `app/serve.py` (`TRUSTED_PROXY`), `app/static/portal.js` (Cognito sign-in, S3 form upload), `requirements.txt` (`boto3==1.44.7`, `PyJWT[crypto]==2.15.1`).
- Docs: ADR-022; AWS sections appended to `docs/API_CONTRACT.md`, `docs/SECURITY.md`, `docs/PIPELINE_RELIABILITY.md`; container configuration and IAM needs in `docs/AWS_ARCHITECTURE.md`.

#### Commands and results (this machine: Windows Server 2022, Python 3.12.0, PostgreSQL 18.7 binaries, FFmpeg from `C:\VideoPortal\tools`)
- Test database: a **throwaway PostgreSQL cluster** created with `initdb` in the session's temp folder, loopback port 55432, random password, started as a normal process (no service). The production cluster on 5432 was not used. New project virtualenv `.venv` (gitignored) with `pip install -r requirements-dev.txt`; `pip check` -> `No broken requirements found.`
- Baseline before any change: `RUN_DB_TESTS=1 pytest -q` -> **128 passed, 7 skipped**.
- After the change: `RUN_DB_TESTS=1 pytest -q` -> **167 passed, 7 skipped** (the same 7: six need Docker, one needs `pg_dump` on PATH, deliberately not added so the backup script could not reach a real database). `tests/test_aws_adapters.py` alone -> 39 passed.
- What the 39 new tests are: (1) real boto3 clients with dummy keys under botocore `Stubber` — operation names and parameters are validated against the AWS service models, and presigned URLs/policies are really generated offline; (2) an in-memory fake S3 driving the full API flow and one real FFmpeg transcode against real PostgreSQL; (3) RSA-signed test tokens for the verifier (wrong audience/issuer/key/algorithm, expired, access token, unverified e-mail, unreachable key set).
- Page check in the embedded browser against a local server on port 8011 (local mode, test cluster): script loads with no console error; sign-in; upload of a 2 KB dummy file -> `POST /api/videos` 201, `PUT /local-storage/upload` 201, `complete` 202, tracker at "Xếp hàng". The S3 form branch was called once against a local URL: it sent a multipart POST and reported the failure cleanly. `node` is not installed, so there was no `node --check`.

#### Not verified / BLOCKED
- **Everything that needs AWS**: real S3 (presigned POST accepted, CORS, versioning), real SQS (redrive, visibility), real Cognito (`InitiateAuth` from the browser, token claims — in particular that `email_verified` arrives as a boolean), IAM permissions, RDS. Cause: no AWS access and out of scope for this phase. Next: Phase 08 preflight.
- **Container images not built** (`deploy/aws/Dockerfile` is unexecuted): Docker is not installed on this machine. Next command, on a machine with Docker: `docker build -f deploy/aws/Dockerfile --target worker -t video-portal-worker .` then the same with `--target api`.
- The Cognito sign-in branch and a successful S3 upload from the page were not exercised (no Cognito, no S3).
- `scripts/smoke_test.py` still uploads with PUT only; it needs an S3 branch before it can be used in Phase 09. The seed command still points seeded videos at local files (`local-seed/`), which a Fargate worker will not have; Phase 09 must upload the ten clips through the API or S3.
- Git: still no repository and no `git` on this machine; nothing committed or pushed.

#### Leftovers on this machine
`C:\VideoPortal-update-v3\.venv` (kept for the next phases). The temporary cluster, its data and the dev-server files are in the session temp folder; the cluster was stopped at the end of the session.

#### Next phase
`prompts/08-AWS-TERRAFORM-PREFLIGHT.md`. Needs from the owner first: account type (output of the read-only check commands), region, domain or not, where images are built, budget. Do not start it without a new request.

### 2026-11-20 — AWS account looked at (read-only, before Phase 08)
The owner signed in to the AWS Console in the embedded browser themselves; I only read pages. Nothing was created, changed or deleted, and no credential was typed by me.
- Personal account on the **Free plan**: account menu shows `Credits remaining $180 USD` and `Days remaining 182 days`. Not an AWS Academy Learner Lab.
- Console region: `ap-southeast-2` (Sydney).
- **CloudShell unavailable**: "Your account verification is in progress. This may take up to two days for new accounts." The read-only CLI checks could therefore not be run.
- RDS console (`ap-southeast-2`): 0 databases. ECS and Cognito consoles open; no user pool exists.
- IAM and EC2 consoles did not load in the embedded browser ("Unable to load content"), so the sign-in type (root or IAM user), IAM permissions and any running EC2 instances are **not verified**.
- Not verified: which services of the design the Free plan allows; whether resources can be created while verification is pending; anything in other regions.
- Recorded in `docs/AWS_ARCHITECTURE.md` (open-points table and "Tài khoản AWS đã kiểm tra"). Account ID, user name and e-mail are deliberately not written to the repository.
- Still open for Phase 08: domain or CloudFront, where images are built, GitHub repository, how Terraform gets credentials.
- **Region decided by the owner (2026-11-20): `ap-southeast-1` (Singapore).** Prices and service availability there are not looked up yet.
- **Owner has a domain name (2026-11-20):** HTTPS will be an ACM certificate on the ALB, no CloudFront. The owner later gave the site address `video.uploadmdm.id.vn`; its DNS is managed at the registrar (outside AWS).

### 2026-11-20 — Phase 08 (AWS preflight + Terraform): written and validated; `plan` BLOCKED
Owner asked to start Phase 08. Scope: `prompts/08-AWS-TERRAFORM-PREFLIGHT.md`. **Nothing was applied; no AWS resource exists; no AWS API was called with credentials.**

#### Completed files
`infra/aws/`: `versions.tf`, `variables.tf`, `network.tf`, `alb.tf`, `ecs.tf`, `data.tf`, `auth.tf`, `iam.tf`, `outputs.tf`, `terraform.tfvars.example`, `README.md`, `.terraform.lock.hcl`. 48 `resource` blocks and 7 `data` blocks (the exact planned resource count is unknown until `plan` runs). ADR-023; cost and domain notes in `docs/AWS_ARCHITECTURE.md`; `.tools/` added to `.gitignore`.

#### Commands and results
- Terraform 1.17.2 for Windows downloaded from `releases.hashicorp.com` (36.9 MB) into `.tools\terraform` (gitignored) with the owner's go-ahead; SHA-256 matched the published `SHA256SUMS` value (`2244b7a3…53024`). Not installed system-wide.
- `terraform fmt` -> no changes. `terraform init` -> `hashicorp/aws v6.73.0`, `hashicorp/random v3.9.1` (both "signed by HashiCorp"). `terraform validate` -> **`Success! The configuration is valid.`**
- `terraform plan -var domain_name=…` -> **failed as expected: no credentials** (`failed to refresh cached credentials, no EC2 IMDS role found`). No state file was created.
- Prices read from the public AWS Price List CSV for `ap-southeast-1` (publication dates 2026-11-11 to 2026-11-19): Fargate 0.05056 USD/vCPU-hour and 0.00553 USD/GB-hour; ALB 0.0252 USD/hour + 0.008 USD/LCU-hour; public IPv4 0.005 USD/hour; RDS `db.t4g.micro` Single-AZ PostgreSQL 0.025 USD/hour; gp3 0.138 USD/GB-month. Derived always-on figure for the design: about 0.147 USD/hour, about 110 USD/month, before S3/SQS/logs/secrets/ECR/backups/egress (not looked up). Itemised in `infra/aws/README.md`. An illustration, not a bill.

#### Found while working
- The VPS site is live on the same host name: `C:\VideoPortal\config\Caddyfile` serves `video.uploadmdm.id.vn`, and `https://video.uploadmdm.id.vn/health` answered 200 with a trusted certificate (the earlier entries in this file describe an IP-only self-signed setup; the owner changed that later). Pointing this name at AWS would take the VPS site off it. Read-only checks only; nothing on the VPS was changed.

#### BLOCKED / not verified
- **`terraform plan`**: needs AWS credentials. CloudShell is unavailable while the new account is being verified, and no CLI credentials exist on this machine. Next, in CloudShell once it opens: upload or clone the repository, then `cd infra/aws && terraform init && terraform plan -var domain_name=<name>`.
- Whether the Free plan allows ALB, RDS, Fargate, Cognito and the rest; whether credits cover them; `db.t4g.micro` and PostgreSQL 17 availability in the region; every IAM policy; Cognito schema settings (immutable e-mail). All of these can only fail or pass at `plan`/`apply`.
- Sign-in type of the account (root or IAM user) is still unknown.
- Git: still no repository and no `git`; nothing committed or pushed.

#### Open decisions for the owner before Phase 09
1. ~~Host name for the AWS deployment~~ **Decided by the owner (2026-11-20): reuse `video.uploadmdm.id.vn`**, i.e. a DNS cut-over from the VPS (a separate sub-domain had been recommended). Cut-over and rollback steps are planned in `docs/AWS_ARCHITECTURE.md`; nothing was changed in DNS. `infra/aws/terraform.tfvars` (gitignored) now holds the domain and region; `terraform validate` was not re-run because no `.tf` file changed.
2. GitHub repository (needed to build the images, since this machine has no Docker).
3. Budget: how many days the stack may stay up, given about 110 USD/month always-on against 180 USD of credit.

#### Git (2026-11-20, later the same day)
- MinGit 2.56.1 (38 MB) downloaded from the official Git for Windows release into `.tools\git` (gitignored) with the owner's go-ahead; SHA-256 matched the published value (`4a92850b…dafd`). Not installed system-wide.
- `git init -b main` in `C:\VideoPortal-update-v3` and `git add -A`: 186 files staged. Checked on the staged content: no `.env`, `*.tfvars`, state, `.terraform/`, `.tools/`, `.venv/` or key files; no AWS key, private key or GitHub token pattern; the AWS account ID and the VPS IP do not appear.
- **Committed locally, not pushed.** The owner approved using their sign-in e-mail as the commit author (repository-local `user.email`; it becomes public when pushed). First commit on `main` of this new local repository holds the whole tree including phases 07–08; identity in `git log -1`. Not pushed because the owner has not given the repository URL. The existing GitHub repository's history has not been seen: before the first push it must be fetched and this work placed on top of it, never force-pushed. Exact next commands once the URL is known: `git remote add origin <url>`, `git fetch origin`, then inspect `origin/main` before deciding how to join the histories.

#### Next phase
`prompts/09-AWS-DEPLOY.md`, only after `plan` has run cleanly and the owner approves each paid step.

### 2026-11-20 — Phase 09 started: deployment still BLOCKED; client-side tooling prepared and tested locally
Owner asked to continue with Phase 09 (`prompts/09-AWS-DEPLOY.md`). **Nothing was created on AWS; no `plan`, no `apply`, no image build.**

#### Why the AWS part did not start
- CloudShell re-checked in the owner's signed-in Console (read-only): `ap-southeast-1` shows "Unable to create the environment… System error"; `ap-southeast-2` still shows "Your account verification is in progress. This may take up to two days for new accounts." So there is still no command line with AWS credentials, and Terraform cannot plan.
- The owner showed the RDS "Create database" page: it opens, with the banner "Free plan has access to limited features and resources… The free plan limits the features and resources that are available for RDS and Aurora databases" and, with Aurora selected, "Full configuration" greyed out (only "Express configuration" selectable). So resources can apparently be created from the Console while verification is pending, but **the Free plan restricts RDS options**; whether a plain `db.t4g.micro` PostgreSQL instance in our own subnet group is allowed is not known yet. Nothing was created from that page.
- No GitHub repository URL yet, and no Docker here, so the two images cannot be built.

#### Done in this step (no AWS needed)
- `scripts/portal_client.py` (new, standard library only): shared HTTP client, sign-in for the `local` and `cognito` providers, upload by PUT or by S3 presigned form POST, `--resolve NAME=IP` support for testing a load balancer before its DNS record exists.
- `scripts/smoke_test.py`: now works with either provider and either storage; for S3 it also checks that a body larger than the signed size is refused; new check that a storage URL without its signature is refused; sign-out revocation is only asserted for local accounts (Cognito ID tokens cannot be revoked by the API).
- `scripts/seed_remote.py` (new): uploads the ten reference clips through the public API, waits for READY, compares each published duration with the manifest (±350 ms), shares the clips marked in the manifest with `--viewer`, and is repeatable (clips already in the owner's library are not uploaded again). This replaces `flask seed-db` for any deployment whose worker cannot read local seed files.
- `tests/test_scripts.py`: 5 tests (multipart body parsed back with Werkzeug, provider selection with a scripted fake client, URL tampering, manifest verification).

#### Commands and results (this machine, local mode, throwaway PostgreSQL cluster on 55432, real FFmpeg)
- `RUN_DB_TESTS=1 pytest -q` -> **172 passed, 7 skipped** (same 7 as before).
- Local API on port 8011 + local worker, then `scripts/seed_remote.py --viewer …` -> `SEED_RESULT {"clips": 10, "uploaded_now": 10, "already_present": 0, "failed": 0, "shared_with_viewer": 5, "total_seconds": 21.5}`; second run -> `uploaded_now: 0, already_present: 10`; wrong password -> `Sign-in failed`, exit 1.
- `scripts/smoke_test.py` against the same server -> **23/23 PASS**, `storage: local`, processing 3.08 s for a 3-second clip.
- These are local-mode runs on the development tree. They say nothing about AWS: the Cognito sign-in and S3 upload branches of the scripts were exercised only by the unit tests with a fake client.

#### AWS CLI (later the same day)
AWS CLI 2.41.2 (49 MB MSI from `awscli.amazonaws.com`, Authenticode signature Valid, signer "Amazon Web Services, Inc.") was unpacked with `msiexec /a` into `.tools\awscli` (gitignored) with the owner's go-ahead. It is **not installed system-wide** (not on PATH, no registry entries). No credentials are configured: the owner still has to run `aws login` and sign in in their own browser. No long-lived access key is to be created.

#### `aws login` attempt: region not supported for the project
- The owner ran `aws login --region ap-southeast-1` in the app's terminal and selected their session in the browser. The command never completed (no "Updated profile" line; `aws sts get-caller-identity` -> `NoCredentials`).
- Cause, read from the AWS sign-in page: **"You're trying to log into an AWS Region that's not supported for your project. Project Fresh Deploy is set up in ap-southeast-2. To fix this, use the following command: `aws login --region ap-southeast-2`."** The account is a "project" bound to Sydney. This also explains the different CloudShell error in `ap-southeast-1` ("System error").
- Consequence: the owner's choice of Singapore may not be possible with this account. Not verified: whether more regions can be enabled for the project (the AWS Settings page did not load in the embedded browser), and whether resources — not just sign-in — are restricted to the project's region. The Terraform default and the cost table are still for `ap-southeast-1` and must be redone if the region changes.
- No credentials were obtained, nothing was created.

#### Region changed to Sydney (owner decision, same day)
- Owner agreed to `ap-southeast-2`. `infra/aws/variables.tf` default, `terraform.tfvars` and the example now use it; `terraform fmt -check` clean, `terraform validate` -> `Success! The configuration is valid.`
- Sydney prices from the public AWS Price List (published 2026-11-11 to 2026-11-19): Fargate 0.04856 USD/vCPU-hour and 0.00532 USD/GB-hour; ALB 0.0252 USD/hour; public IPv4 0.005 USD/hour; RDS `db.t4g.micro` 0.025 USD/hour; gp3 0.138 USD/GB-month. Always-on illustration for the design: about 0.144 USD/hour, about 108 USD/month, before S3/SQS/logs/secrets/ECR/backups/egress. Table in `infra/aws/README.md`.
- `aws sts get-caller-identity --region ap-southeast-2` -> still `NoCredentials`: the owner has not yet re-run the sign-in for Sydney.

#### `terraform plan` PASS (same day, after the owner signed in for Sydney)
- The owner ran `aws login --region ap-southeast-2`, selected their session and confirmed the region prompt. `aws sts get-caller-identity` -> an assumed role named `AccountFullAccessRole` (not the root user). Credentials are short-lived and cached by the CLI under the Windows profile; no access key was created and none is in the repository.
- Read-only inventory of the account in `ap-southeast-2`: one default VPC; 0 EC2 instances, Elastic IPs, load balancers, ECS clusters, RDS instances/clusters, S3 buckets, SQS queues, Cognito pools, ECR repositories, secrets. AZs `2a`, `2b`, `2c` available.
- RDS: PostgreSQL 17.7–17.11 and 18.1–18.6 are offered; `db.t4g.micro` is orderable for 18.6 (gp3 included) and for 17.11. `db_engine_version` default changed from `17` to `18` because the project's own test runs used 18.7.
- **`terraform plan` -> `Plan: 54 to add, 0 to change, 0 to destroy.`** No errors or warnings. Key values: VPC `10.20.0.0/16`, public subnets in `2a`/`2b`, RDS `db.t4g.micro` engine `18`, 20 GB, not publicly accessible, single-AZ; both ECS services `desired_count = 0`; certificate for `video.uploadmdm.id.vn`. The saved plan and its text output were deleted afterwards (they contain the account ID); no state file exists.
- A successful plan does **not** show Free-plan or verification restrictions; those appear only at `apply`.

#### First AWS resource: ACM certificate (owner approved this single step)
- `terraform plan -target=aws_acm_certificate.site` -> `Plan: 1 to add`; `terraform apply` of that saved plan -> **`Apply complete! Resources: 1 added, 0 changed, 0 destroyed.`** (creation took 17 s; the "Applied changes may be incomplete" warning is the normal `-target` notice).
- Real resource: ACM certificate `9ee301d5-24ad-47d0-a6e0-92709ef7b99f` in `ap-southeast-2` for `video.uploadmdm.id.vn`, type `AMAZON_ISSUED`, not exportable, not in use. Status right after creation: **`PENDING_VALIDATION`**.
- DNS record the owner must add at the registrar (type CNAME): name `_27e3d71429cea22ebf345df1fcd8bbb9.video.uploadmdm.id.vn.` -> value `_62354f3b3e27523844f0abf7bf46c086.wzccmgtwzk.acm-validations.aws.` It does not touch the existing `video` A record that serves the VPS. At the time of writing the name does not resolve yet.
- `infra/aws/terraform.tfstate` now exists locally (gitignored; holds this one resource and no secret yet). It is the only record Terraform has of what it created: do not delete it.
- Cost: not looked up in the price list today; to the best of my knowledge public, non-exportable ACM certificates carry no charge. Nothing else exists in the account from this project.
- Not done: the other 53 resources, any image, any task.

#### Still BLOCKED for Phase 09
1. ~~Command-line credentials and `terraform plan`~~ done (see above). Credentials expire with the console session and must be renewed with `aws login`.
1b. Owner adds the certificate validation CNAME; then check `aws acm list-certificates` shows `ISSUED`.

#### DNS check after the owner added the validation record: validation record present, **`video` A record missing**
- Authoritative servers (`ns1`/`ns2.dotvndns.vn`) return the validation CNAME with the expected value. Public resolver 1.1.1.1 sees it; 8.8.8.8 not yet. Certificate still `PENDING_VALIDATION` at the time of the check (minutes after the record was added).
- **The same authoritative servers now return no record at all for `video.uploadmdm.id.vn` (A, CNAME, ANY -> only SOA).** Before this step the name resolved and served the VPS site. Most likely the existing `video` row was edited into the new record instead of a second row being added. This machine still reaches the site only through its own DNS cache; outside visitors lose the site as their caches expire (TTL was 3600 s).
- I did not and cannot change DNS: it is in the owner's registrar account. Action for the owner: add the `video` A record back with the VPS address, and keep the validation CNAME as a separate row. Nothing on the VPS or on AWS was changed by this.

#### DNS restored by the owner; certificate ISSUED
- After the owner re-added the row: both authoritative servers and the public resolvers 8.8.8.8 and 1.1.1.1 return the `video` A record (TTL 3600) and the validation CNAME. The A record equals this VPS's public address. With the local DNS cache cleared, `https://video.uploadmdm.id.vn/health` -> HTTP 200 `database: ok` from the VPS.
- **`aws acm list-certificates` -> `ISSUED`.** The certificate for `video.uploadmdm.id.vn` is ready for the load balancer. The validation CNAME must stay in DNS (ACM uses it for renewal).
- How long outside visitors could not resolve the name while the A record was missing was not measured.

#### GitHub repository known; **push deliberately held back** (owner is still editing the web interface)
- Owner gave the repository (`tuananhdinhhoang9-bit/code-loz-khoi`, public) and asked not to push yet.
- `git remote add origin …` and `git fetch origin` (read-only, no sign-in needed): the remote has **one commit, "Initial commit", containing only `README.md`**; no shared history with the local `main`, no workflows, no secret files. Nothing was pushed.
- When pushing is allowed: the two histories are unrelated and both have a `README.md`. Join them with a merge that keeps the remote commit (`git merge origin/main --allow-unrelated-histories`, resolve `README.md` in favour of the project's), then a normal `git push -u origin main`. No force-push.
- Prepared locally, not active until pushed/applied:
  - `infra/aws/github.tf`: GitHub OIDC provider and a role `video-portal-github-images` that only the `main` branch of that repository can assume, limited to pushing to the two ECR repositories. Controlled by `github_repository` (empty = nothing created). `terraform validate` OK; `terraform plan` -> **`Plan: 56 to add, 0 to change, 0 to destroy`** (53 remaining + these 3). Not applied.
  - `.github/workflows/ci.yml`: job `test` (PostgreSQL 18 service, FFmpeg, `pytest`) on every push and pull request; job `images` on `main` only, when the repository variable `AWS_ROLE_ARN` is set: build `api` and `worker` from `deploy/aws/Dockerfile`, push to ECR tagged with the commit SHA.
- **Unverified:** the workflow has never run and was not even syntax-checked (no YAML parser or `actionlint` here); the test suite has only ever run on Windows in this project, so Linux-only failures in CI are possible; the Docker build is still untested. The deploy step (new task definition, service update, rollback) belongs to Phase 12 and is not in the workflow.
- Because the repository is public, everything pushed becomes public, including the commit author e-mail and `docs/PROGRESS.md`.

### 2026-11-21 — Interface redesign (owner chose option A, "Professional SaaS"); local only, VPS not touched
Owner asked for three design directions first, picked A, and asked that backend, API, auth and video functions stay unchanged.
- Three standalone prototypes with sample data are kept in `design/prototypes/` (`a-saas.html`, `b-enterprise.html`, `c-media.html`); they are not part of the application.
- Rewritten: `app/templates/index.html`, `app/static/portal.css`; in `app/static/portal.js` the starfield was removed and the library/overview block replaced (same API calls). **No Python file, route or response changed.**
- What changed for the user: light neutral theme with thin borders (no gradients, no glass panels); sidebar with consistent SVG icons; overview shows a one-row summary, a four-lane "Dòng xử lý" board (waiting for upload / queued / processing / newly ready), failed videos with the reason, and videos shared with the user; library is a table with real thumbnails, duration, size and date, status and owner filters, a name search in the top bar, and a detail panel beside the table; upload page shows the five-step progress beside the form; the page rebuilds the table only when data changes, so thumbnails are not re-fetched on every poll.
- Duration in the list comes from the existing `GET /api/videos/{id}/thumbnail` response (`duration_ms`), so no API change was needed. Fonts are system fonts only: the page's CSP forbids external fonts and no font file was downloaded.
- Verified in the embedded browser against a local server (port 8011, local mode, throwaway PostgreSQL, real FFmpeg worker), desktop 1280 px and phone 375 px: no console errors; sign-in; overview; library with 11 videos and thumbnails; row selection and detail; player (320x180 clip played, `readyState 4`); a real MP4 uploaded through the form went create -> send -> queue -> process -> ready; search, "no match" row, status filter; grant and revoke permission; delete; user management page; account page; guide page; mobile menu; no horizontal overflow at 375 px.
- `RUN_DB_TESTS=1 pytest -q` -> **172 passed, 7 skipped** (unchanged).
- Not verified: other browsers than the embedded Chromium; real phones; the Cognito sign-in and S3 upload branches (no AWS deployment); the live site (the embedded browser blocks the live site's static files with `ERR_BLOCKED_BY_CLIENT`, so the live look was reviewed through an identical local copy). **Not deployed to the VPS** at that point (see the next entry).

### 2026-11-21 — New interface deployed to the VPS (owner request); push to GitHub waiting for the owner's sign-in
- **VPS, interface only.** The owner asked for the new version on the VPS. Only three files were replaced in `C:\VideoPortal\app`: `app\templates\index.html`, `app\static\portal.css`, `app\static\portal.js`. No Python file, dependency, configuration, database or other service was touched: the VPS backend is still the pre-AWS code, and the new script was checked to work with it (it falls back to PUT upload when the server sends no `upload_method`).
- Backup of the previous three files: `C:\VideoPortal\backups\ui-before-2026-11-21\` (sizes 17342 / 22704 / 31812 bytes). Files were overwritten in place, so their NTFS permissions are unchanged (`VideoPortal-API` still has read access).
- `Restart-Service VideoPortal-API` (needed because templates are cached): healthy again after 9 s; Worker, Caddy and PostgreSQL were not restarted. All four services Running.
- Checked over HTTPS on `video.uploadmdm.id.vn`: home page 200 with the new markup and without the old starfield; `portal.css` and `portal.js` byte-identical to the repository files; `/health` -> `database: ok`; `/api/videos` without a token -> 401; `/api/config` -> `auth_provider: local`, `max_upload_bytes: 200000000`; `api-error.log` still empty.
- Not verified: the live pages rendered in a browser after sign-in. The embedded browser still blocks the live site's static files (`ERR_BLOCKED_BY_CLIENT`), and I have no account on the live site. The same files were verified in a browser on the local copy (previous entry).
- Rollback: copy the three files back from the backup folder and `Restart-Service VideoPortal-API`.
- **GitHub push: BLOCKED on sign-in.** Before pushing, every commit was scanned (no key, token, AWS account ID, VPS address or ignored file in history). The remote's initial commit was joined with `git merge -s ours origin/main --allow-unrelated-histories` (remote commit kept as a parent, project tree kept, nothing overwritten). `git push -u origin main` then failed: `could not read Username for 'https://github.com': terminal prompts disabled` — this session cannot show the Git Credential Manager sign-in. Next command, run by the owner in a terminal so the sign-in window can open: `& "C:\VideoPortal-update-v3\.tools\git\cmd\git.exe" -C C:\VideoPortal-update-v3 push -u origin main`. Nothing is on GitHub yet beyond the original README commit.

### 2026-11-21 — Pushed to GitHub; first CI runs; one Linux-only failure fixed
- The owner ran the push and signed in. Verified: `git ls-remote origin refs/heads/main` equalled the local `main` (`2db91b9…`), 0 ahead / 0 behind. Later pushes from this session used the sign-in now stored on the machine; each was verified the same way.
- GitHub Actions, workflow `ci` (first time the test suite ran on Linux, with a PostgreSQL 18 service and distribution FFmpeg):
  - run 1 (`2db91b9`): **failure** in the test step. Job logs need a signed-in viewer, so the workflow was changed to publish failing test names as annotations (`8bd6d2d`).
  - run 2 (`8bd6d2d`): **`1 failed, 168 passed, 10 skipped`** — `tests/test_windows_vps.py::test_pg_queue_concurrent_receivers_never_share_a_message`, `assert (4 == 5)`.
  - Cause: `PgBroker.receive()` locked up to five rows and delivered the first, so a concurrent receiver could find every row locked and return nothing while messages were waiting. No message was ever delivered twice; the test also expected all five to be handed out within ten concurrent calls. Fix in `app/queue_pg.py`: lock exactly one row per attempt (exhausted messages are still marked dead in the same transaction, up to five per call).
  - Locally after the fix: the test passed 15 of 15 repeated runs; full suite **172 passed, 7 skipped**.
  - run 3 (`88b7857`): **success** — job `test` passed on Linux; job `images` skipped as designed (repository variable `AWS_ROLE_ARN` is not set yet). https://github.com/tuananhdinhhoang9-bit/code-loz-khoi/actions/runs/44785425103
- The VPS still runs the earlier `queue_pg.py`; with its single worker the old behaviour only meant an occasional empty poll. Not redeployed.
- Still not done in CI: image build (needs the AWS role), deploy and rollback (Phase 12).

### 2026-11-21 — Second interface redesign, "Media Studio" (owner brief); development only, **not deployed**
The owner found option A too plain and gave a concrete direction: charcoal sidebar `#111827`, content `#F5F6FA`, primary `#2563EB`, a colour per processing state, real thumbnails as the accent, 150–250 ms transitions, and five screens (signed-out intro, dashboard, library workspace, upload, video details). Constraints kept: no backend, API, database or FFmpeg change; no fake data; no private video exposed; no production deploy before approval.
- Changed: `app/templates/index.html`, `app/static/portal.css`, `app/static/portal.js` only. **No Python file changed.** The VPS still serves option A (deployed earlier the same day); `C:\VideoPortal\app` was not touched in this step.
- Signed out: the application shell is hidden entirely; one screen explains the product with the four real pipeline stages and the real limits (from `/api/config`), next to the sign-in form. No statistics, thumbnails or video markup exist in the DOM for a guest (checked: 0 such elements, and after sign-out the player has no `src`).
- Dashboard: pipeline card with four stage counters and the videos currently waiting or processing with measured progress; a dark metrics card; "Video gần đây" with real thumbnails where the newest video is shown double size; failed videos with the reason; videos shared with the user.
- Library: status tabs, owner filter (all / mine / shared), name search, **grid or list** (choice kept in `localStorage`), and a per-video action menu (open, share, delete — the last two only for the owner).
- Video details is now a page (`#watch`) instead of a side panel and modal: inline player first, then processing steps, metadata, sharing and delete. A video that is not READY shows its state and reason instead of a player.
- Upload: large drop zone, a card with the chosen file's name, size and type (with a warning for a wrong type or size), and two separately measured phases: bytes sent by the browser, then the FFmpeg percentage reported by the server.
- Verified in the embedded browser on the development server (port 8011, local mode, throwaway PostgreSQL, real FFmpeg worker) at 1440x900 and 375x812: no console errors; guest screen; sign-in; dashboard; library grid, list and menu; details for a READY video (player `readyState 4`, 320x180) and for a FAILED video; a real MP4 uploaded through the page, observed states `Đã gửi 95 KB` -> `Đang xếp hàng` -> `Đang kiểm tra file` -> `99%` -> `Hoàn tất`; delete; sign-out; no horizontal overflow at 375 px. Twelve screenshots are in `design/screenshots/media-studio/` (test clips and the throwaway dev account only).
- `RUN_DB_TESTS=1 pytest -q` -> **172 passed, 7 skipped**.
- Not verified: other browsers, real phones, keyboard-only use of the action menu beyond focus and Escape, the Cognito/S3 branches, and anything on the live site.

### 2026-11-21 — "Media Studio" interface deployed to the VPS (owner approved after seeing the screenshots)
- Deployed from commit `fb7b7a2` with a clean working tree. Again only `app\templates\index.html`, `app\static\portal.css`, `app\static\portal.js` were replaced in `C:\VideoPortal\app`; backend, configuration, database, Worker and Caddy untouched.
- Backup of the files that were live (option A): `C:\VideoPortal\backups\ui-before-media-studio-2026-11-21\`. The earlier backup of the original space-theme files is still in `ui-before-2026-11-21\`.
- `Restart-Service VideoPortal-API`: healthy again after 5 s; all four services Running.
- Checked over HTTPS on `video.uploadmdm.id.vn`: home 200 with the guest intro and the `#watch` page in the markup; `portal.css` and `portal.js` byte-identical to the repository; `/health` -> `database: ok`; `/api/videos` without a token -> 401; `/api/config` -> local provider, 200 MB limit (so the page shows 200 MB there, 50 MB in development); `api-error.log` empty and no 5xx in the last API log lines.
- Not verified: the live pages in a real browser after sign-in (no account on the live site; the embedded browser blocks the live static files). The owner is asked to hard-refresh and try sign-in, playback and one upload.
- Rollback: copy the three files back from the backup folder of the wanted version and `Restart-Service VideoPortal-API`.

### 2026-11-21 — Live VPS site tested end to end with an administrator account (owner request)
The owner supplied the administrator password in chat and asked for the functions and the database to be checked. All signed-in checks were made against the application on this machine at `http://127.0.0.1:8000` (Waitress, behind which the public site runs); the password is not recorded anywhere in the repository.
- Database of the live site (read-only queries through the app's own models): **PostgreSQL 18.7 on the VPS itself**, database `video_portal`, `listen_addresses = localhost`, 8.6 MB. Before the tests: 3 users (2 administrators, 1 disabled rehearsal account), 1 video (READY) with its job, 2 output objects, 1 published outbox event, 0 queue messages, 0 dead messages, 0 permissions. Storage: 3 media files, 0.9 MB. Backends: local storage, PostgreSQL queue, local accounts. **No database backup file exists in `C:\VideoPortal\backups`.**
- `scripts/smoke_test.py --base-url http://127.0.0.1:8000` with the administrator account: **23/23 PASS** — health, 401 without a token, wrong password refused, sign-in, upload slot, private upload, no overwrite, job queued, playback refused before READY, worker finished READY in 5.17 s (3-second clip), playback URL, Range 206, full MP4, JPEG thumbnail, tampered and unsigned storage URLs refused (403), delete, sign-out, token revoked.
- Interface in the embedded browser on the same address (static files load there): guest screen shows the VPS limit (200 MB); sign-in as administrator; dashboard counts and a real thumbnail; details page played a 320x180 clip (`readyState 4`, duration 0:03); grant and revoke of a view permission; user-management page listed 3 accounts; delete through the page; sign-out left no video markup; no console errors.
- Test data: two clips named "Smoke test clip" were uploaded by these checks and both were deleted. Afterwards the database was back to 1 video, 1 job, 0 permissions, 0 queue messages.
- **AWS state at the same time:** the CLI sign-in had expired (`aws sts get-caller-identity` failed while refreshing the token), so the account could not be queried; `terraform state list` shows the only resource this project has created is `aws_acm_certificate.site`. **There is no AWS database, bucket, queue, user pool, load balancer or ECS service.** The live site does not use AWS at all.
- Not verified: the public HTTPS path after sign-in (signed-in checks used the loopback address), other browsers, real phones.

### 2026-11-21 — Third interface redesign, "Vibrant Media Studio" (owner brief V3); development only, **not deployed**
The owner judged the live "Media Studio" interface too monochrome and too close to an ordinary admin dashboard, and gave a new brief: Deep Ink `#211638`, Electric Violet `#6D28D9`, Vibrant Pink `#EC4899`, Cyan `#06B6D4`, Energetic Orange `#F97316`, Soft Lavender `#FAF7FF`; colour on meaningful areas; three controlled gradients; a real change of layout and hierarchy, not a recolour. Constraints kept: no backend, API, database, authentication, authorization, upload or FFmpeg change; real data only; nothing private or statistical for a guest; no invented processing percentage; no production deploy.
- Changed: `app/templates/index.html`, `app/static/portal.css` (rewritten), `app/static/portal.js` (small additions). **No Python file changed.** `C:\VideoPortal` was not touched; the VPS still serves "Media Studio".
- Gradient roles: Violet→Pink for the hero, the dashboard banner, the selected navigation item and transcoding progress; Cyan→Violet for everything about uploading (drop zones, upload buttons, bytes-sent progress); Pink→Orange for small accents (brand mark, heading underline, section markers). Where white text sits on a gradient the darker stops `#0E7490`/`#5B21B6`/`#DB2777` are used; solid cyan and orange tiles carry Deep Ink text.
- Signed out: full-width gradient hero with a slanted lower edge, the headline "Tải lên. Xử lý. Chia sẻ.", an upload button (it moves focus to the sign-in form and says sign-in is needed), a layered CSS illustration of the pipeline (screen, four stages, three chips with the real formats and output), and the sign-in card overlapping the hero edge; below it the four stages as coloured cards and the real limits from `/api/config`. Checked for a guest: application shell `display: none`, 0 thumbnail/video elements, all counters empty, player without `src` — also again after sign-out (counters are now cleared on sign-out).
- Dashboard: gradient banner whose sentence is built from the real counts, with a "Tải nhanh" drop zone (drop or click puts the file into the upload form and opens the upload page); bento grid of unequal tiles — Deep Ink total with a ring drawn to the real ready/total ratio, pipeline timeline with four coloured stage nodes and the list of running videos, cyan ready tile, orange waiting tile, pink failed tile; recent videos with the newest double size; failed and shared lists.
- Upload: large tinted drop zone with a drag-over state, file card with a type badge, a Deep Ink panel explaining the two phases (replaced by the tracker once an upload starts), two differently coloured measured bars, and a result block ("Video đã sẵn sàng" with "Xem ngay", or the failure reason). No video preview of the chosen file: the page's CSP does not allow `blob:` media, and the policy was not loosened.
- Library: pill filters coloured by the state they select, cards with hover elevation, image zoom and a play mark, coloured state thumbnails for videos without an image, list view, and an SVG-illustrated empty state. Details page: player in a gradient frame. Guide page in two columns with numbered steps.
- Motion: 150–300 ms transitions, hover elevation, slow hero/banner gradient drift, staggered entrance of the top-level blocks of each view, bars driven by measured values. With `prefers-reduced-motion` all animations are off and the "no measurement yet" bar becomes a full, dimmed bar so it cannot be read as a percentage.
- Fixed on the way (also present before this redesign): choosing a section while the page was scrolled to the top let the browser scroll to the section's anchor and hide its first rows under the sticky header; `.view { scroll-margin-top }` prevents it (`scrollY` 0 after sign-in and after opening a video).
- Verified in the embedded browser on the development server (port 8011, local mode, throwaway PostgreSQL, real FFmpeg worker) at 1440x900, 768x1024 and 390x844: no console errors; no horizontal overflow at any of the three widths; guest page; sign-in; dashboard; library grid and list, action menu (opens, Escape closes); details of a READY video (plays) and of a FAILED video; two real MP4 uploads through the page ending in "Video đã sẵn sàng" and "Xem ngay" opening the player; a simulated drop on "Tải nhanh" (file card with name, size, `MP4` badge, title pre-filled); delete; sign-out. Nineteen screenshots are in `design/screenshots/vibrant/` (test clips and the throwaway dev account only); the earlier design is in `design/screenshots/media-studio/` for comparison.
- `RUN_DB_TESTS=1 pytest -q` -> **172 passed, 7 skipped** (the suite checks the served HTML and the API; it does not execute the page's JavaScript — that was covered by the browser checks above).
- Not verified: the animations themselves (the embedded browser reports `prefers-reduced-motion: reduce`, so only the reduced-motion rendering was seen); a real mouse drag of a file onto the drop zones (events were simulated); other browsers and real phones; contrast measured with a tool (ratios were calculated by hand for the text/background pairs); the Cognito/S3 branches; anything on the live site.
- Self-critique: the pipeline tile is half empty while nothing is processing; the "Giới thiệu", "Tài khoản của tôi" and "Quản lý người dùng" pages are still plain cards with an accent stripe; the test clips are colour bars, so the screenshots look louder than real footage would.

### 2026-11-21 — "Vibrant Media Studio" interface deployed to the VPS (owner approved after seeing the screenshots)
- Deployed from commit `e4d83ba` with a clean working tree. Only `templates\index.html`, `static\portal.css`, `static\portal.js` were replaced in `C:\VideoPortal\app\app`; backend, configuration, database, Worker and Caddy untouched.
- Backup of the files that were live ("Media Studio"): `C:\VideoPortal\backups\ui-before-vibrant-2026-11-21\` (three files, hashes equal to the live ones before the copy). Earlier backups `ui-before-media-studio-2026-11-21\` and `ui-before-2026-11-21\` are still there.
- `Restart-Service VideoPortal-API`: `/health` answered 200 again after 3 s; API, Worker, Caddy and PostgreSQL services all Running.
- Checked over HTTPS on `video.uploadmdm.id.vn`: home 200 with the new hero and the quick-drop zone in the markup; `portal.css` and `portal.js` byte-identical to the repository; `/health` -> `database: ok`; `/api/videos` without a token -> 401; `/api/config` -> local provider, 200 MB limit; Content-Security-Policy header unchanged; `api-error.log` still empty.
- Guest page of the live application in the embedded browser (`http://127.0.0.1:8000`, where static files load): hero, illustration and sign-in card render, the limit shows `200 MB, 30 giây`, no console errors, no horizontal overflow at 1440 px, 0 thumbnail/video elements.
- Not verified: the live pages after sign-in (no account of mine on the live site; the administrator password was not reused), the public address in a real browser, phones. The owner is asked to hard-refresh (Ctrl+F5) and try sign-in, one upload and playback.
- Rollback: copy the three files back from `ui-before-vibrant-2026-11-21\app\` into `C:\VideoPortal\app\app\` and `Restart-Service VideoPortal-API`.

### 2026-11-21 — Two deployment branches pushed to GitHub: `vps` and `aws` (owner request)
The owner asked for two editions on GitHub, one for the VPS and one "for the database", and confirmed that the second means the AWS edition and that the split should be two branches.
- `main` (`60f6204`): README now lists the two branches and no longer claims the VPS is not installed; `infra/aws/README.md` status corrected (the ACM certificate is the one applied resource; plan is 56 to add).
- **`vps` (`2c35b23`)**, cut from `main`: README rewritten for the Windows Server edition; AWS-only material removed (`infra/aws/`, `deploy/aws/`, `docs/AWS_ARCHITECTURE.md`, seven AWS prompts — 23 tracked files); CI reduced to the test job; a branch note in `AGENTS.md`.
- **`aws` (`01037b5`)**, cut from `main`: README rewritten for the AWS edition, stating plainly that nothing is deployed; VPS-only material removed (`scripts/windows/`, `deploy/windows/`, six `docs/WINDOWS_VPS_*.md`, two VPS prompts — 23 tracked files); a branch note in `AGENTS.md`.
- `app/`, `worker/` and `tests/` are identical on all three branches (`git diff main vps -- app worker tests` and the same for `aws`: empty). The application chooses its backends by configuration, so the editions differ only in deployment material and README. Rule written in the READMEs: change code on `main`, then merge into `vps` and `aws`.
- `RUN_DB_TESTS=1 pytest -q` on `vps`: **172 passed, 7 skipped**; on `aws`: **172 passed, 7 skipped** (Windows development machine, PostgreSQL 18, real FFmpeg).
- Before pushing: the lines added by these commits were scanned for keys, tokens, passwords, 12-digit account IDs, public IP addresses, signed URLs and e-mail addresses (only the loopback address `127.0.0.1` matched); no `.env`, `*.tfstate` or `*.tfvars` is tracked on any branch. The gitignored `infra/aws/terraform.tfstate` and `terraform.tfvars` are still on disk after the branch switches.
- Pushed with a normal `git push origin main vps aws`; `git ls-remote --heads origin` equals the three local SHAs.
- Found while writing the `vps` README: **the backend running on the VPS matches no commit in this repository.** It was installed before the AWS adapters were added; ten of its Python files in `app/` differ from `main` and three adapter modules are absent there. Only the three interface files on the server are current. Reinstalling the backend on the VPS from branch `vps` has not been done and was not requested.
- Not verified: the GitHub Actions runs triggered by these pushes (not finished when this was written); installing either branch from a fresh clone; the Docker image build; anything on AWS.

### 2026-11-21 — VPS backend updated to branch `vps` (owner chose "Cập nhật VPS")
The server folder `C:\VideoPortal\app` now holds exactly the tracked files of branch `vps` at `2c35b23` (203 files, compared by content ignoring line endings: 0 differences). `C:\VideoPortal\app\DEPLOYED_COMMIT.txt` records the branch and commit, so the running build can be identified next time.
- Before touching anything: 25 files on the server differed and 43 were missing (13 in `app/`: ten changed modules plus `auth_oidc.py`, `queue_sqs.py`, `storage_s3.py`; the rest are scripts, tests, docs, prompts and screenshots). `app/models.py` is unchanged, so there is **no schema change** and no migration.
- Dependencies: nothing installed. `PyJWT` 2.15.1 and `cryptography` were already in the server's virtualenv. `boto3` is listed in `requirements.txt` but is **not installed on the VPS**; it is imported only when `STORAGE_BACKEND=s3` or `QUEUE_BACKEND=sqs`, which the VPS does not use. The server's `.env` was not changed (no new variable is required in local mode).
- Pre-flight, read-only: the new code was run from a staging folder with the server's own Python and `.env` (Flask test client): `/health` 200 `database: ok`, `/api/config` local provider and 200 MB, `/api/videos` 401, page 200; backends resolved to `local` / `local` / `postgres`. The database held 1 video and 1 job, both READY; queue 0 pending, 0 dead; outbox empty — nothing in flight.
- Backups: the whole code folder as it was -> `C:\VideoPortal\backups\backend-before-vps-branch-2026-11-21\app\` (160 files; `changed-files.txt` beside it lists what was replaced or added); database -> `C:\VideoPortal\backups\videoportal-20261121-042339.dump` made by `scripts\windows\backup.ps1` (9 tables, `pg_restore --list` verified, `.sha256` beside it). Both are on the same disk as the data; no off-server copy was made.
- Swap: `Stop-Service` Worker then API, copy the 68 files, delete `__pycache__`, start API then Worker. `/health` answered 200 again 10 s after the stop began; Caddy and PostgreSQL were not touched.
- After the swap, over HTTPS on `video.uploadmdm.id.vn`: `/health` 200 `database: ok`; home 200 with the current interface; `/api/config` and `/api/auth/config` -> local provider; `/api/videos` and `/api/monitor` without a token -> 401; `/local-storage/read` with a bogus ticket -> 403; `portal.js` 200. `worker.log` shows `worker_stopped` then `worker_started`; `api.log` has no WARNING/ERROR line since the restart; `api-error.log`, `worker-error.log` and both service `.err.log` files are still empty; both Python processes kept the same PIDs when checked again (no restart loop); `flask system-status` -> queue 0 pending, 0 dead.
- One visible change: the Content-Security-Policy header no longer lists `https://identitytoolkit.googleapis.com` in `connect-src`, because the new code adds it only when `AUTH_PROVIDER=firebase` and the VPS uses local accounts.
- **Not verified: anything after sign-in on the live site with the new backend** — sign-in itself, an upload, the FFmpeg job, playback, sharing, delete. No account of mine exists on the live site and the administrator password was not used. The same code passes `RUN_DB_TESTS=1 pytest -q` (172 passed, 7 skipped) on the development machine, which is not the same as a live upload. Next step: the owner uploads one short clip on the site, or approves a temporary test account for `scripts/smoke_test.py`.
- Rollback: `Stop-Service VideoPortal-Worker, VideoPortal-API`; `robocopy C:\VideoPortal\backups\backend-before-vps-branch-2026-11-21\app C:\VideoPortal\app /E`; delete `auth_oidc.py`, `queue_sqs.py`, `storage_s3.py` from `C:\VideoPortal\app\app`; start the two services. The database needs no restore because the schema did not change.

### 2026-11-21 — Deployment target changed from AWS to Azure (owner decision) — design and plan only
The owner asked whether AWS could be replaced by Azure, then decided: drop AWS, do Azure only. This entry is documentation; **no application code changed, no Azure account was looked at, no cloud resource was created, changed or deleted.**
- Brief re-read for the Azure wording. The PDF could not be rendered on this machine (no `pdftoppm`), so its text was extracted with a small standard-library script. Azure row: "App Service API; Azure Database for PostgreSQL; Blob Storage; Service Bus; Functions or Container Apps workers. Use bounded Container Apps Jobs for conversion"; identity: "Entra External ID on Azure … or justify another OIDC provider"; secrets in Key Vault.
- `docs/DECISIONS.md`: **ADR-024** (Azure replaces AWS; mapping, costs of the change, review triggers).
- `docs/AZURE_ARCHITECTURE.md` (new): diagram, mapping from the existing code, eleven design choices with trade-offs, a table of facts checked against Microsoft Learn on 2026-11-21 with the page for each, a list of points that could **not** be confirmed from the pages read, open points for the owner, a rough cost table, failure domains.
- Main differences from the AWS design: conversion is an event-driven Container Apps Job (one job per execution) instead of an always-on worker, with a scheduled maintenance job and outbox relay from the API after commit; the database has no public address (VNet private access); upload is a `PUT` with a user delegation SAS, which cannot limit size, so the limit is enforced at `complete`; sign-in is a redirect (authorization code + PKCE) to Entra External ID.
- Prices: read from the Azure Retail Prices API on 2026-11-21 for `southeastasia` (PostgreSQL B1ms 0.026 USD/h, PostgreSQL storage 0.138 USD/GiB-month, Container Registry Basic 0.1666 USD/day, private DNS zone 0.50 USD/month, Container Apps 0.000034 USD/vCPU-s and 0.000004 USD/GiB-s active, Service Bus Basic 0.05 USD per million operations, Blob Hot LRS 0.02 USD/GB-month). Fixed part of the estimate: about 29 USD/month. This is arithmetic on list prices with assumed sizes and durations, not a bill; one meter in the list ("Environment Management Hour", 0.10 USD/h) is unexplained and must be understood before any `apply`.
- `AGENTS.md` (deployment target section), `docs/PHASES.md` (phases 07–13 retargeted, AWS phases archived, three open requirement risks), `docs/REQUIREMENTS.md` (provider line), `README.md` (branch table and target section), seven new `prompts/*-AZURE-*.md`; ARCHIVED banners on the seven AWS prompts, `docs/AWS_ARCHITECTURE.md` and `infra/aws/README.md`; the VPS prompt banners now point to the Azure prompts.
- Left as they are on purpose: the AWS adapter modules, their tests and `boto3` (removed in Azure Phase 07 when replacements pass tests); `infra/aws/` and `deploy/aws/` (reference; the Dockerfile is the starting point for the Azure images); the `images` job in `.github/workflows/ci.yml` (its condition skips it while the repository variable `AWS_ROLE_ARN` is unset; replaced in Phase 12); the ACM certificate on AWS (free, still exists, deleting it needs the owner's AWS sign-in); the `aws` branch on GitHub (frozen, not deleted).
- Branches: `main` `75afe78` carries the change. `aws` `14f296f` got a "frozen" notice in its README and AGENTS note; `vps` `6367eb5` got a note that the cloud target is now Azure. `main` was not merged into either for this documentation-only change (`app/`, `worker/`, `tests/` are still identical on all three). Remote heads equal the local SHAs.
- Checks: documentation only, so no application test was run for this change. `git diff --check` clean; changed files re-read for consistency.
- Not verified / BLOCKED: everything on Azure. Next step that needs no account: Phase 07 (`prompts/07-AZURE-ADAPTERS.md`). Phase 08 is BLOCKED until the owner has an Azure subscription and signs in themselves (`az login`; the Azure CLI is not installed on this machine).

### 2026-11-21 — Azure Phase 07: adapters in code, local only — PASS for code and local tests; nothing run against Azure
Scope: `prompts/07-AZURE-ADAPTERS.md`. **No Azure resource was created and no call to Azure was made.** Design choices: ADR-025.
- New: `app/storage_blob.py` (`BlobStorage`: user delegation SAS for upload and for version-pinned playback, `head`, `write`, `download`, `delete` of every version, `old_objects`), `app/queue_servicebus.py` (`ServiceBusBroker`: `publish/receive/ack/dead_letter/extend/close`), `deploy/azure/Dockerfile` (+ `.dockerignore`), `tests/test_azure_adapters.py`.
- Changed: `app/main.py` (Azure and OIDC settings, validation, CSP), `app/auth_oidc.py` and `app/auth.py` (generic OIDC: explicit issuer/JWKS/authorize/token URLs, e-mail claim, `roles` claim), `app/storage.py` (`upload_headers`, `blob_origin`), `app/queue_pg.py` (`make_broker`), `app/videos.py` (relay after `complete` with Service Bus; an oversized blob is deleted at `complete`), `app/worker_service.py` (`--once`), `app/admin_cli.py` (`maintain`, `system-status`), `app/pipeline.py` (`DISPATCH_SECONDS` from the environment, default still 30), `app/static/portal.js` and `app/templates/index.html` (authorization code + PKCE sign-in, one `PUT` upload path), `scripts/portal_client.py`, `scripts/smoke_test.py`, `requirements.txt` (three Azure SDK packages replace `boto3`), `.env.example`, `.github/workflows/ci.yml` (AWS `images` job removed; an Azure deploy job is Phase 12).
- Removed from `main` (still on branch `aws`): `app/storage_s3.py`, `app/queue_sqs.py`, `tests/test_aws_adapters.py`, `deploy/aws/`.
- SDK versions installed in the development virtualenv and pinned: `azure-storage-blob` 12.31.1, `azure-servicebus` 7.15.0, `azure-identity` 1.27.0 (`pip check`: no broken requirements). The method signatures the code relies on were read from the installed packages, not from memory.
- Tests — `RUN_DB_TESTS=1 pytest -q` (PostgreSQL 18, real FFmpeg, Windows): **181 passed, 7 skipped** (skips: 6 need the Docker worker image, 1 needs PostgreSQL client tools on PATH). Without a database: 84 passed, 104 skipped. What the new tests cover and how:
  - SAS tokens are generated for real, offline, with a fake delegation key: create-only (`sp=c`, `sr=b`) for upload, read on a version (`sp=r`, `sr=bv`, `versionid`, `rsct`) for playback, HTTPS only, 120 s, key value never in the response; the delegation key is cached and renewed before expiry.
  - The real `BlobServiceClient` with a recording fake transport: the HTTP requests for `head`, `write`, `delete` (current blob, list with `include=versions`, delete by `versionid`) and `old_objects` are asserted, and real response parsing gives size, type and version ID. Download is covered only by the in-memory fake.
  - Service Bus against an in-memory fake only (AMQP cannot be stubbed like HTTP): publish with `message_id` = event ID, peek-lock redelivery, failures become `QueueError` and reopen the link, malformed message dead-lettered, lock renewed only when due. A separate test binds every SDK call the code makes to the installed SDK's signatures.
  - OIDC: RS256 only, issuer, audience, expiry, e-mail claim, `email_verified`, admin role, key-set outage -> 503, configuration and CSP validation (including injection attempts in URLs and names).
  - Full flows with PostgreSQL: upload -> `complete` -> playback -> delete on fake Blob Storage; oversized blob rejected and deleted at `complete`; storage outage -> 503; queue outage after commit -> 202 and the `maintain` command publishes later; local mode does not relay from the API; one `--once` run transcodes the recorded blob version with real FFmpeg, renews the lock, acks, and a redelivered message is a no-op.
- Browser checks on the development machine (embedded browser, throwaway PostgreSQL, real FFmpeg worker):
  - Local mode (`http://localhost:8011`): sign-in through the refactored login path; a real 4,680-byte MP4 uploaded through the page — one `PUT /local-storage/upload` with the server-provided `Content-Type` header, HTTP 201 — and processed to "Video đã sẵn sàng"; no console errors.
  - OIDC mode (`http://127.0.0.1:8013`) against a **fake OIDC provider written for this check** (scratch script, not in the repository, not Entra): the e-mail and password fields are hidden and disabled; "Đăng nhập" redirects with `response_type=code`, `code_challenge_method=S256`, `state`, `nonce`, scope `openid profile email`; on return the page exchanged the code with the correct PKCE verifier, the API verified the RS256 ID token through a real JWKS fetch, the user was signed in as the lower-cased e-mail with the admin role, the code was removed from the address bar and the saved values from `sessionStorage`; sign-out went through the provider's logout URL and back; a callback with a wrong `state` and a callback with `error=` both showed "Đăng nhập chưa hoàn tất" without calling the token endpoint; an unrelated query string was ignored; no console errors. The harness ran the app in TESTING mode because real configuration refuses `http` OIDC URLs.
- Local mode starts and serves with the Azure packages made unimportable (checked by blocking the imports), so the VPS does not need them installed.
- **Not verified — needs real Azure (Phase 08/09):** every call to Blob Storage and Service Bus; that a create-only SAS cannot overwrite an existing blob; that a browser `PUT` with these headers passes the storage account's CORS rules and sets the blob's content type; deleting versions; lock renewal and dead-lettering on a real queue; KEDA starting a job execution and the 300 s dispatch window being long enough; Entra External ID itself (issuer and endpoint URLs, claim names, verified e-mail, app roles, logout); role assignments; the Dockerfile (never built: no Docker on this machine). Not run for this change: `scripts/smoke_test.py` and `scripts/seed_remote.py` against a server (their shared helpers are unit-tested).
- Branch `vps` is merged with this change (see the commit after this one); the code running on the VPS itself is still branch `vps` at `2c35b23` and was not touched.
- Next: Phase 08 (`prompts/08-AZURE-TERRAFORM-PREFLIGHT.md`) — BLOCKED until the owner has an Azure subscription and signs in themselves.
2. Confirmation that the Free plan permits the RDS, ALB, Fargate and Cognito resources in `infra/aws/`.
3. GitHub repository URL -> push, then a workflow to build and push the two images.
4. Owner approval of the first paid `apply`, with the plan output and the cost table in front of them.

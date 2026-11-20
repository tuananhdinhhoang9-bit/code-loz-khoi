# API contract (minimal)

API JSON responses include `request_id` or `job_id` for troubleshooting. Use auth checks in **server** even if browser hides controls.

| HTTP | Path | Principal / behavior |
| --- | --- | --- |
| `GET` | `/` | Jinja portal HTML; login redirect when needed |
| `GET` | `/api/videos` | Auth user sees owned + permitted videos only |
| `POST` | `/api/videos` | Owner creates pending video + receives scoped upload Signed URL |
| `POST` | `/api/videos/{id}/complete` | Owner; HEAD/check object existence, size, content-type and GCS generation, then transactional job+outbox |
| `GET` | `/api/videos/{id}` | Owner/permitted viewer; metadata and status |
| `GET` | `/api/videos/{id}/status` | Owner/permitted viewer; queued/processing/retrying/ready/failed; no guessed progress percentage |
| `POST` | `/api/videos/{id}/permissions` | Owner grants/revokes exact Viewer UID |
| `GET` | `/api/videos/{id}/playback` | Authorize caller AND READY object; return short-lived URL |
| `GET` | `/api/videos/{id}/thumbnail` | Same authorization; short-lived signed URL, no public objects |
| `GET` | `/api/monitor` | Demo admin only; sanitized aggregate stats and error codes |

## Validation and errors

- No 200 OK on missing, invalid or unauthorized object. Use 400/401/403/404/409/413 as appropriate, predictable error JSON.
- Unsupported/corrupt/too long content may initially upload to private GCS then be rejected by `ffprobe`. Never mark READY if validation fails; cleanup invalid source according to documented retention policy.
- Limit upload object size after completion; if using policy with hard size constraints use it, otherwise server checks size before job dispatch. Never trust client size alone.
- Signed URLs are temporary **capabilities**: don't log, cache publicly or share in `GET /api/videos` listing.
- API tests must call private endpoints directly with valid, missing, expired and forbidden credentials.
- Separate authentication vs authorization: Owner owns, Viewer requires explicit permission.

## Implemented local contract, Phase 03–04
- GET /api/auth/config is public client configuration (Firebase Web API key only, not credentials); 503 until project/web key configured. Browser signs in directly with Firebase REST, then sends ID token as Authorization: Bearer. GET /api/me returns verified uid/admin and request_id.
- POST /api/videos JSON: title (1–200 trimmed characters), mime_type (video/mp4, video/webm, video/quicktime), size_bytes (integer 1–50,000,000). Owner always comes from the verified identity, never request JSON. Returns 201 with video_id, upload_url, expires_in=120. No actual duration/codec acceptance before Phase 05 probing.
- Local capability transport: PUT /local-storage/upload?ticket=... uses the issued content type and raw bytes; signature binds operation, immutable object name and byte limit. No public source GET. GET /local-storage/read?ticket=... serves authorized output capabilities with Range support and generation checks. These are local equivalents, not GCS evidence. Werkzeug access logs redact ticket values; no-referrer and no-store headers prevent routine referrer/cache leakage.
- POST complete returns 202 with job_id/status; repeated successful completion returns 200 with the same job_id. Missing object -> 409, actual metadata mismatch -> 400/413. Row lock + unique keys + one transaction protect job/outbox against parallel duplicate completion.
- List returns up to 100 permitted metadata rows, no object paths or signed URLs. Status returns honest state only. Permission JSON: viewer_uid and action=grant|revoke, Owner only; idempotent. Forbidden video access returns 404. Admin monitor uses verified admin=true claim, not a client header.
- Playback/thumbnail require Video READY, matching READY Job and both matching OutputObjects present/unchanged; otherwise 409. Returns url, expires_in=120 and duration_ms. Revocation blocks new URLs; previously issued capability stays valid until expiry. Tests do not claim actual conversion results.

## Added in Phase 07 (Windows VPS)
- `GET /api/config` (public): `auth_provider`, `max_upload_bytes`, `request_id`. Lets the page show the configured limit; contains no secret.
- `GET /api/auth/config` returns `{"provider": "local"}` when `AUTH_PROVIDER=local`; the Firebase response (`api_key`) is unchanged otherwise.
- `POST /api/auth/login` (local provider only; 404 otherwise) JSON `email`, `password` -> 200 `token`, `expires_in`. Wrong or unknown credentials -> 401 `invalid_credentials` (same response for both); locked account or too many attempts from one address -> 429 `too_many_attempts`. The token is sent as `Authorization: Bearer`.
- `POST /api/auth/logout` (authenticated): revokes the current local session.
- `DELETE /api/videos/{id}` (Owner only; others get 404): removes the video, its jobs, outputs, permissions, outbox/queue rows, then the stored files. 409 `video_processing` while a worker holds a live lease.
- `GET /api/videos/{id}/status` now also returns `progress_percent` (measured, only while PROCESSING, otherwise null) and `error_code` (for FAILED/RETRYING).
- `GET /api/monitor` (admin) adds `failed_by_error`, `dead_messages`, `storage_free_bytes`.
- Size limit is `MAX_UPLOAD_BYTES` (default 50,000,000; 200,000,000 in the VPS template). New error: 507 `storage_full` when accepting the upload would leave less than `MIN_FREE_BYTES` free.
- Object names are restricted to `inputs|outputs/` followed by 1–6 segments of `[A-Za-z0-9._-]`; anything else, Windows device names and paths through symlinks/junctions are answered with 404.

## Added 2026-11-18 — account management (local provider only; 404 with `AUTH_PROVIDER=firebase`)
- `GET /api/users` (admin): `users` list of `uid`, `admin`, `active`, `locked`, `created_at`. Never returns password hashes.
- `POST /api/users` (admin) JSON `email`, `password` (12–256 characters), optional `admin` -> 201 `uid`. Errors: 400 `invalid_email` / `weak_password`, 409 `user_exists`.
- `POST /api/users/password` (admin) JSON `email`, `password`: sets a new password and revokes that user's sessions. 404 `user_not_found`.
- `POST /api/users/active` (admin) JSON `email`, `active` (boolean): disables or re-enables sign-in; disabling revokes sessions. 400 `cannot_disable_self` so an administrator cannot lock themselves out.
- `POST /api/auth/password` (any signed-in user) JSON `current_password`, `new_password`: 401 `invalid_credentials` if the current password is wrong; on success all of the user's sessions are revoked.
- Non-admin callers get 403 `admin_required`; unauthenticated callers 401. There is no public sign-up.
- `GET /api/videos` and `GET /api/videos/{id}` items now also carry `size_bytes` and `created_at`.

## Added 2026-11-20 — AWS backends (Phase 07; selected by configuration, local behaviour unchanged)
- `POST /api/videos` now always returns `upload_method`. Local storage: `"PUT"` with `upload_url` (as before). S3: `"POST"` with `upload_url` (the bucket) and `upload_fields`; the browser sends a multipart form with those fields first and the file last, and S3 answers 204. S3 itself rejects a wrong Content-Type or a body larger than the signed limit. `complete` still checks the real size, type and version.
- With `STORAGE_BACKEND=s3`: `PUT /local-storage/upload` and `GET /local-storage/read` answer 404; playback and thumbnail URLs are presigned S3 GET URLs pinned to the published object's VersionId (120 s). New error: 503 `storage_unavailable` when S3 cannot be reached or refuses the request. `GET /api/monitor` returns `storage_free_bytes: null`.
- With `QUEUE_BACKEND=sqs`: `GET /api/monitor` returns `dead_messages: null` (dead letters are in the SQS dead-letter queue, not in PostgreSQL).
- With `AUTH_PROVIDER=cognito`: `GET /api/auth/config` returns `provider: "cognito"`, `region`, `client_id` (public values, no secret). The browser calls Cognito `InitiateAuth` itself and sends the **ID token** as `Authorization: Bearer`. The API accepts only RS256 tokens with the configured issuer and audience, `token_use = "id"`, an unexpired `exp` and `email_verified = true`; `uid` is the lower-cased e-mail and `admin` is membership of the `admin` group. Anything else is 401 `invalid_or_expired_token`; an unreachable key set is 503 `auth_temporarily_unavailable`. `POST /api/auth/login` and the account-management routes stay local-only (404).
- The page's Content-Security-Policy lists only the origins in use: the Cognito endpoint (`connect-src`) and the bucket (`connect-src`, `media-src`, `img-src`). The Firebase host is listed only with `AUTH_PROVIDER=firebase`.

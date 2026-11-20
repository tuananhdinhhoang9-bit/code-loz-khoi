# Security baseline

1. Verify Firebase/Identity Platform ID tokens server-side with official SDK; never trust user ID from request body. Test hooks may inject a fake verifier **only** in test configuration (not in deployed runtime).
2. All private resources require authorization: listings, metadata, status, playback, thumbnail, admin monitoring and permissions. Test with direct HTTP calls.
3. Private GCS bucket: no allUsers/allAuthenticatedUsers access; uniform bucket-level access + public access prevention. Short TTL signed URL only after permission check. Revoked permission prevents issuance of **new** URLs; existing URLs last until expiry — keep TTL short and state this limitation.
4. Upload validation: random object name, allowlisted content type, size/generation check, ffprobe inspection, FFmpeg safe args via `subprocess` list (no shell interpolation). Limit CPU, time, memory, local scratch and input bytes.
5. Database reachable only through documented Cloud Run path and IAM/DB credentials in Secret Manager; minimal privileges. Define region, subnet, private IP routing; don't call a resource private just because it is in the cloud.
6. Separate workload identities for API, relay, dispatcher, worker. Narrow storage prefixes/roles where supported. Pub/Sub push authenticated by OIDC and invoker role.
7. No credentials in code or log. `.env` local only, `.gitignore`. GitHub CI uses Workload Identity Federation rather than permanent JSON keys.
8. HTTPS public entry points; CSRF protection if using session cookies for state-changing routes, otherwise use Authorization bearer tokens + appropriate CORS policy. Avoid XSS with template escaping. Never echo signed URL in logs.
9. Cost/abuse controls: fixed 50 MB limit, 30 s duration, no public anonymous jobs, bounded concurrency, retry limits, download/playback permissions, rate limiting appropriate to demo.
10. `terraform apply/destroy`, database destructive operations, public bucket changes and privileged IAM grants require explicit user authorization.

## Security acceptance

- Direct unauthorized API call -> denied; no video bytes/signed URL leak.
- Private GCS URL without signature -> denied.
- HTTPS public URL; secrets handled appropriately; IAM permissions verified.
- Failed/retried job never exposes partially written video.

## Windows VPS (from 2026-11-17)

Points 1, 5, 6 and 7 above describe the archived GCP design (Firebase, Cloud SQL, workload identities, Secret Manager). Their VPS equivalents — local accounts, localhost-only PostgreSQL with a least-privilege role, per-service virtual accounts with NTFS ACLs, and an ACL-protected config file — are specified in `docs/WINDOWS_VPS_SECURITY.md`. Points 2, 3 (with local storage instead of GCS), 4, 8, 9 and 10 apply unchanged.

## AWS (from 2026-11-20, ADR-021/022)

Read "GCS" as S3, "generation" as VersionId, "Secret Manager" as AWS Secrets Manager, "Firebase" as Cognito. Implemented in code in Phase 07 and tested with stubs only; **not yet verified on AWS**:
- Point 1: Cognito ID tokens verified with the pool's public keys (`app/auth_oidc.py`); RS256 only, issuer, audience, expiry, `token_use` and verified e-mail checked.
- Point 3: private bucket reached only through 120-second presigned URLs; names restricted to the `inputs/` and `outputs/` layout; playback pinned to the checked VersionId.
- Point 4: presigned POST with a signed size range and Content-Type, then server-side size/type/version check, then ffprobe.
- Point 7: no AWS access key in code, configuration or image; boto3 uses the ECS task role. Log lines for S3 failures carry only the operation and error code.
Still to do on AWS (phases 08–09): Block Public Access and bucket CORS, security groups and private RDS subnets, separate task roles, Secrets Manager injection, HTTPS on the load balancer, and the direct-call tests against the real endpoints.

# Local runbook

## Start

1. From the `project-alpha` root, run `./run.ps1` on Windows or `./run.sh` on Linux/macOS; this creates the environment and seeds the local demo assets.
2. Open the printed local URL and copy the one-time demo passwords from the server terminal, or set `ALPHA_DEMO_*_PASSWORD` environment variables before startup.
3. Sign in as `alice` or `bob` to search. Sign in as `admin` to upload/retire documents and view ingestion status.
4. `/health` reports app readiness; the Knowledge Assistant `/api/admin/status` route requires the admin role.

## Recovery and maintenance

- A failed file appears as `NEEDS_REVIEW` with a short parser/validation reason. Correct the source and upload again.
- Re-running the seed script is content-hash idempotent for each filename/version.
- Back up the SQLite file only if its data is approved for the target environment. This sample database can be deleted to reset the demo.
- Retire a source using `POST /api/documents/{document_id}/retire`; verify it no longer appears in a search response.
- On failure, inspect the uvicorn error output, confirm Python/dependencies and file format, then reproduce with a synthetic fixture.

## Before any pilot

For a real organizational pilot, replace the local demo accounts with a verified identity provider and managed secrets; define retention/deletion and encrypted storage; add malware scanning, deployment hardening, monitoring, backups, and review with each source owner. These are release blockers for real organizational data.

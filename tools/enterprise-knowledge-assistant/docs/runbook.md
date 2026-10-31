# Local runbook

## Start

1. Create and activate a Python virtual environment; install `requirements.txt`.
2. Run `python scripts/seed_demo.py` to index the three authored synthetic sources.
3. Start with `uvicorn app.main:app --host 127.0.0.1 --port 8000`.
4. Visit `/`; `/health` is the process health endpoint and `/api/admin/status` shows local ingestion state.

## Recovery and maintenance

- A failed file appears as `NEEDS_REVIEW` with a short parser/validation reason. Correct the source and upload again.
- Re-running the seed script is content-hash idempotent for each filename/version.
- Back up the SQLite file only if its data is approved for the target environment. This sample database can be deleted to reset the demo.
- Retire a source using `POST /api/documents/{document_id}/retire`; verify it no longer appears in a search response.
- On failure, inspect the uvicorn error output, confirm Python/dependencies and file format, then reproduce with a synthetic fixture.

## Before any pilot

Replace header-derived identity with verified authentication and group claims; protect admin routes; define retention/deletion and encrypted storage; add malware scanning, deployment hardening, monitoring, backups, and review with each source owner. These are release blockers for real organizational data.

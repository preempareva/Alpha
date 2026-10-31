# Project Alpha baseline audit

This is a code inspection and test run of the already extracted project. The supplied setup instruction to unzip another copy was skipped as requested. Claims below were checked against the local files and are not assumed to be true merely because earlier documentation says so.

## Baseline findings

| Finding | Evidence | Priority |
|---|---|---|
| Knowledge Assistant accepts `X-User-Id` and `X-User-Groups` as identity and access control. Upload, admin status, and retire routes are unauthenticated. | `tools/enterprise-knowledge-assistant/app/main.py`: `user_context`, `/api/ask`, `/api/feedback`, `/api/documents`, `/api/admin/status`, `/api/documents/{id}/retire`; `static/app.js` supplies these headers from a browser selector. | P0 |
| Alpha dynamically imports every project under the same `app.main` name, mutates `sys.path`, removes modules from `sys.modules`, and manually dispatches deprecated startup/shutdown hooks. | `alpha_app/main.py`: import loop and `@app.on_event` handlers. | P0 |
| A root-level pytest run does not collect cleanly because project tests share the generic `app` package name and rely on per-test path mutation. Collection produced six import errors, including imports resolving to the wrong project. | `python -m pytest "ai projects\\project-alpha\\tools" -q` on 2026-10-31. Errors span observability, segmentation, knowledge, demand, inventory, and BI tests. | P0 |
| The Windows PowerShell terminal renders some valid UTF-8 glyphs incorrectly; reading the source as UTF-8 confirms the files contain the intended Unicode characters. This was a terminal display issue, not a source corruption issue. | `static/index.html`, `static/app.js`, `alpha_app/main.py`. | P2 |
| Readiness currently reports a static `ok` instead of checking each mounted project's DB/model dependencies. | `alpha_app/main.py` `/health`; individual tool `/health` functions mostly return a constant. | P1 |
| Sales forecast docs/evaluation make claims about repeated snapshots; current generator creates distinct opportunity IDs per row, so this claim needs correction or generator evidence. | `tools/sales-pipeline-forecasting/scripts/generate_data.py`, `README.md`, `docs/model_card.md`, `scripts/train.py`. | P1 |
| BI's “agents” are a deterministic route/tool workflow with a trace, not autonomous LLM agents. | `tools/multi-agent-business-intelligence/app/workflow.py`. Rename/describe honestly. | P1 |
| Sentiment results are generated from synthetic/template-like data and should not be presented as general real-world performance. | `tools/customer-sentiment-intelligence/scripts/` and any committed evaluation output (ignored generated artifact). Re-evaluate before retaining numerical claims. | P1 |
| Runtime caches, bytecode, databases, generated CSVs and model artifacts exist in the extracted working copy. Most are covered by ignore patterns, but a clean fresh-clone seed path and repository index still need verification. | Files under each `tools/*` tree; root `.gitignore`. | P2 |

## Phase 0 plan

1. Add a root `pyproject.toml`, pinned dependency lock, pytest/Ruff/type-check configuration, and a single root test command.
2. Introduce stable package identities for each tool, remove import-path/module-cache hacks, and convert mounted apps to routers without changing existing `/tools/<slug>/...` URLs.
3. Replace event hooks with lifespan and add a tested `alpha_core` configuration, logging/request IDs, error handling, and optional Ollama adapter. Keep the default provider disabled.
4. Add deterministic seed orchestration, readiness checks, cross-platform launchers, and CI; ensure generated/local artifacts stay out of Git.
5. Fix documentation and UI encoding issues, then add root integration coverage for every mounted health route.

## Phase 0 progress

- Added repo-local package identities and removed the Alpha and test-suite `sys.path`/`sys.modules` mutation. Existing tool endpoint paths remain mounted under `/tools/<slug>/`.
- Replaced manual startup-hook dispatch with FastAPI lifespan contexts, including the three project apps that initialize local SQLite databases.
- Added shared settings, request IDs, structured request logs, root-shell error envelopes, and an optional Ollama-only adapter with a disabled default and fake provider.
- Added a bootstrap module used by the Windows and Linux launchers, repository test/lint/type-check configuration, CI workflow, and root integration tests.
- The shell checks all 13 tool health handlers and reports degraded status if one fails. Individual legacy health handlers still need deeper DB/model readiness checks.
- Deferred direct `APIRouter` conversion to a later compatibility pass because the individual demos currently provide their own root pages and `/docs`; endpoint and docs compatibility needs explicit coverage before replacing their mounted ASGI apps.
- Fixed the sales-pipeline documentation/evaluation mismatch: the generator creates one row per opportunity, not repeated historical snapshots.
- Confirmed the apparent garbled glyphs in PowerShell output are valid UTF-8 in the source files; no text repair was needed.

Latest validation: `python -m pytest -q` from the Alpha root — **41 passed** on Python 3.14.0. The project targets Python 3.12+; a Python 3.12 CI run remains pending.

## Knowledge Assistant security progress

- Removed all trust in `X-User-Id` and `X-User-Groups`. A signed, HttpOnly, eight-hour cookie identifies a database user; role and groups are read from the server-side users table on every request.
- Added bcrypt password hashes, configurable demo credentials, and random one-time credentials printed only when the demo accounts are first created. Admin-only access covers upload, retirement, and ingestion status.
- Moved the access-group predicate into the SQLite retrieval query before candidate text is returned; expired and retired documents remain excluded.
- Added `audit_events` for successful login/logout, document upload/retirement, and feedback. Updated both the Alpha panel and standalone Knowledge page to sign in without identity headers.
- Added adversarial tests for unauthenticated requests, header spoofing, cross-group access, admin authorization, expiry, retirement, and audit logging.
- Validation on the Alpha-local Python 3.14 environment: **45 tests passed**; `ruff check alpha_core`, `mypy`, and `node --check static/app.js` passed. Full pytest still emits dependency deprecation warnings from Starlette/httpx and PyMuPDF; no failures.

## Baseline test result

Command: `python -m pytest "ai projects\\project-alpha\\tools" -q`

Result: **collection failed** with six import errors. The test run did not reach the full per-project test suite. Python 3.14.0 was used because no Alpha-local virtual environment was present; the project requirements currently pin FastAPI 0.162.0 and pytest 9.2.0. Do not interpret prior test claims as a current green baseline.

## Scope and limitations

This audit covers local source and test collection. It does not establish security suitability for deployment, real-data model quality, or live third-party service reliability. The Alpha UI binds to localhost and currently has no authenticated user session.

# Build state

Updated: 2026-11-01

## Baseline

Baseline was run on branch alpha-v2-build before changes for this master plan. The existing Prompt 1 work was already present as an uncommitted working-tree diff and is included in this baseline.

- Full tests: **63 passed**, 6 dependency deprecation warnings.
- Repo-wide Ruff: **failed**, 114 findings across legacy tool folders.
- Mypy: **passed**, 10 configured source files, no issues.
- JavaScript syntax: **passed**, node --check static/app.js.
- Retrieval eval: last run in the previous task passed its recorded synthetic-corpus thresholds (Recall@5 0.977, abstention 1.0, ACL leakage 0); rerun during Phase G/H verification.

## Phase checklist

- [x] Phase A — Agent runtime hardening. Gate passed: 75 full-suite tests; 23 runtime tests; 12 Knowledge Assistant auth/access tests; scoped Ruff passed for core, app shell, and changed auth/runtime modules; mypy passed across 12 core source files; JavaScript syntax passed.
- [x] Phase B — BI Analyst Workflow tool-using agent. Gate passed on the current synthetic dataset: full pytest 101 passed; changed-code Ruff passed; mypy passed for 13 Alpha core files and 6 BI source files; JS syntax passed; 40-case BI evaluation and 5 tamper trials completed.
- [x] Phase C — Alpha Agent Hub. Gate passed: full pytest 119 passed, 7 warnings; scoped Ruff passed; mypy passed for 14 Alpha core/Hub files and 5 BI package source files; JavaScript syntax passed for both static files; 60-task HTTPX/API and runtime evaluation plus five BI tamper trials completed.
- [ ] Phase D — Business Data Copilot.
- [ ] Phase E — Inventory Control Tower.
- [ ] Phase F — Hub wiring and expanded evaluation.
- [ ] Phase G — Housekeeping, CI, docs consistency.
- [ ] Phase H — Final self-audit and fresh-clone verification.

## Phase A notes

The runtime no longer accepts caller-supplied approved call IDs or approval callbacks. It now uses persisted, single-use approval records, canonical saved plans, immutable registry snapshots, identity-scoped trace reads, per-step idempotency contexts, atomic run/step claims, read-only retry rules, bounded/redacted traces, correlation IDs, and retention cleanup. The Knowledge Assistant now uses the shared signed-session codec without changing its cookie claims or server-side user lookup.

Repo-wide Ruff remains at the recorded legacy baseline scope; no excluded app was mass-reformatted. Full scoped Ruff checks passed for all changed Python code.

## Phase B notes

Added deterministic and optional local-LLM planning, fixed allowlisted SQL tools, SQLGlot AST checks, read-only/time-bounded SQLite execution, per-user signed-session identity, user-scoped traces, and independent Python verification. The legacy BI `/api/ask`, `/api/trace`, and `/health` routes remain available. The BI page now presents the actual planner mode and SYNTHETIC/read-only badges.

- Full test suite: **101 passed**, 7 dependency/deprecation warnings.
- Changed Python Ruff scope: **passed**. Repo-wide Ruff still fails with **111 legacy findings**; it had 114 at the recorded baseline and was not mass-reformatted.
- Mypy: **13 Alpha core source files passed**; **6 BI source files passed** with `tools/multi-agent-business-intelligence/mypy.ini` and that tool folder as the mypy working directory.
- JavaScript syntax: **passed** for the one tracked `static/*.js` file.
- BI synthetic gold evaluation: 40 questions; tool sequence 1.0, argument accuracy 1.0, numeric correctness 1.0, refusal/clarification correctness 1.0; verifier caught 5/5 tamper attempts; p50 11.841 ms, p95 18.733 ms. These scores only describe this hand-authored, templated benchmark and do not estimate performance on real users or data.
- Evaluation mode: `LLM_PROVIDER=none`; Ollama not run. The available runtime was Python 3.14; Python 3.12 is not installed in this environment.

The BI project folder name contains hyphens, so mypy cannot derive its package root from the repository root. Run the BI config from that folder with `MYPYPATH` containing the BI folder and Project Alpha root; this is recorded in its local `mypy.ini`.

## Phase C notes

Added the authenticated Hub API and a vanilla JavaScript workspace screen with tool catalogue, plan preview, cross-tool run results, evidence tables/charts, trace timeline, run history, cancellation, and an approval inbox. The app shell serves the Hub UI as a separate static module while the 13 existing project slugs and routes remain mounted. Workspace scope now comes from the Knowledge Assistant's configured `ALPHA_WORKSPACE_ID`; same-workspace admins can review approvals, and an approved saved plan resumes with the original active requester identity. Hub POSTs require signed user-bound CSRF tokens and are rate-limited per user.

- Full test suite: **119 passed**, 7 dependency/deprecation warnings.
- Changed-code Ruff: **passed**. Repo-wide Ruff remains at **111 legacy findings**; no broad reformat was attempted.
- Mypy: **14 Alpha core/Hub source files passed**; **5 BI package source files passed** using the package-local config and `MYPYPATH`.
- JavaScript syntax: **passed** for both `static/app.js` and `static/agent-hub.js`.
- HTTPX-backed TestClient API coverage includes CSRF, spoofed identity headers, role/workspace scoping, admin approval/resume, cancellation, policy refusals, rate limiting, and verified BI+demand cross-tool output. Playwright/browser automation was not run.
- Offline Agent Hub evaluation: **60 tasks** with `LLM_PROVIDER=none`; tool-selection accuracy 1.0000, argument accuracy 1.0000, normal-task end-to-end success 1.0000, correct refusals 1.0000, policy-denial correctness 1.0000, trace completeness 1.0000; p50 12.065 ms and p95 212.090 ms. BI verifier caught **5/5** tampering trials. The hand-authored benchmark is templated and synthetic; these results do not estimate general user-query accuracy. Ollama was not run.
- Evaluation metadata and per-task outcomes are in `docs/eval/agent_hub.json`; summary and limits are in `docs/eval/agent_hub.md`. No result rows or model/data contents are stored in the evaluation report.
- Only Python 3.14 is available in this environment; the exact Python 3.12 runtime remains unverified.

## Next action

Begin Phase D1: implement the Business Data Copilot upload, profiling, and isolated synthetic workspace data path without changing the existing 13 projects.

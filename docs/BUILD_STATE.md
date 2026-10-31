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
- [ ] Phase C — Alpha Agent Hub.
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

## Next action

Begin Phase C1: add the Alpha Agent Hub backend routes and connect the verified BI tools while preserving existing app routes and session-derived identity.

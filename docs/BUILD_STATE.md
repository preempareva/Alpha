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
- [x] Phase D — Business Data Copilot. Gate passed: 135 full-suite tests; 16 Copilot-focused tests; scoped Ruff, core/BI/Copilot mypy, JS syntax, and the saved synthetic Copilot evaluation passed.
- [x] Phase E — Inventory Control Tower. Gate passed: 154 full-suite tests; 19 inventory tests covered by the full run; scoped Ruff, core and inventory mypy, JS syntax, dependency consistency, and saved forecast/scenario evaluation passed.
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

## Phase D notes

Added the Business Data Copilot as the fourteenth Alpha tool while preserving the existing thirteen slugs and route prefixes. It supports bounded CSV/XLSX uploads, in-memory schema previews, explicit schema confirmation, hashed owner/workspace DuckDB storage, session-bound CSRF, read-only typed queries, a SQLGlot SELECT guard, timeout/result caps, an independent pandas verifier, and formula-safe CSV export. Sensitive fields are removed from optional planner schemas, Hub profiles, confirmed previews, dimensions, filters, query labels, and audit plans; explicit aggregates are deterministic and use generic aliases. The shared Hub now registers copilot.profile and copilot.query.

- Full tests: **135 passed**, 7 dependency/deprecation warnings. Tests used PYTHON_DOTENV_DISABLED and temporary test stores.
- Copilot-focused tests: **16 passed**, including file/magic checks, XLSX macro/external/embedded/traversal rejection, formula text preservation, SQL injection parameterization, cross-user/workspace access, CSRF, upload body cap, sensitive date grouping, Hub routing, CSV formula escaping, and verifier tampering.
- Changed-code Ruff passed. Repo-wide Ruff reports **111 legacy findings**; no broad reformat was attempted.
- Mypy passed for **14 Alpha core/Hub files**, **6 BI source files**, and **11 Copilot source/script files**. JavaScript syntax passed for all static JS modules.
- Copilot synthetic evaluation: **40/40** numeric questions, **4/4** refusal cases, verifier caught **5/5** tampered results; p50/p95 **150.718 / 187.191 ms**, with LLM_PROVIDER=none. The hand-authored templates cover one fixed-seed fictional dataset only and do not estimate general query accuracy.
- The synthetic demo generator ran successfully and its output was confirmed git-ignored. No result rows or uploaded content are recorded in the evaluation.
- DuckDB data is not encrypted at rest. This limitation is documented in the tool README, data card, threat model, and UI.
- Only Python 3.14 is available in this environment; the Python 3.12 target remains unverified.

## Phase E notes

Merged the inventory forecasting and replenishment workflows into Inventory Control Tower while preserving both existing app slugs and the legacy `/api/backtest` and `/api/recommend` routes. Added a fixed-seed, validated synthetic dataset; Decimal-based ATP, safety-stock, reorder, MOQ/pack/budget/max-stock, coverage, and transfer calculations; rolling-origin baseline/ETS/Croston forecasts with empirical residual intervals; and fixed-seed lean/balanced/resilient scenario comparisons. Hub reads now include risk, position, forecast, scenario, and transfer tools. Replenishment drafts and their simulated execution remain owner-scoped, idempotent, locally recorded, and gated by separate persisted approvals. The combined workflow screen shows stock components, inbound purchase orders, excess positions, budget-aware drafts, transfers, and scenario tradeoffs.

- Full test suite: **154 passed**, 7 dependency/deprecation warnings, using isolated temporary stores with `PYTHON_DOTENV_DISABLED=1` and `LLM_PROVIDER=none`.
- Inventory test module: **19 tests**; all passed in the full run, including formula boundaries, leakage/interval checks, approvals, idempotency, existing routes, and shell integration.
- Changed-code Ruff passed. Mypy passed for **14 Alpha core/Hub files** and **6 inventory source/script files**. `node --check static/inventory.js`, `git diff --check`, and `pip check` passed.
- Forecast evaluation saved at `docs/eval/inventory_forecast.json` and `.md`: 36 horizon/segment metric groups and 6 scenario tradeoffs. The selected baselines were naive for intermittent demand and ETS for seasonal demand under the documented simplicity rule. Metrics use fixed-seed synthetic data only.
- The standalone inventory legacy routes and both existing inventory slugs remain available. The local approval flow does not create or send real purchase orders.
- Only Python 3.14 is available in this environment; Python 3.12 remains unverified. Browser-driven UI testing was not run.

## Next action

Begin Phase F: rerun the 60-task Agent Hub benchmark and add 20 evaluated cross-project tasks that each use at least three read tools, then update Hub demo and screenshot guidance.

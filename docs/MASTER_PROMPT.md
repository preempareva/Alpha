# Codex master prompt: one run, everything

Why this is built differently: Codex fails on mega-prompts when it loses state, skips verification, or quits halfway. This prompt fixes that with (1) hard rules up front, (2) internal phases with acceptance gates it must pass before moving on, (3) a `docs/BUILD_STATE.md` checkpoint file it updates after every phase so a one-line "continue" resumes exactly where it stopped, (4) local checkpoint commits on a dedicated branch (never push), (5) a self-audit at the end.

## Before you paste (you, 3 min)

```
git switch p1-knowledge
git add -A && git status          # make sure no .env, *.db, *.zip, model binaries are staged
git commit -m "WIP: agent runtime foundation (pre-hardening)"
git switch -c alpha-v2-build
```
Delete `project-alpha-source.zip` from the folder, add `*.zip` to `.gitignore`. Rotate the APEX keys (they were in AI.zip). Never put AI.zip anywhere near Codex. Install Ollama only if you want LLM planning (`ollama pull llama3.1:8b`); everything must pass with it OFF.

Open Codex in `project-alpha/`, set it to the strongest model and highest reasoning effort you have, full-auto/workspace-write (no network needed except pip). Paste everything inside the box below.

---

## THE PROMPT (paste all of this)

```
ROLE
You are the lead engineer finishing Project Alpha v2 in ONE autonomous run. Work through every phase below in order, without asking me questions. When something is ambiguous, pick the safest reasonable option, write the decision into docs/DECISIONS.md, and continue. Only stop early if a hard rule would be violated or you hit a blocker you cannot work around (record it in docs/BUILD_STATE.md).

STEP 0: ORIENT (do before any change)
1. Read AGENTS.md, README.md, docs/*.md, pyproject.toml, requirements*.txt, .github/workflows/*, alpha_core/**, alpha_app/main.py, static/app.js, static/index.html, tests/**.
2. Run: git status; git log --oneline -10; the full test suite, ruff, mypy. Record the real baseline (pass/fail counts) in docs/BUILD_STATE.md. If baseline tests fail, fix test infra only (not behaviour) before proceeding.
3. Create docs/BUILD_STATE.md with a checklist of Phases A to H, status of each, baseline numbers, and a "next action" line. Update it after EVERY phase. This file is how a later session resumes: if it already exists with completed phases, SKIP those phases and continue from the first unfinished one (after re-running tests to confirm they're still green).
4. Work on the current branch `alpha-v2-build`. After each phase passes its gate, make ONE local checkpoint commit: "phase X: <summary>". NEVER push, merge, rebase, force, or touch other branches.

HARD RULES (violating any = stop and report)
R1 No paid or key-based LLM APIs (Anthropic, OpenAI, Gemini, Groq, etc.). No such packages in any requirements file. LLM = optional local Ollama through alpha_core/llm.py only. Default LLM_PROVIDER=none. EVERY feature must work, and be tested, with the LLM off. Tests use FakeProvider; CI never needs Ollama.
R2 Clean-room. Never read, copy, or reference APEX/AI.zip/any employer (Media.net, RP Tech) code, data, names, hostnames, schemas, or credentials. All data is synthetic (clearly labelled SYNTHETIC in UI, API responses, README, data/model cards) or public data under its licence.
R3 Never read or print .env*, *.db, *.duckdb, logs, uploads, generated data, or model binaries. Only .env.example. Never commit secrets, databases, generated data, model binaries, caches, zips.
R4 LLM output is untrusted. It can only propose typed, schema-validated plans. The server re-checks identity, role, workspace, tool allowlist, arguments, and side-effect policy IMMEDIATELY before every tool call. The LLM never writes SQL, shell, Python, or performs external writes, and never calculates numbers (numbers come from tested Python/SQL).
R5 Identity, role, workspace, and approvals come ONLY from the authenticated server-side session. Never from request bodies, query params, or custom headers. Reuse the existing signed-session auth from the Knowledge Assistant by moving it into a shared alpha_core/auth module (keep the Knowledge Assistant's behaviour and tests green).
R6 Honest labels. Only call something an "agent" if a planner really selects registered tools at runtime under bounded steps, policy checks, and approval gates. Otherwise say rule-based / workflow. No invented metrics, accuracy, savings, or "production-ready" claims. Every number in any README, doc, or UI that is a measured result must come from an eval you actually ran and saved in docs/eval/*.json|md.
R7 Do not rewrite the 13 existing apps. Preserve existing routes/URLs/slugs and passing tests. Add, don't break. Refactor only what a phase explicitly requires.
R8 Tests before/with code. Fail closed on every error path. Python 3.12, Windows + Linux compatible (no bash-only code in app logic; keep run.ps1 and run.sh working).
R9 Dependencies: add only what a phase needs (e.g. duckdb, openpyxl, sqlglot, statsmodels, python-multipart already present). Pin in requirements.lock/pyproject. LightGBM is OPTIONAL: import guarded, tests pass without it.
R10 Be truthful in the final report. Never claim a command passed unless you ran it in this session and saw it pass.

VERIFICATION LOOP (applies to every phase)
After implementing a phase: run pytest (full), ruff, mypy (config must cover every new package), the JS syntax check (node --check on static/*.js if node exists), and the phase's own eval/negative tests. If anything fails, fix and re-run until green, up to 5 repair iterations per phase. If still failing, record the failure in BUILD_STATE.md, revert the broken part of that phase, and move on only if later phases don't depend on it; otherwise stop and report.

=========================================================
PHASE A: Harden the Agent Runtime (alpha_core/agent/)
=========================================================
Files: models.py, policy.py, registry.py, runtime.py, trace.py (+ new approvals.py, redaction.py if useful), tests/test_agent_runtime.py (split into several test files).
Audit each file, cite file:line for every finding in docs/SECURITY_REVIEW_AGENT_RUNTIME.md, then fix:
A1 Approval spoofing: BoundedExecutor.run currently takes `approved_call_ids` as an argument. REMOVE that trust path. Executor consults only persisted approval records.
A2 Approval records table: approval_id, run_id, call_id, plan_hash, user_id, workspace_id, requested_by, approver_id, status (pending|approved|rejected|expired), created_at, expires_at, decided_at, reason. Rules: approver identity comes only from the authenticated Identity; approver must hold an allowed role; self-approval blocked when policy says so; bound to run_id+call_id+plan_hash; single-use (consumed on execute, replay fails); expired/rejected/wrong-workspace/wrong-plan fail closed. APIs: request_approval(), approve(), reject(), expire_stale(), consume().
A3 Immutability: plans and ToolSpecs are deep-copied or frozen (frozen pydantic models + tuple/frozenset/MappingProxy or deepcopy on ingress and egress) at submission/registration. plan_hash is computed over canonical JSON (sorted keys) of exactly what executes. Resume uses the STORED plan only; caller-supplied params on resume are rejected.
A4 Concurrency/idempotency: atomic step claiming via SQLite transaction/compare-and-set on step state; per-run lock; idempotency key per step; retries only re-run read-class tools automatically; write/external steps are never auto-retried.
A5 State machine: requested -> planned -> validated -> running -> (waiting_approval <-> running) -> completed|failed|cancelled. Reject illegal transitions with a typed error. Cancellation mid-run works and is recorded. Timeouts produce a failed step with code TIMEOUT.
A6 Trace safety: configurable redaction of sensitive keys (password, token, secret, api_key, authorization, cookie, email optional) in stored args/results; size caps per field and per run; results always valid JSON; error codes only (no stack traces/secrets); correlation_id on every run/step/log line; retention setting (RETENTION_DAYS) with purge_expired() + test.
A7 Cross-user/workspace isolation: a user can only read/cancel/resume their own runs (admins by role); every trace query is workspace-scoped.
A8 Adversarial tests (all must fail closed): plan mutation after submission; ToolSpec mutation after registration; forged approval; approval replay; expired approval; unauthorized approver role; self-approval when disallowed; workspace mismatch; cross-user run access; two concurrent duplicate requests -> exactly one execution; retry behaviour + no duplicate side effects; cancellation mid-run; timeout; oversized output; malformed non-JSON output; every invalid state transition; redaction of sensitive keys; retention purge; step cap (max 5); unknown tool; role denial; LLM-off fallback.
GATE A: all tests/ruff/mypy green; docs/agent_runtime.md written (state machine diagram in mermaid, approval flow, redaction/retention, threat model, limits). Checkpoint commit.

=========================================================
PHASE B: BI Analyst Workflow becomes a real tool-using agent
=========================================================
Project: tools/multi-agent-business-intelligence (keep existing routes working; add new ones).
B1 Move shared pieces: build alpha_core/agent/planner.py with `Planner` interface: DeterministicPlanner (wraps the existing keyword router, outputs typed AgentPlan) and LLMPlanner (uses alpha_core.llm provider with a JSON schema = AgentPlan, one retry on parse failure, then falls back to deterministic). The planner cannot grant itself permissions; plan is validated by registry+policy.
B2 Register approved read-only, parameterized tools with typed input/output schemas, row caps, timeouts: revenue_trend(grain, date_range), top_categories(metric, n, date_range), top_products, refund_rate(by), anomaly_check(metric, window, z_threshold), region_breakdown, and a verifier tool `verify_totals`. NO free-form SQL anywhere; SQL is built by deterministic code with bound parameters against an allowlist; read-only connection; statement timeout; row limit; sqlglot AST check as a second guard (single SELECT only, allowlisted tables/columns).
B3 Verifier: re-computes totals/row counts independently and compares to tool outputs; the report writer may only include numbers that carry a tool_result_id; unsupported numbers are removed and flagged in the report.
B4 Endpoint: POST /tools/bi/api/agent/ask {question} -> {answer, findings[], data, evidence_ids[], limitations[], trace{run_id, steps[], timings}, mode:"deterministic"|"llm_planned"}. Identity from session. Also GET .../runs/{id} (owner/admin only).
B5 Evaluation: gold set of 40 questions with expected tool sequence and expected numeric results (computed from the synthetic dataset by independent code, not by the system under test). Include: ambiguous question (must ask to clarify), unsupported question (refuse), write attempt ("delete all rows") refused, prompt-injection in the question, SQL-injection strings in filters, over-long input, unknown metric. Save results to docs/eval/bi_agent.json + .md: tool-selection accuracy, argument accuracy, numeric correctness, refusal correctness, verifier catch rate (include tests that tamper with a number), latency p50/p95. Run it with LLM off (and with Ollama only if it is available; otherwise state "not run").
B6 Rename/label honestly in UI + README: "BI Analyst Workflow" with a visible badge "Deterministic planner" or "LLM-planned (local)".
GATE B: green + eval files exist + docs/agent cards updated. Checkpoint commit.

=========================================================
PHASE C: Alpha Agent Hub (backend + UI)
=========================================================
C1 Backend router alpha_app/agent_hub.py: POST /api/agent/ask, GET /api/agent/runs, GET /api/agent/runs/{id}, POST /api/agent/runs/{id}/cancel, GET /api/agent/approvals?status=pending, POST /api/agent/approvals/{id}/approve|reject (approver identity from session only; CSRF token required for all state-changing routes; rate limit per user).
C2 Tool catalogue endpoint listing registered tools the CURRENT user may use (filtered by role/workspace), with description, side_effect, schemas.
C3 Planner: deterministic router for obvious asks (map intents to tools across BI, Knowledge Assistant search, and later Copilot/Inventory tools registered by those phases); LLMPlanner for ambiguous multi-step asks; if LLM is off and the ask is ambiguous, return a clarification question. Max 5 steps. Unsupported -> clear refusal.
C4 Register read-only tools from existing projects too: knowledge.search (ACL-filtered, uses the caller's identity), sales_forecast.score_demo, churn.score_demo, demand.forecast_demo (read-only, SYNTHETIC-labelled). Each has typed schemas and role scopes.
C5 UI (add to static/, new "Agent Hub" card at top of the sidebar; keep the existing visual identity): ask box; plan preview card (steps, tools, args); live run timeline (state per step, timings, evidence IDs, denials); results panel (answer, tables/charts using the existing chart approach, limitations); approval inbox (pending proposals with approve/reject, reason field, shows who/when); run history; clear badges: SYNTHETIC data, LLM-off/Planner mode, "read-only". Loading, empty, error, denied, needs-approval states. Keyboard accessible, labels on inputs, no inline secrets. No frameworks needed; keep vanilla JS but organise into modules.
C6 Verifier + report composer shared across tools: final answer lists each number with its evidence ID.
C7 Eval: 60 tasks (normal, ambiguous, unsupported, prompt injection, unauthorized tool attempts, malformed args, timeouts, cross-workspace, approval-required). Metrics: tool-selection accuracy, argument accuracy, end-to-end success, correct refusals, policy-denial correctness, trace completeness, p50/p95 latency. Save docs/eval/agent_hub.json + .md. Real runs only.
C8 Playwright (or httpx-driven) smoke test of the UI flow if Playwright is installable without network issues; otherwise API-level tests plus JS syntax check, and state which one was done.
GATE C: green; eval saved; docs/agent_hub.md (architecture diagram, tool contract, demo script of a cross-tool question needing >= 2 independent tools at this stage and >= 3 after Phase E). Checkpoint commit.

=========================================================
PHASE D: Business Data Copilot (new tool: tools/business-data-copilot, slug "copilot")
=========================================================
Follow the existing tool layout (app/, tests/, docs/, README, requirements) and mount it in alpha_app like the others; add a sidebar card + a proper workflow screen.
D1 Upload: strict size cap (config, default 10 MB), allowlist .csv/.xlsx, magic-byte/signature check (xlsx = zip with expected parts), safe generated filenames, store under an instance/workspaces/<workspace_id>/ dir outside static root, reject xlsx containing macros (vbaProject), external links, or embedded objects; never evaluate formulas (openpyxl data_only / read formulas as text); csv delimiter/encoding detection with limits; row/column caps.
D2 Profiling: inferred types, nulls, duplicates, date ranges, min/max, cardinality, outliers (IQR), invalid values, quality warnings with severity; preview 20 rows. User confirms schema (types, date field, measures vs dimensions) and marks sensitive columns (excluded from LLM prompts and from output unless aggregated).
D3 Load into isolated per-workspace DuckDB (manifest: source sha256, ingest time, row count, schema version, retention). Workspace id derived from the session. Connection used for queries is read-only; ingestion uses a separate writer path.
D4 Query: typed QueryPlan {measures[{col,agg}], dimensions[], filters[{col,op,value}], time_grain, order_by, limit}. Planner: deterministic parser for simple asks ("revenue by region last 6 months") and optional local-LLM planner producing the same typed plan; LLM sees only schema + column names/types + sample-free stats (never raw rows from sensitive columns). Deterministic compiler -> parameterized SQL on allowlisted columns/aggregations only (SUM, AVG, COUNT, COUNT DISTINCT, MIN, MAX); sqlglot guard; statement timeout; row/byte caps; every query audit-logged (redacted).
D5 Verifier: re-computes totals and row counts via an independent path (pandas) and compares; output = table + chart spec + query plan + assumptions + provenance (dataset hash, query id, row counts, time).
D6 Charts: render in UI with the existing chart approach (bar/line/table).
D7 Register tools in the ToolRegistry as read-class: copilot.profile, copilot.query. Hub can call them.
D8 Synthetic demo dataset + generator script (orders: date, region, product, channel, units, revenue, cost, segment; include deliberate quality issues: nulls, duplicates, a negative quantity, an outlier). Labelled SYNTHETIC.
D9 Tests: malicious filenames (../, absolute, unicode tricks), oversize, wrong extension/magic mismatch, xlsx macros/external links, formula injection cells (=cmd|...), CSV injection on export, SQL injection through filter values and column names, unknown column/agg, write/DDL attempts, cross-workspace access, cross-user access, LLM-off path, verifier tamper test. Gold set of 40 questions with expected numeric results (computed independently). Save docs/eval/copilot.json + .md.
D10 Docs: data card, agent card, threat model, runbook, demo script.
GATE D: green; eval saved. Checkpoint commit.

=========================================================
PHASE E: Inventory Control Tower (extends tools/intelligent-inventory-forecasting + tools/inventory-optimization-agent; keep their old routes working; add new routes + a combined workflow screen; the card keeps the existing slugs)
=========================================================
E1 Synthetic generator + tables (label SYNTHETIC everywhere): sales_history(sku, location, date, units, revenue), inventory_snapshot(sku, location, snapshot_time, on_hand, reserved, blocked, in_transit), purchase_orders(po_id, sku, location, supplier_id, order_date, expected_date, open_qty, status), supplier(supplier_id, lead_time_days, lead_time_std, min_order_qty, pack_size, unit_cost, reliability), transfers(transfer_id, sku, source_location, destination_location, qty, ship_date, eta, status), sku_policy(sku, location, service_level, review_period_days, max_stock_days). Include intermittent-demand SKUs, seasonality, promotions, supplier delays, blocked stock, and a data-quality validator with its own tests. Fixed seed; reproducible.
E2 Deterministic business logic (Decimal for money; every formula documented in docs/inventory_formulas.md): available_to_promise = on_hand - reserved - blocked (blocked never sellable); inventory_position = ATP + confirmed incoming - backorders; demand over lead time + review period from the selected forecast; safety stock from service level z and combined demand + lead-time variance (state the formula); reorder point; order quantity respecting MOQ, pack size, budget, max stock; days/weeks of cover with explicit zero/negative-demand handling; transfer proposals constrained by source surplus, destination shortage, route time, cost.
E3 Forecasting: baselines (naive, seasonal naive, moving average, ETS via statsmodels, Croston/SBA for intermittent) plus optional LightGBM global challenger (guarded import). Rolling-origin backtests at multiple cutoffs and horizons. Report WAPE, MASE or RMSSE, bias, and prediction-interval coverage by horizon and segment (replace the old symmetric stdev band with empirical-residual or conformal intervals and report their measured coverage). Keep the simplest model that wins; record the comparison in docs/eval/inventory_forecast.json + .md.
E4 Scenario simulator: lean / balanced / resilient policies under (a) supplier delay and (b) demand spike; Monte Carlo with fixed seed; report fill rate, stockout days, avg inventory, holding cost, excess, expedite cost, order frequency. Present trade-offs, not a single "optimal" answer.
E5 Workflow: ingest -> validate -> forecast -> position -> risk/excess detection -> options (reorder, transfer, wait) -> recommendation -> NEEDS_APPROVAL -> simulated execution -> reconcile expected vs observed. NO real purchase orders; proposals are `draft` side effect; "execute" is simulated and requires a persisted approval from Phase A.
E6 Register tools for the Hub: inventory.risk_ranking (read), inventory.position (read), inventory.forecast (read), inventory.propose_replenishment (draft), inventory.simulate_scenario (read). Demo question for the Hub: "Which SKUs are at risk over the next 6 weeks, why, and what should I review first?" must use >= 3 independent tools and produce a risk-ranked report with evidence IDs.
E7 UI: workflow screen with risk table, SKU detail (forecast band, stock position bars, PO/supplier info, transfer options), scenario comparison chart, proposal list with approve/reject; SYNTHETIC badge; empty/loading/error states.
E8 Tests: formula unit tests with hand-computed expected values; boundary cases (zero demand, negative stock, MOQ > need, pack rounding, budget cap); leakage test (features use only data <= cutoff); interval coverage test; approval-gating; idempotent simulation.
GATE E: green; eval saved; docs (data card, model card, agent card, runbook, demo script). Checkpoint commit.

=========================================================
PHASE F: Wire everything into the Hub and re-evaluate
=========================================================
F1 Ensure Copilot + Inventory tools are in the Hub catalogue with correct role scopes. F2 Re-run the 60-task Hub eval plus 20 new cross-tool tasks (>= 3 tools). F3 Update docs/agent_hub.md demo script and screenshots section (capture screenshots only if a headless browser is available; otherwise leave a TODO listing the exact steps).
GATE F: green. Checkpoint commit.

=========================================================
PHASE G: Housekeeping, CI, docs consistency
=========================================================
G1 Docs must match code: fix docs/architecture.md (current Knowledge Assistant retrieval: FTS5 + optional embeddings with weighted fusion; shell mounts 13+ ASGI sub-apps; what PrefixApiPaths does; the new alpha_core/agent and auth modules). Update README: what's real vs simulated vs rule-based vs ML vs LLM, per project, in one table.
G2 Rename misleading labels everywhere (UI, README, agent cards, docs), URLs/slugs unchanged: Multi-Agent BI -> "BI Analyst Workflow"; Sales Nudge -> "Sales Follow-up Prioritizer"; Inventory Optimization -> merged into "Inventory Control Tower"; Segmentation -> "Customer Segmentation"; Observability -> "Incident Evidence Correlator (synthetic)"; Helpdesk -> "Helpdesk Triage". Do NOT label them agents.
G3 CI (.github/workflows): install pinned deps, ruff, mypy, seed synthetic fixtures, pytest, plus eval steps for: Knowledge Assistant retrieval benchmark (fail if Recall@5 or abstention accuracy regresses, or ACL leakage > 0), BI agent eval, Hub eval, Copilot eval, Inventory eval (fail on defined regressions; thresholds taken from the first real run minus a small tolerance, written in docs/eval/thresholds.json). Upload eval JSONs as artifacts. Matrix: Python 3.12 (+3.13 if deps allow) on ubuntu; add a Windows job that runs the fast test subset.
G4 Security hardening for new routes: CSRF on state-changing cookie-authenticated routes, rate limits, upload validation, log redaction, no stack traces in responses, CORS locked to same-origin, secure cookie flags configurable, security headers (CSP, X-Content-Type-Options, frame-ancestors). Add tests.
G5 Repo hygiene: .gitignore covers *.zip, instance/, DuckDB/SQLite files, generated data, models, caches; verify with `git ls-files` that none are tracked. seed_all script rebuilds every dataset/model/db from scratch (run it in a clean temp clone to prove a fresh clone works).
G6 Per-project docs complete for everything built in A to E: README, data card (+ entry in docs/data_register.md with source/licence/date/checksum or SYNTHETIC), model/agent card, threat model, runbook, 3-minute demo script. Add docs/CASE_STUDIES.md with an honest 1-page write-up per flagship (problem, user, architecture, what's real vs simulated, measured results copied from docs/eval/*, limitations).

=========================================================
PHASE H: Final self-audit (mandatory)
=========================================================
H1 Fresh-clone test: `git clone` the repo to a temp dir (or copy tracked files via git archive), create a venv, install, run seed_all, run the full test suite, ruff, mypy, JS check, start the app and call every /health plus the Hub, BI, Copilot and Inventory demo endpoints with the demo users. Record real output.
H2 Claim audit: grep README/docs/UI for claims (accuracy, "agent", "production", savings, "secure"); list each claim with the test or eval file backing it; remove or soften any claim without backing.
H3 Secret/data audit: scan tracked files for key-like strings, .env, *.db, *.duckdb, *.zip, model binaries; report results (don't print any secret values).
H4 Write docs/BUILD_REPORT.md: phases completed, files changed (grouped), tests/lint/type results (real numbers), eval results table (copied from eval files), security issues found and fixed, remaining limitations (be candid: e.g. LLM planner untested without Ollama, UI not browser-tested if so), explicit confirmation that nothing was pushed, and the exact commands for me to review (`git log --oneline`, `git diff main --stat`).
H5 Update docs/BUILD_STATE.md to "ALL PHASES COMPLETE" or the exact next action if you stopped early.

OUTPUT TO ME AT THE END
A concise summary: phase table (done/partial/skipped + why), real test/ruff/mypy counts, eval headline numbers, top 5 remaining risks, and what I should manually review first. Do not paste huge diffs. Do not push.

OUT OF SCOPE (do NOT start): the other 8 projects (observability/OTel, churn, sales forecast, sentiment, segmentation, supplier quotes, helpdesk, travel), merging to main, deploying, any real external integrations.
```

---

## If Codex stops early (context/time limit)

Paste exactly this and it resumes from the checkpoint file:

```
Read AGENTS.md and docs/BUILD_STATE.md. Continue the Alpha v2 master plan from the first unfinished phase, following all HARD RULES and the VERIFICATION LOOP from the master prompt (it's in docs/MASTER_PROMPT.md). Re-run the full tests first to confirm green. Do not redo completed phases. Do not push.
```
(So also save the box above as `docs/MASTER_PROMPT.md` in the repo before you start. Codex can then re-read it on resume.)

## After it finishes (you, 15 min)

1. Read `docs/BUILD_REPORT.md` first, then `git log --oneline` and `git diff main --stat`.
2. Run the app yourself: `run.ps1`, log in, try the Hub demo question, upload the sample CSV in Copilot, open Inventory Control Tower.
3. Check `docs/eval/*.md` numbers look real (not suspiciously perfect; 1.00 on templated data is a red flag).
4. Then `git push -u origin alpha-v2-build`, open a PR into `main`, merge when CI is green.
5. The remaining 8 projects come next as a second run (observability with OpenTelemetry first).
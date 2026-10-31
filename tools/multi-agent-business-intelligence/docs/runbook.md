# Runbook

## Start and sign in

From the Project Alpha folder run `powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1`. Bootstrap creates the fixed-seed synthetic warehouse if needed and starts the local Alpha site. Sign in to the Knowledge Assistant using the locally configured demo account; the BI API reuses that signed cookie and server-side user lookup.

## Use the workflow

Open `/tools/bi`. The page shows the planner mode, `SYNTHETIC DATA`, and `READ ONLY` badges. Ask about revenue by month or week, top products or categories, refund rates, anomalies, or regional totals. Ambiguous questions return a clarification. Unsupported or write requests are refused.

The API routes are `/tools/bi/api/agent/ask` and `/tools/bi/api/agent/runs/{run_id}`. The ask endpoint requires a unique `Idempotency-Key`. Its normal response includes the run ID, step trace, evidence IDs, planner mode, and only independently verified numeric rows.

## Local planner mode

`LLM_PROVIDER=none` is the default and uses deterministic routing. To try the optional local provider, configure the local Ollama adapter before starting Alpha with `LLM_PROVIDER=ollama`. No hosted or key-based provider is supported. The optional model path has not been evaluated in the current benchmark.

## Data and traces

Bootstrap or run `python -m tools.multi-agent-business-intelligence.scripts.seed_data` to recreate the synthetic order database. Runtime databases live below this tool's ignored `data/runtime` directory. `BI_DATABASE_PATH` and `ALPHA_BI_TRACE_PATH` can point to disposable local paths for development. Never put secrets, external data, or real customer information in this demo.

## Checks

Run BI tests with `python -m pytest tools/multi-agent-business-intelligence/tests -q`; run the measured gold set with `python -m tools.multi-agent-business-intelligence.scripts.evaluate_agent`. Evaluation output is written under `docs/eval`. Legacy `POST /tools/bi/api/ask`, `GET /tools/bi/api/trace`, and `/health` remain available.

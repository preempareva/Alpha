# BI Analyst Workflow

The BI Analyst Workflow answers bounded questions about a clearly labelled **SYNTHETIC** retail dataset. It is a real tool-using workflow: a deterministic planner (or optional local Ollama planner) proposes typed tool calls, the server checks every call against the registered catalogue and policy, and `verify_totals` independently recomputes each result before numbers are returned.

## Run it

From the Project Alpha folder, run `powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1`. The bootstrap creates the synthetic demo data. Open the BI Analyst Workflow from the Alpha site. Sign in through the Knowledge Assistant so the BI routes can resolve the signed server session.

The tool is mounted at `/tools/bi`. The legacy `POST /tools/bi/api/ask` and `GET /tools/bi/api/trace` routes remain available. The verified workflow adds:

- `POST /tools/bi/api/agent/ask` with `{"question":"Show monthly revenue"}` and a required `Idempotency-Key` header.
- `GET /tools/bi/api/agent/runs/{run_id}` for a run owned by the authenticated user.

The response includes the planner mode, bounded trace, limitations, evidence IDs, and verified data. Ambiguous asks return a clarification state. Unsupported and write requests are refused.

## Available analysis

The registered read-only catalogue covers revenue trends, top categories, top products, refund rates, monthly anomaly checks, regional totals, and an independent result verifier. SQL comes only from fixed query templates. Date and limit values are bound parameters; selected identifiers and metrics use allowlists. SQLite is opened read-only with `query_only`, an authorizer, a one-second progress deadline, a 20-row cap, and a SQLGlot SQLite AST check.

Planner mode defaults to `deterministic` with `LLM_PROVIDER=none`. Setting `LLM_PROVIDER=ollama` enables optional local planning through Alpha's shared adapter; malformed output is retried once and then falls back to deterministic routing. A model can propose tools but cannot grant permissions or issue SQL.

## Evaluation and limits

Run `python -m tools.multi-agent-business-intelligence.scripts.evaluate_agent` to create `docs/eval/bi_agent.json` and `.md`. The recorded run uses 40 hand-authored questions against the fixed-seed synthetic dataset, with LLM planning off and five deliberate numeric tamper attempts. The perfect scores describe only this small, templated benchmark; they do not estimate performance on real analysts or business data. Ollama was not evaluated.

The dataset and results are fictional. This demo is not validated for a real warehouse, production security, financial decisions, or business impact. The request endpoint currently has no explicit CSRF token or rate limiter; those are repository hardening work tracked for the later security phase.

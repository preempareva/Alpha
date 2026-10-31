# BI Analyst Workflow agent card

- **Purpose:** Answer supported retail analysis questions from a fixed synthetic dataset.
- **Identity:** The server resolves the signed Knowledge Assistant session and uses its database-resolved user and role. The request body and arbitrary headers never provide identity.
- **Planner:** Deterministic routing is the default. An optional local Ollama provider may propose a typed `AgentPlan`; the plan remains untrusted and falls back after one schema retry.
- **Tools:** `revenue_trend`, `top_categories`, `top_products`, `refund_rate`, `anomaly_check`, `region_breakdown`, and `verify_totals`.
- **Execution limits:** One selected analysis plus server-added verification (two steps per simple ask; five total is the runtime ceiling). Tools have role scopes, a 5-second runtime timeout, fixed SQL templates, bound date/limit values, 20-row cap, 100 KB result cap, SQLite read-only mode, authorizer, query-only mode, one-second SQL progress deadline, and a SQLGlot AST check.
- **Evidence:** Every analysis row carries the tool result ID. The verifier reads source rows independently and recomputes results. Numeric output is withheld if verification fails; failed run history also withholds raw tool results.
- **Side effects:** No write, external, purchase, or business action tools are registered.
- **Data:** Fixed-seed synthetic retail orders only. See [data card](data_card.md).
- **Evaluation:** 40 deterministic gold questions plus five tamper trials. See [the measured run](../../../docs/eval/bi_agent.md). The hand-authored synthetic benchmark is small and templated; perfect scores must not be generalized.
- **Known limitations:** No real warehouse connector, explicit CSRF token, request rate limiter, or Ollama evaluation. Current evidence only supports the recorded synthetic benchmark and unit tests.

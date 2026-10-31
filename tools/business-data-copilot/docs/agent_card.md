# Business Data Copilot agent card

## Summary

Business Data Copilot is a bounded analytics workflow with a deterministic default planner. It accepts a typed QueryPlan, validates every referenced field against the user's confirmed schema, compiles one allowlisted DuckDB SELECT, and compares the result with an independent pandas implementation.

The shared Agent Hub exposes two read tools:
- copilot.profile: caller-owned schema/profile fields, excluding sensitive columns and sample rows.
- copilot.query: a bounded natural-language question against the caller's confirmed dataset.

Both tools derive owner and workspace from the server-authenticated identity. Neither accepts caller-provided identity fields or writes external systems. Hub evidence is checked by re-running the query and comparing rows; Copilot itself has already compared each result against pandas.

## Planner modes

- Deterministic: default, offline, no model call.
- LLM-planned (local): opt-in with Ollama. It receives the question, confirmed nonsensitive schema, and sample-free statistics; the proposal must validate as a QueryPlan. The model never emits SQL or computes numbers. The server validates the plan and compiles all SQL.

## Boundaries

- One confirmed dataset per owner in the configured workspace.
- Uploads are capped at 50,000 rows; query output is capped at 500 rows.
- Aggregations: SUM, AVG, COUNT, COUNT DISTINCT, MIN, MAX.
- Only confirmed dimensions/date fields can be grouped; marked-sensitive fields cannot be grouped or filtered.
- Sensitive values may contribute only to explicit aggregate outputs, which use generic field labels.
- No mutation, arbitrary SQL, web access, or remote model provider.

See docs/eval/copilot.md for measured results. The benchmark is a small hand-authored synthetic template set and is not a general accuracy estimate.

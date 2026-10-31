# Threat model

## Assets and boundaries

The only business data is generated synthetic retail order data. The route resolves the existing signed Knowledge Assistant session and uses a database-resolved user and role; `Idempotency-Key` is only a replay key. Trace reads are scoped by that authenticated identity. Each user is assigned an isolated demo workspace keyed from the server-resolved user ID.

## Untrusted input and planner output

Question text and all optional local-model output are untrusted. Deterministic preflight rejects write attempts, prompt-injection patterns, unsupported data requests, and out-of-range input before the local planner is called. An LLM can return only a typed plan. The server replaces the report goal, appends the verifier, and the runtime checks registered tools, role, workspace, schema, side-effect class, timeout, result size, and row bounds immediately before dispatch.

## Data access and query safety

No free-form SQL reaches SQLite. Code selects fixed SQL templates; date ranges and limits are bound parameters; metric and grouping identifiers map to fixed strings. SQLGlot checks one SQLite SELECT against the table, column, wildcard, and function allowlists. SQLite opens with `mode=ro`, `PRAGMA query_only=ON`, a restrictive authorizer, a one-second progress handler, and a 20-row result cap. The independent Python verifier reads only the same synthetic order source and must match the tool result before numeric data is returned.

## Fail-closed behavior and remaining risks

Unsupported requests are refused; ambiguous requests ask for clarification. Tool errors return safe error codes. An unverified result is withheld from the ask response and from later run-history reads. Trace storage uses the shared runtime's redaction, per-field/per-run size limits, and retention controls. Data and trace SQLite files are generated under ignored runtime paths.

The app has no explicit CSRF token or rate limiter on the BI POST route yet, and the demo has not had an external penetration test. Keep it on the local Alpha host. The synthetic benchmark is too small to establish real-world accuracy or robustness. No real warehouse or write integration is present.

# Business Data Copilot threat model

## Assets

- Signed-in user and configured workspace identity.
- User-uploaded files while they are parsed, staged, and stored.
- Confirmed schema and per-column sensitivity choices.
- Query results, provenance, and redacted audit metadata.

## Trust boundaries and controls

| Threat | Control |
|---|---|
| Forged identity in body or headers | Identity is resolved by the existing signed Knowledge Assistant cookie and active server-side user record; Copilot ignores custom identity headers |
| Cross-user or cross-workspace access | Workspace directory is keyed by a workspace hash; manifest reads require owner and workspace hashes; table name is derived from the authenticated owner; previews and export cache are owner-scoped |
| Malicious or oversized uploads | Extension allowlist, byte/row/column/cell limits, strict encodings, XLSX signature/member/path/size checks, macro/external/embedded-object rejection |
| Formula execution | XLSX is opened with formulas retained as text and is never recalculated; CSV formula-like strings are ordinary text |
| SQL injection | User values are bound parameters; table/column identifiers are generated and allowlisted; SQLGlot accepts one SELECT and rejects unsupported functions, joins, subqueries, and commands |
| Planner prompt injection | Requests are preflighted; model output is only a typed plan; uploaded names are untrusted identifiers; no SQL or code is accepted from the model |
| Sensitive data disclosure | Sensitive fields are excluded from optional planner schema, Hub profile, confirmed preview, dimensions, filters, and result labels. Explicit aggregates run deterministically and use generic output labels |
| Incorrect result | Query rows are withheld unless an independent pandas aggregation agrees; result row and byte caps apply |
| Spreadsheet formula injection on export | Text cells starting with equals, plus, minus, at-sign, tab, or carriage return are prefixed with an apostrophe; numeric values stay numeric |
| CSRF and request floods | Session-bound signed CSRF is required on upload/demo/schema/query mutations; shared per-user Alpha Hub rate limiter applies |
| Long-lived data | Confirmed dataset retention is 30 days, redacted query audit retention is 90 days, preview and export caches are time-bounded |

## Residual risks and limits

- Copilot does not encrypt DuckDB data or local audit metadata at rest. Host disk and account controls remain responsible for storage security.
- Preview staging and query export caching are in process memory. The configured Alpha launcher runs one local process; multi-worker deployments are not supported.
- Column typing is heuristic. A query can be technically verified but still answer a misinterpreted question; the UI shows the plan, assumptions, and provenance.
- A local Ollama model is optional and is not part of the default verification run. Sensitive column names explicitly mentioned by the user are handled deterministically so they are not sent to the local model.
- The default 10 MiB upload size and in-memory pandas verification are intended for small files, not a warehouse workload.

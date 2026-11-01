# Project Alpha architecture

## Workspace layout

```mermaid
flowchart TD
    Browser --> Shell[alpha_app.main<br/>workspace, auth boundary, health, weather]
    Shell --> Hub[Agent Hub router<br/>/api/agent/*]
    Shell --> P[14 mounted FastAPI project apps<br/>/tools/{slug}/*]
    Hub --> Registry[ToolRegistry + PolicyEngine]
    Registry --> Runtime[BoundedExecutor + TraceStore]
    Runtime --> Tools[BI, Knowledge, scoring, demand,<br/>Copilot, Inventory reads]
    Runtime --> Approvals[Persisted approvals<br/>draft-only inventory actions]
    Shell --> Static[static/index.html + modular JS/CSS]
```

The root app in `alpha_app/main.py` mounts fourteen ASGI sub-applications under stable `/tools/{slug}` prefixes. The slug list is defined in `PROJECTS`; display labels can change without changing route prefixes. The shell also serves the workspace home page, health endpoints, shared static modules, and the Hub router.

`PrefixApiPaths` is middleware added to each mounted sub-app. For HTML responses only, it rewrites root-relative `href` values and quoted `/api/` references to include that tool's `/tools/{slug}/` prefix. It does not rename routes, rewrite JSON responses, or alter JavaScript asset URLs. This keeps older project pages working when mounted below the workspace root.

## Shared modules

- `alpha_core/agent/` contains the typed plan and tool contracts, registry snapshots, role/side-effect policy, bounded executor, persisted approval records, idempotency handling, and trace store. The Hub only dispatches fixed registered handlers; it does not execute model-provided code, SQL, or shell commands.
- `alpha_core/auth.py` provides the signed-session and user-bound CSRF codecs used with the Knowledge Assistant's server-resolved user records. The browser does not supply authoritative roles, groups, user IDs, or workspace IDs.
- `alpha_core/llm.py` is the only LLM adapter. `LLM_PROVIDER=none` is the default. Optional Ollama planning is local, bounded, schema-checked, and falls back to deterministic planning.
- `alpha_app/agent_hub.py` registers the read tools and the inventory draft tools, resolves current identity, enforces CSRF/rate limits on state-changing Hub routes, records evidence, and checks results before returning them.
- `alpha_app/bootstrap.py` builds missing ignored demo assets from source scripts. `scripts/seed_all.py` provides the clean-checkout entry point for rebuilding them.

## Browser and error boundaries

The browser UI is served from the same origin as the APIs. Alpha does not emit permissive CORS headers; cross-origin browser reads are not enabled. The shell applies a content security policy, frame denial, MIME sniffing protection, same-origin referrer/resource policies, and a restrictive permissions policy to mounted app responses. Unhandled exceptions return a generic error with a request ID; logs contain the exception class and request ID, not exception text or user payloads. The same generic handler is installed on mounted project apps. The Knowledge Assistant session cookie is HttpOnly, SameSite=Lax, and adds Secure when `ALPHA_HTTPS=1`.

Hub and Copilot state-changing APIs require user-bound CSRF tokens and share a process-local per-user rate limiter. Copilot upload endpoints enforce body and file limits, extension and content checks, and spreadsheet member restrictions. Some legacy standalone endpoints have narrower controls, as called out in their threat models; Alpha is intended to bind to localhost and has not had an external penetration test.

## Knowledge retrieval

The Knowledge Assistant uses SQLite FTS5 with BM25-style lexical ordering as its deterministic baseline. Optional local Ollama embeddings add a vector score. When vectors are available, the fusion score is `0.6 * lexical + 0.4 * normalized_vector`; without vectors, retrieval stays lexical. Active-document, effective-date, and access-group filters are applied in the retrieval query. Answer synthesis is disabled by default; citations and abstention are returned from the retrieved evidence.

## Project routes

| Workspace path | Product |
|---|---|
| `/tools/copilot` | Business Data Copilot |
| `/tools/knowledge` | Knowledge Assistant |
| `/tools/helpdesk` | Helpdesk Triage |
| `/tools/travel` | Travel Itinerary Planner |
| `/tools/demand` | Demand Forecasting |
| `/tools/churn` | Customer Churn Prediction |
| `/tools/sales-forecast` | Sales Pipeline Forecast |
| `/tools/sentiment` | Customer Sentiment Insights |
| `/tools/bi` | BI Analyst Workflow |
| `/tools/replenishment` | Inventory Control Tower |
| `/tools/sales-nudge` | Sales Follow-up Prioritizer |
| `/tools/incidents` | Incident Evidence Correlator (synthetic) |
| `/tools/quotes` | Supplier Quote Comparison |
| `/tools/segments` | Customer Segmentation |

The `demand` and `replenishment` applications keep their previous route prefixes and legacy APIs. The combined Inventory Control Tower screen is served from the `replenishment` app.

## Data and side effects

The BI, Knowledge Assistant starter corpus, demand, model-training fixtures, and Inventory Control Tower datasets are generated fictional examples. Copilot can analyze a signed-in user's local CSV/XLSX upload; confirmed uploads are owner/workspace scoped in a local DuckDB store, which is not encrypted at rest. Weather lookup is the only live external data request and is initiated by the user.

Inventory Hub writes stop at a local proposal ledger. Creating a replenishment draft and recording a simulated execution each require a persisted approval. Neither action sends a purchase order, supplier message, or external-system write. Other Hub tools are read-only. The legacy standalone Helpdesk review route and older BI route have narrower protections than the shared Hub; see the tool threat models before exposing the local app beyond localhost.

## Verification

The root `/health` reports each mounted project's readiness. Project tests live in the corresponding `tools/*/tests` folders or the root `tests/` folder. Offline evaluation artifacts and their limits are under `docs/eval/`; CI compares each run with `docs/eval/thresholds.json`. See `docs/agent_hub.md` for the cross-tool flow and identity/approval rules.

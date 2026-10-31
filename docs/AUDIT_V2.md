# Project Alpha audit v2

## Scope

This audit covers only Project Alpha source and its fictional demos. It excludes APEX and all employer or organization systems. No credentials, user databases, uploaded files, logs, or model binaries were inspected.

## Current foundation

- The shell imports and mounts 13 FastAPI ASGI sub-applications under stable `/tools/<slug>/` paths. `PrefixApiPaths` adjusts root-relative links and `/api/` fetch URLs in legacy HTML so they continue working below each prefix.
- Shared settings default to `LLM_PROVIDER=none`; the optional adapter uses local Ollama. Deterministic paths remain available without a model.
- Knowledge Assistant identity, roles, and groups come from a signed server-side session. Retrieval filters active, effective documents by server-resolved groups before returning evidence.
- Knowledge retrieval uses SQLite FTS5 and optional local Ollama embeddings. When embeddings are available, lexical and cosine ranks combine at weights 0.6 and 0.4. If embedding calls fail or the provider is disabled, retrieval falls back to FTS5.
- CI builds the synthetic churn and sentiment models before running tests; those generated artifacts are intentionally excluded from Git.

## Phase 1 work

This phase standardizes product labels, documents current shell and retrieval behavior, adds an allowlisted policy-checked tool runtime with bounded asynchronous execution and SQLite traces, and adds runtime security tests plus retrieval evaluation to CI.

The runtime takes a server-created identity and a typed plan of at most five calls. Only explicitly registered async handlers can run. Policy is rechecked immediately before each attempt for identity, role, optional workspace allowlist, handler module, JSON arguments, side effect, and approval. Tool timeouts are capped at 60 seconds, transient retries at one, and results at declared row and byte limits. Write/external tools require approval. Runs can pause on approval and resume only with the same identity, workspace, and plan. The trace stores each run/step state in SQLite. No existing demo endpoint is automatically exposed as a tool.

## Remaining product gaps

- The BI demo is a deterministic, fixed-tool workflow. It does not plan tools with an LLM.
- Inventory forecasting and replenishment remain separate demos. Their synthetic assumptions do not model a full purchasing control tower.
- Churn, sentiment, sales, and segmentation use synthetic data and do not establish real-world outcomes, causal impact, or deployment readiness.
- Travel weather is an explicit live Open-Meteo lookup; other demo inputs are synthetic or locally generated.
- The new tool runtime is a library foundation. Existing routes are not automatically converted into tools in this phase; each future registration must declare schemas, roles, workspace limits, side effects, and approval requirements.

## Later phases

The next candidate phases are a synthetic Business Data Copilot, an integrated Inventory Control Tower, an Alpha Agent Hub, and one-at-a-time evaluation improvements for the remaining demos. Each phase needs its own review and green checks before integration.

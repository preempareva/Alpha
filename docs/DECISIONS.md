# Decisions

## Scope and instruction conflicts

- The master plan asks for Phases A–H, while its out-of-scope section prohibits starting eight existing projects. Work will focus on the explicitly scoped runtime, BI workflow, Hub, Copilot, and Inventory Control Tower. No new feature work will be started in the eight excluded projects.
- Product-label edits to the excluded projects were already present from the earlier authorized Prompt 1 task when this master prompt began. Preserve these inherited edits and their existing routes; do not expand their functionality.
- The supplied prompt assigns ZIP deletion and key rotation to the user. Do not inspect archives, credentials, or employer materials. The repository ignore rule already excludes ZIP files.
- No pre-hardening commit existed when this prompt arrived. Continue on a dedicated alpha-v2-build branch and checkpoint only after a phase gate passes. Never push or merge.
- Repo-wide Ruff currently reports 114 findings in legacy project files. New and touched core code must pass scoped Ruff; do not mass-reformat excluded applications to reduce the baseline count.
- Keep all new runtime and evaluation behavior functional with LLM_PROVIDER=none; Ollama remains optional.
- The Knowledge Assistant now attaches its configured `ALPHA_WORKSPACE_ID` (default `alpha-demo`) to the server-resolved principal. Non-admin run reads remain owner-only; admins can inspect runs and approvals within that shared workspace. The workspace is never accepted from request data.
- The Hub uses that configured shared workspace rather than a user-derived workspace. This lets an authorized same-workspace admin review an employee's persisted approval, while the saved plan is resumed with the original active requester identity and current groups.
- Hub evidence is cached in process only while a run needs verification or approval, bounded to 256 runs and 15 minutes. A process restart can make a paused run unverifiable; it fails closed rather than trusting incomplete evidence.
- Agent Hub CSRF tokens are signed and user-bound with a separate serializer salt. The Hub UI and API are same-origin; its current rate limiter is a single-process sliding window, suitable for the local shell but not a multi-worker deployment.
- Run BI's deterministic safety preflight before optional local planning. Unsupported or write-oriented prompts are refused before any model call, while an accepted model proposal remains subject to the runtime registry and policy.

## Phase D decisions

- Copilot stores workspace DuckDB files under an opaque hash derived from the server-configured workspace ID. Tables and manifests are separately scoped to a hash of the authenticated user ID.
- Upload previews remain in process memory for 15 minutes until schema confirmation. Staging is capped at 100 MiB process-wide; confirmed data is retained for 30 days, and redacted query audit metadata for 90 days.
- Marked-sensitive fields do not appear in optional local planner schemas, Hub profiles, confirmed previews, groups, filters, result labels, or query audit plans. Explicit sensitive aggregates are handled deterministically and use generic output aliases.
- XLSX formulas are read as formula text, not evaluated. Macro projects, external links, embedded objects, unsafe paths, and oversized expanded archives are rejected.
- Copilot's local Ollama planner requires COPILOT_LOCAL_PLANNER=1 in addition to the shared local provider configuration; default behavior is deterministic and offline.
- Copilot files are not encrypted at rest. This residual risk is called out in the data card and threat model; host filesystem protection remains the local operator's responsibility.

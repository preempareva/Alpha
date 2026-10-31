# Decisions

## Scope and instruction conflicts

- The master plan asks for Phases A–H, while its out-of-scope section prohibits starting eight existing projects. Work will focus on the explicitly scoped runtime, BI workflow, Hub, Copilot, and Inventory Control Tower. No new feature work will be started in the eight excluded projects.
- Product-label edits to the excluded projects were already present from the earlier authorized Prompt 1 task when this master prompt began. Preserve these inherited edits and their existing routes; do not expand their functionality.
- The supplied prompt assigns ZIP deletion and key rotation to the user. Do not inspect archives, credentials, or employer materials. The repository ignore rule already excludes ZIP files.
- No pre-hardening commit existed when this prompt arrived. Continue on a dedicated alpha-v2-build branch and checkpoint only after a phase gate passes. Never push or merge.
- Repo-wide Ruff currently reports 114 findings in legacy project files. New and touched core code must pass scoped Ruff; do not mass-reformat excluded applications to reduce the baseline count.
- Keep all new runtime and evaluation behavior functional with LLM_PROVIDER=none; Ollama remains optional.

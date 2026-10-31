# Build state

Updated: 2026-11-01

## Baseline

Baseline was run on branch alpha-v2-build before changes for this master plan. The existing Prompt 1 work was already present as an uncommitted working-tree diff and is included in this baseline.

- Full tests: **63 passed**, 6 dependency deprecation warnings.
- Repo-wide Ruff: **failed**, 114 findings across legacy tool folders.
- Mypy: **passed**, 10 configured source files, no issues.
- JavaScript syntax: **passed**, node --check static/app.js.
- Retrieval eval: last run in the previous task passed its recorded synthetic-corpus thresholds (Recall@5 0.977, abstention 1.0, ACL leakage 0); rerun during Phase G/H verification.

## Phase checklist

- [x] Phase A — Agent runtime hardening. Gate passed: 75 full-suite tests; 23 runtime tests; 12 Knowledge Assistant auth/access tests; scoped Ruff passed for core, app shell, and changed auth/runtime modules; mypy passed across 12 core source files; JavaScript syntax passed.
- [ ] Phase B — BI Analyst Workflow tool-using agent (in progress).
- [ ] Phase C — Alpha Agent Hub.
- [ ] Phase D — Business Data Copilot.
- [ ] Phase E — Inventory Control Tower.
- [ ] Phase F — Hub wiring and expanded evaluation.
- [ ] Phase G — Housekeeping, CI, docs consistency.
- [ ] Phase H — Final self-audit and fresh-clone verification.

## Phase A notes

The runtime no longer accepts caller-supplied approved call IDs or approval callbacks. It now uses persisted, single-use approval records, canonical saved plans, immutable registry snapshots, identity-scoped trace reads, per-step idempotency contexts, atomic run/step claims, read-only retry rules, bounded/redacted traces, correlation IDs, and retention cleanup. The Knowledge Assistant now uses the shared signed-session codec without changing its cookie claims or server-side user lookup.

Repo-wide Ruff remains at the recorded legacy baseline scope; no excluded app was mass-reformatted. Full scoped Ruff checks passed for all changed Python code.

## Next action

Complete Phase B1: add Planner, DeterministicPlanner, and LLMPlanner interfaces with schema validation, one parse retry, and deterministic fallback; then register BI's bounded read-only tools and keep the existing BI routes intact.

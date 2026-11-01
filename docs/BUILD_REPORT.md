# Project Alpha build report

## Verification scope

Phase H verified the committed Phase G source (`e0472ed`) from a fresh temporary checkout outside the project workspace. The checkout used an isolated Python 3.14 virtual environment and installed `requirements.lock`. `PYTHON_DOTENV_DISABLED=1` and `LLM_PROVIDER=none` were set for fixture generation, evaluations, tests, and app smoke checks. Generated data, databases, model artifacts, and server logs remained in the temporary checkout; no live weather request was made.

## Gates

| Gate | Result |
|---|---|
| Clean-checkout `scripts.seed_all` | Passed; generated every expected path and did not inspect generated contents |
| Knowledge Assistant retrieval evaluation | Passed thresholds; 127 authored cases, Recall@5 0.977, abstention 1.000, ACL leakage 0, expired-version leakage 0 |
| BI Analyst Workflow evaluation | Passed; 40 cases, tool/argument/numeric/refusal/verifier metrics 1.000, 5/5 tamper catches |
| Business Data Copilot evaluation | Passed; 40/40 numeric questions, 4/4 refusals, 5/5 tamper catches |
| Agent Hub evaluation | Passed; 80 tasks, 20 cross-project tasks, all reported selection/argument/completion/trace/refusal/policy checks 1.000, 5/5 BI tamper catches |
| Inventory Control Tower evaluation | Passed; six tables valid, 36 metric groups, six scenarios, selected models `naive` (intermittent) and `ets` (seasonal) |
| Central evaluation thresholds | Passed against fresh reports |
| Full pytest suite | **160 passed**, 7 dependency deprecation warnings |
| Ruff | Passed for the maintained/shared, flagship, and changed-test scopes |
| Mypy | Passed: shared 14 files, BI 6, Copilot 11, Inventory 6 |
| Dependency consistency and JavaScript | `pip check` passed; all 4 tracked JavaScript files passed `node --check` |
| Running application/API smoke | Passed: 14/14 root health entries, workspace home/catalogue, BI/Copilot/Knowledge/Inventory health, inventory backtest, BI read-only demo, and three unauthenticated access checks |
| Repository hygiene and source scan | 0 tracked database/generated-runtime/model-binary/secret-path files; 0 high-confidence credential-pattern matches in tracked source |

Evaluation numbers are for authored or fixed-seed synthetic fixtures. They do not estimate accuracy on arbitrary user requests, real organizations, or live data. Timing is environment-dependent and is not a service-level target.

## Remaining limits

- The current machine has Python 3.14 only. The workflow targets Python 3.12 and 3.13, but those hosted runners have not executed yet.
- The Windows fast-test job is configured but was not run here.
- Browser automation and screenshots remain unverified; the environment has no installed Playwright/browser runner.
- The local Knowledge Assistant accounts are not an enterprise identity provider. Copilot and the inventory draft ledger are not encrypted at rest. Some legacy standalone routes have narrower CSRF/rate-limit protections; the shell Hub and Copilot write flows have explicit CSRF and rate limits.
- Ollama planning and embedding providers were disabled for this build gate. The only live integration is the user-triggered Open-Meteo lookup, which was not called.
- No external penetration test or production deployment validation has been performed. The documented scope remains a localhost demonstration.

## Review order

1. Start the application and review the Alpha landing page, product labels, and flagship workflows.
2. Read [the architecture](architecture.md), [case studies](CASE_STUDIES.md), and each flagship's local data/security limits.
3. Review [the CI workflow](../.github/workflows/ci.yml), especially its not-yet-run hosted Python/Windows matrix.
4. Inspect [the evaluation tolerances](eval/thresholds.json) before changing benchmark cases or metrics.

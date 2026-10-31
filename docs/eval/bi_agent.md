# BI Analyst Workflow evaluation

This run uses a fixed-seed SYNTHETIC retail dataset and `LLM_PROVIDER=none`. Expected values are calculated in this script from source rows with independent Python aggregation. Ollama evaluation was not run.

| Metric | Result |
|---|---:|
| Gold questions | 40 |
| Tool sequence accuracy | 1.0 |
| Argument accuracy | 1.0 |
| Numeric correctness | 1.0 |
| Refusal and clarification correctness | 1.0 |
| Verifier tamper catch rate | 1.0 |
| Latency p50 (ms) | 11.841 |
| Latency p95 (ms) | 18.733 |

The run evaluated 30 supported asks and 10 refusal or clarification cases. The verifier was challenged with 5 modified numeric results; it withheld unverified output in 5 cases.

Per-question expected/actual tool sequence, argument match, numeric correctness, and latency are recorded in `bi_agent.json`. No external data or real business claims are included.

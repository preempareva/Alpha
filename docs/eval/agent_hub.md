# Alpha Agent Hub evaluation

Measured: `2026-10-31T20:35:44.727589+00:00`. Planner mode: `none`. Ollama: not run.

The run used 60 real Hub/runtime trials against generated synthetic project assets. The report stores plans, tool names, status, timings, and aggregate scores, but no result rows or customer content.

| Metric | Measured result |
|---|---:|
| Tool-selection accuracy (40 normal tasks) | 1.0000 |
| Argument accuracy (40 normal tasks) | 1.0000 |
| End-to-end success (40 normal tasks) | 1.0000 |
| Correct refusals (12 ambiguity/unsupported/injection tasks) | 1.0000 |
| Policy-denial correctness (6 policy tasks) | 1.0000 |
| Trace completeness (48 execution tasks) | 1.0000 |
| p50 latency across 60 tasks | 12.065 ms |
| p95 latency across 60 tasks | 212.090 ms |
| BI tamper trials caught | 5/5 |

## Limits

This is a hand-authored, synthetic-data benchmark. Tool and argument accuracy measure only the listed prompts; the results do not estimate performance on arbitrary user requests or real business data. P50/p95 include planner refusals and short runtime policy fixtures. The timeout case intentionally waits for its one-second tool limit. The verifier tamper trials independently recompute BI values from the synthetic source; non-BI demo scores are re-run through their fixed scoring functions rather than an independent model implementation. LLM planning and Ollama were not tested.

## Reproduce

```powershell
$env:LLM_PROVIDER = 'none'
..\.venv\Scripts\python.exe -m scripts.evaluate_agent_hub
```

Per-task metadata and failure classifications are in `agent_hub.json`; no generated data values are included.

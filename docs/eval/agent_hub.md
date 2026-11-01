# Alpha Agent Hub evaluation

Measured: `2026-10-31T21:48:34.912405+00:00`. Planner mode: `none`. Ollama: not run.

The run repeated the original 60-task benchmark and added 20 cross-project Hub/runtime trials, for 80 total, against generated synthetic project assets. The report stores plans, tool names, status, timings, and aggregate scores, but no result rows or customer content.

| Metric | Measured result |
|---|---:|
| Original benchmark tasks | 60 |
| Tool-selection accuracy (40 original normal tasks) | 1.0000 |
| Argument accuracy (40 original normal tasks) | 1.0000 |
| End-to-end success (40 original normal tasks) | 1.0000 |
| Cross-project tasks (four source tools each) | 20 |
| Cross-project tool-selection accuracy | 1.0000 |
| Cross-project argument accuracy | 1.0000 |
| Cross-project end-to-end success | 1.0000 |
| Cross-project trace completeness | 1.0000 |
| Correct refusals (12 ambiguity/unsupported/injection tasks) | 1.0000 |
| Policy-denial correctness (6 policy tasks) | 1.0000 |
| Trace completeness (68 execution tasks) | 1.0000 |
| p50 latency across 80 tasks | 16.399 ms |
| p95 latency across 80 tasks | 1360.447 ms |
| BI tamper trials caught | 5/5 |

## Limits

This is a hand-authored, synthetic-data benchmark. The 20 cross-project cases each run inventory risk ranking, position, and forecast alongside one BI analysis, then verify all four results. Tool and argument accuracy measure only the listed prompts; the results do not estimate performance on arbitrary user requests or real business data. P50/p95 include planner refusals and short runtime policy fixtures. The timeout case intentionally waits for its one-second tool limit. The verifier tamper trials independently recompute BI values from the synthetic source; non-BI demo scores are re-run through their fixed scoring functions rather than an independent model implementation. LLM planning and Ollama were not tested.

## Reproduce

```powershell
$env:LLM_PROVIDER = 'none'
..\EXtra\project-alpha-support\.venv\Scripts\python.exe -m scripts.evaluate_agent_hub
```

Per-task metadata and failure classifications are in `agent_hub.json`; no generated data values are included.

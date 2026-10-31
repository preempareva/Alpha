# BI Analyst Workflow

A controlled analyst workflow over a small synthetic retail dataset. A router selects from fixed, typed analysis tools; a read-only SQLite analyst executes parameterized queries; an independent verifier checks row shape and totals; a report writer summarizes the verified result. It does not generate arbitrary SQL, mutate data, or take business actions.

## Run in Alpha

Open the unified workspace from project-alpha with powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1. This tool opens as a workflow inside the Alpha site at http://127.0.0.1:8000.

## Limits

The sample is fictional. The workflow uses deterministic intent routing rather than an LLM planner, so unsupported questions are rejected. Query allowlists, query-only connection mode, authorizer restrictions, row limits, and a step budget bound the analysis. This does not establish production security, real business impact, or validity for a real dataset.





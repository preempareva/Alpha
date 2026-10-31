# Inventory Control Tower

Combined synthetic workflow extending the existing demand and replenishment projects. It validates six reproducible data tables, compares naive, seasonal naive, moving-average, Statsmodels ETS and intermittent Croston SBA forecasts, and reports rolling-origin WAPE, MASE, bias and empirical interval coverage. The optional pooled LightGBM challenger is import-guarded.

The interactive screen at the existing `replenishment` slug includes risk ranking, weekly demand bands, stock position, scenario comparisons, constrained transfer options, proposal lists and persisted approval queues. Both legacy replenishment endpoints remain available: `GET /api/backtest` and `POST /api/recommend`. The separate demand app remains mounted at its old slug with its original `/api/forecast/{sku}` and `/api/backtest/{sku}` routes.

Replenishment calculation uses Decimal quantities/costs, explicit supplier MOQ and pack rules, a budget cap, and maximum-stock constraints. `inventory.propose_replenishment` requires a Phase A persisted approval before saving a draft. `inventory.simulate_execution` requires another persisted approval and only records a local idempotent simulation. No order, supplier message or external system is written.

## Run in Alpha

From `ai projects/project-alpha`, run `./run.ps1`. Alpha bootstrap creates the ignored fixed-seed demo tables as needed. This tool opens inside the Alpha site at http://127.0.0.1:8000.

## Limits

All data and cost assumptions are synthetic. Scenario metrics and forecast coverage only describe the recorded fixed-seed benchmark. They are not real forecasts, savings claims, or optimal policy recommendations. The local SQLite draft ledger is not encrypted at rest; do not place confidential or operational data in it. See `docs/data_card.md`, `docs/model_card.md`, `docs/threat_model.md`, `docs/runbook.md`, and `docs/inventory_formulas.md`.

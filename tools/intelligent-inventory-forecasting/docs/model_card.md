# Legacy demand forecast card

- **Route:** The original `demand` slug and `/api/forecast/{sku}` and `/api/backtest/{sku}` endpoints remain available.
- **Unified workflow:** The user-facing inventory workflow now lives at the existing replenishment slug under **Inventory Control Tower**.
- **Data:** Existing forecast API still reads its ignored fixed-seed synthetic `demand.csv`; it has no stock-on-hand or supplier truth.
- **Limits:** This legacy endpoint retains its simple moving-average baseline and is not an operational forecast. The combined tower's model comparison, rolling-origin evaluation and empirical intervals are documented in `tools/inventory-optimization-agent/docs/model_card.md` and `docs/eval/inventory_forecast.md`.

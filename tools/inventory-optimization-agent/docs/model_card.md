# Inventory Control Tower model card

- **Status:** Synthetic demonstration. It is not trained or validated on operational data.
- **Panel:** Fixed-seed weekly sales for 24 fictional SKUs at three fictional locations, with a 104-week generated horizon, intermittent items, seasonality, promotions, supplier delays and stock constraints.
- **Forecast candidates:** Naive, 52-week seasonal naive, eight-week moving average, additive-trend ETS from Statsmodels, and Croston SBA for intermittent demand. A pooled LightGBM challenger is optional and import-guarded.
- **Selection:** Rolling-origin evaluation at three cutoffs and four horizons. Model selection is segment-specific by aggregate WAPE; the simplest candidate within 2% of the best score is retained. The current benchmark and selected model are in `docs/eval/inventory_forecast.json`.
- **Intervals:** Training-only empirical residual quantiles from rolling moving-average errors. The evaluation reports realized 10–90% coverage by segment and horizon; the bands are not assumed to be calibrated on real data.
- **Inventory logic:** Decimal-based deterministic ATP, position, service-level safety stock, reorder point, MOQ/pack/budget/max-stock limits and transfer feasibility. Full definitions are in `docs/inventory_formulas.md`.
- **Actions:** Proposals and simulated execution use the Phase A persisted approval runtime. Simulation only updates a local synthetic ledger; no order, email, supplier request, ERP write or external effect is possible.
- **Limits:** No stockout censoring, actual replenishment constraints, actual supplier commitments, verified costs, policy fit, or evidence of service or savings impact. No live decisions should use these scores.

# Inventory Control Tower forecast evaluation

Generated: 2026-10-31

SYNTHETIC; fixed-seed generator; no live inventory or supplier data; local deterministic evaluation.

## Data quality

- Validator: **passed** across 6 tables.
- Synthetic rows: 7,736 across six tables.

## Model selection

Selection rule: lowest aggregate WAPE; select the simplest model within 2% of the best score.

| Demand segment | Selected model |
|---|---|
| intermittent | naive |
| seasonal | ets |

The comparison includes naive, seasonal naive, eight-week moving average, statsmodels ETS, and Croston SBA for intermittent demand. The optional LightGBM global challenger is guarded and runs only when the package is installed. The selected model per segment is computed from aggregate WAPE; models within 2% of the best score are tie-broken toward the simplest baseline.

## Rolling-origin metrics

Cutoffs are 26, 13, and 6 weeks before the end of the series. Metrics are grouped by segment and horizon; residual bands are recalibrated using training-only rolling moving-average residuals at each cutoff.

| Segment | Horizon | Model | n | WAPE | MASE | Bias units | 10–90 coverage |
|---|---:|---|---:|---:|---:|---:|---:|
| intermittent | 1 | croston_sba | 36 | 1.517 | 0.809 | 0.74 | 0.944 |
| intermittent | 1 | ets | 36 | 1.450 | 0.773 | 0.78 | 0.944 |
| intermittent | 1 | moving_average | 36 | 1.483 | 0.791 | 0.56 | 0.889 |
| intermittent | 1 | naive | 36 | 1.208 | 0.645 | 0.31 | 0.750 |
| intermittent | 1 | seasonal_naive | 36 | 1.042 | 0.556 | -1.53 | 0.806 |
| intermittent | 2 | croston_sba | 36 | 1.179 | 1.006 | -1.26 | 0.833 |
| intermittent | 2 | ets | 36 | 1.183 | 1.009 | -1.23 | 0.833 |
| intermittent | 2 | moving_average | 36 | 1.193 | 1.018 | -1.44 | 0.778 |
| intermittent | 2 | naive | 36 | 1.099 | 0.938 | -1.69 | 0.639 |
| intermittent | 2 | seasonal_naive | 36 | 1.057 | 0.902 | -2.25 | 0.694 |
| intermittent | 4 | croston_sba | 36 | 1.254 | 0.820 | -0.01 | 0.917 |
| intermittent | 4 | ets | 36 | 1.236 | 0.808 | 0.02 | 0.917 |
| intermittent | 4 | moving_average | 36 | 1.206 | 0.788 | -0.19 | 0.889 |
| intermittent | 4 | naive | 36 | 1.347 | 0.880 | -0.44 | 0.639 |
| intermittent | 4 | seasonal_naive | 36 | 1.170 | 0.765 | -2.11 | 0.750 |
| intermittent | 6 | croston_sba | 36 | 2.275 | 0.718 | 2.10 | 0.972 |
| intermittent | 6 | ets | 36 | 2.284 | 0.721 | 2.13 | 0.972 |
| intermittent | 6 | moving_average | 36 | 2.137 | 0.675 | 1.92 | 0.944 |
| intermittent | 6 | naive | 36 | 2.479 | 0.782 | 1.67 | 0.667 |
| intermittent | 6 | seasonal_naive | 36 | 2.972 | 0.938 | 3.03 | 0.611 |
| seasonal | 1 | ets | 180 | 0.374 | 0.813 | 0.92 | 0.800 |
| seasonal | 1 | moving_average | 180 | 0.381 | 0.829 | 0.85 | 0.778 |
| seasonal | 1 | naive | 180 | 0.414 | 0.900 | 0.30 | 0.728 |
| seasonal | 1 | seasonal_naive | 180 | 0.428 | 0.932 | 0.41 | 0.711 |
| seasonal | 2 | ets | 180 | 0.334 | 0.753 | 0.65 | 0.800 |
| seasonal | 2 | moving_average | 180 | 0.340 | 0.764 | 0.59 | 0.772 |
| seasonal | 2 | naive | 180 | 0.396 | 0.890 | 0.04 | 0.728 |
| seasonal | 2 | seasonal_naive | 180 | 0.408 | 0.918 | 0.12 | 0.717 |
| seasonal | 4 | ets | 180 | 0.353 | 0.779 | 0.76 | 0.800 |
| seasonal | 4 | moving_average | 180 | 0.363 | 0.802 | 0.74 | 0.767 |
| seasonal | 4 | naive | 180 | 0.405 | 0.894 | 0.19 | 0.733 |
| seasonal | 4 | seasonal_naive | 180 | 0.397 | 0.877 | 0.19 | 0.733 |
| seasonal | 6 | ets | 180 | 0.340 | 0.803 | 0.21 | 0.761 |
| seasonal | 6 | moving_average | 180 | 0.367 | 0.868 | 0.21 | 0.739 |
| seasonal | 6 | naive | 180 | 0.386 | 0.911 | -0.34 | 0.722 |
| seasonal | 6 | seasonal_naive | 180 | 0.359 | 0.847 | -0.36 | 0.728 |

## Scenario comparison

The fixed-seed Monte Carlo run compares lean, balanced, and resilient buffers under supplier delay and a demand spike. Values describe one fictional SKU/location scenario only.

| Condition | Policy | Fill rate | Stockout days | Avg stock | Holding cost | Excess | Expedite cost | Orders |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| supplier_delay | lean | 0.998 | 0.10 | 37.59 | $5.50 | 0.14 | $0.05 | 0.81 |
| supplier_delay | balanced | 0.999 | 0.02 | 37.86 | $5.54 | 0.15 | $0.05 | 0.97 |
| supplier_delay | resilient | 1.000 | 0.01 | 37.66 | $5.51 | 0.03 | $0.10 | 1.08 |
| demand_spike | lean | 0.998 | 0.14 | 31.59 | $4.62 | 0.08 | $0.12 | 1.40 |
| demand_spike | balanced | 0.999 | 0.07 | 32.52 | $4.76 | 0.12 | $0.08 | 1.16 |
| demand_spike | resilient | 0.999 | 0.04 | 32.52 | $4.76 | 0.04 | $0.12 | 1.50 |

## Limits

This is a hand-authored synthetic panel with a fixed seed. Backtest metrics and interval coverage apply only to its segments, generated assumptions, cutoffs, and horizons. The scenario cost rates are illustrative. They do not establish service-level performance, savings, supplier outcomes, or suitability for live purchasing.

No observation-level demand, inventory, supplier, or simulation rows are stored in this report.

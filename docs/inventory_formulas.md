# Inventory Control Tower formulas

All displayed inventory and supplier records are generated synthetic data. Unit measures are nonnegative except that derived available-to-promise and inventory position can be negative when reservations, blocked stock, or backorders exceed stock. Money in deterministic recommendation calculations is represented with `Decimal` and rounded to cents using `ROUND_HALF_UP`.

## Stock position

For one SKU and location:

```text
ATP = on_hand - reserved - blocked
confirmed_incoming = snapshot_in_transit + sum(open_qty for confirmed/open POs not yet past expected_date)
inventory_position = ATP + confirmed_incoming - backorders
```

Blocked units are excluded from ATP. The generated snapshot's `in_transit` amount represents shipments separate from open purchase orders, so this synthetic data does not double count those inputs. The data validator checks key uniqueness, required values, numeric ranges, references, route direction, date order, and row-set consistency before the tower serves an analysis.

## Demand estimate and reorder point

Demand is weekly. For the deterministic recommendation the selected forecast supplies the expected weekly demand; the historical weekly standard deviation supplies the demand uncertainty. The engine converts these to daily units using an independent-day approximation:

```text
mu_d = mean_weekly_units / 7
sigma_d = sample_std_weekly_units / sqrt(7)
H = supplier_lead_time_days + review_period_days
z = NormalDist().inv_cdf(service_level)
lead_review_demand = mu_d * H
safety_stock = z * sqrt(H * sigma_d^2 + mu_d^2 * lead_time_std_days^2)
reorder_point = lead_review_demand + safety_stock
raw_need = max(0, reorder_point - inventory_position)
```

The variance combines demand uncertainty over the lead-plus-review horizon with supplier lead-time uncertainty. A policy service level of 90%, 95%, or 98% maps to the standard normal quantile. Other valid service levels use Python's normal inverse CDF.

The unconstrained draft order is `max(MOQ, ceil_to_pack(raw_need))`. It is limited by the policy maximum stock and, when supplied, the budget:

```text
maximum_stock_units = mu_d * max_stock_days
stock_capacity = max(0, maximum_stock_units - inventory_position)
stock_cap = floor_to_pack(stock_capacity)
budget_cap = floor_to_pack(budget / unit_cost)
suggested_units = min(unconstrained_draft, stock_cap, budget_cap)
```

If the constrained result is below the supplier MOQ, the engine returns zero with a reason code. With no positive need it returns zero. No result creates or transmits a purchase order. The Hub persists an approval before the local draft is saved; a separate persisted approval is required to record a simulated execution.

## Cover and demand bands

```text
mean_daily_demand = mean_weekly_forecast / 7
days_of_cover = ATP / mean_daily_demand
```

Negative or zero ATP is shown as zero days with `stockout_or_negative_stock`. Positive stock and no positive forecast demand returns `days = null` with `no_positive_demand`; it is never divided by zero.

Forecasts use naive last value, 52-week seasonal naive (falling back to last value until a full season exists), eight-week moving average, additive-trend ETS from Statsmodels, and Croston SBA for intermittent series. An optional pooled LightGBM challenger is imported only when installed; its feature builder filters every series to dates at or before the requested cutoff. The comparison selects the lowest aggregate WAPE and, among models within 2% of that score, the simplest model. Segment selections are written to `docs/eval/inventory_forecast.json` and used by the app.

The chart uses training-only empirical residuals from rolling one-step, eight-week moving-average predictions over the latest 52 eligible observations:

```text
p10 = max(0, point + quantile(residuals, 0.10))
p50 = max(0, point + quantile(residuals, 0.50))
p90 = max(0, point + quantile(residuals, 0.90))
```

These are empirical residual bands, not a parametric normal interval. Their measured coverage is reported by demand segment and horizon.

## Forecast evaluation

Rolling-origin cutoffs are 26, 13, and 6 weeks before the series end. Horizons are 1, 2, 4, and 6 weeks. Each cutoff trains only on observations at or before that cutoff. The report groups metrics by horizon and segment:

```text
WAPE = sum(abs(actual - forecast)) / sum(abs(actual))
MASE = mean(abs(actual - forecast)) / mean(abs(training[t] - training[t-1]))
bias = mean(forecast - actual)                 # positive means over-forecast
interval_coverage = mean(p10 <= actual <= p90)
```

WAPE is `null` when the test window has no positive actual demand. A zero MASE denominator is replaced by 1 to keep the metric finite for a constant history; this boundary is explicitly covered by tests.

## Transfer options

For a source/destination route:

```text
source_surplus = max(0, source_ATP - source_mean_daily * source_max_stock_days)
destination_need = max(0, destination_mean_daily * (destination_lead_days + destination_review_days)
                          - destination_inventory_position)
transfer_units = floor(min(source_surplus, destination_need))
```

The route duration and per-unit cost use the median synthetic transfer history for that SKU and route, or a fixed five-day/0.25-unit-cost fallback when history is absent. A route is offered only when its lead time is no greater than the destination supplier lead time and its estimated per-unit cost is at most 15% of the destination item cost. The proposal is further bounded by source surplus and destination shortage.

## Scenario simulator

The fixed-seed simulator runs a 90-day daily demand process with 200 replications per policy/condition in the UI. It begins with ATP, the confirmed inbound pipeline, and existing backorders from the synthetic snapshot. Demand is Poisson at the recent weekly mean divided by seven; a demand-spike condition multiplies the first 21 days by 1.50. The supplier-delay condition adds seven days to lead time; the supplier's synthetic reliability can add another seven days. Lean, balanced, and resilient policies use 1.00, 1.35, and 1.80 multipliers on the safety buffer:

```text
target = min(mu_d * (lead_days + review_days)
             + buffer_multiplier * z * sqrt((lead_days + review_days) * sigma_d^2
                                             + mu_d^2 * lead_time_std_days^2),
             mu_d * max_stock_days)
reorder_trigger = 0.72 * target
```

Orders respect pack size, MOQ, and remaining maximum-stock capacity. Fill rate is units served divided by units requested; stockout days count days where demand exceeded available units; average inventory is the mean end-of-day on-hand quantity; excess is ending stock plus open simulated inbound minus target. Holding cost uses a synthetic 1% of item value per 30 days, prorated over the horizon. Expedite cost uses 15% of unit cost for each simulated late delivery. Order frequency is the average number of orders per 90-day replication. Results compare all six policy/condition combinations; they do not identify an optimal policy.

## Approval and simulation boundary

`inventory.propose_replenishment` and `inventory.simulate_execution` are registered as draft side effects with `requires_approval=true`. Alpha's Phase A executor persists, scopes, expires, consumes, and audits approval records. A denied, pending, expired, or rejected approval does not call the handler. The simulation handler only updates the local synthetic proposal ledger, is idempotent, and returns `real_purchase_order_created=false`. There is no vendor API, ERP write, email, or live purchasing route.

# Inventory Control Tower demo

1. Open **Inventory Control Tower** and point out the `SYNTHETIC DATA` badge and table validation result.
2. Select `SKU-001` at `LOC-001`. Explain the difference between on-hand, available-to-promise and inventory position, including why blocked units are excluded.
3. Review the six-week forecast and training-only empirical band; compare its selected model and interval coverage in `docs/eval/inventory_forecast.md`.
4. Open **Scenario tradeoffs** and run 200 replications. Compare fill rate, stockout days, stock, holding cost, excess, expedite cost and order frequency across both disruptions.
5. Open **Transfer options** and show how source surplus, destination shortage, route time and transfer cost restrict candidates.
6. Request a draft for `SKU-001` at `LOC-001`. Show the pending persisted Hub approval. An admin in the same workspace approves or rejects it; the requester cannot self-approve.
7. After approval, show the saved draft. Request its simulation and approve that second persisted approval. Point out `SIMULATED ONLY` and `real_purchase_order_created=false`.
8. Use the Hub sample question: “Which SKUs are at risk over the next 6 weeks, why, and what should I review first?” Verify the trace includes `inventory.risk_ranking`, `inventory.position`, and `inventory.forecast`, then `hub.verify_results`.

Do not present generated costs, service levels, backtests, or policies as claims about real inventory or savings.

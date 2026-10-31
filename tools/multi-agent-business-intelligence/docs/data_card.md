# Synthetic retail orders data card

- **Dataset label:** SYNTHETIC.
- **Source:** Generated locally by `scripts/seed_data.py`; no external source, employer source, or personal data.
- **Seed:** Python random seed `53`.
- **License:** Not applicable; generated demonstration data.
- **Refresh:** Recreate with `python -m tools.multi-agent-business-intelligence.scripts.seed_data`.
- **Schema:** `orders(order_id, order_date, product, category, region, quantity, gross, refund)`.
- **Intended use:** Demonstrate bounded aggregation and independent verification in the BI Analyst Workflow.
- **Prohibited use:** Do not treat it as a sample of any real business, estimate actual sales, or support operational decisions.
- **Limitations:** Small, fixed and deliberately regular data generation; dates fall on the 15th of each month. It is unsuitable for measuring generalization, seasonal forecasts, or business performance.
- **Storage:** Generated SQLite file under ignored `data/runtime/`; no database file is committed.

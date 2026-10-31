# Inventory Control Tower tool card

- **Purpose:** Help an analyst review synthetic inventory risk, forecast bands, stock position, scenario tradeoffs, and feasible transfer options.
- **Data boundary:** Fixed-seed `SYNTHETIC` records only. The tools do not fetch real inventory or supplier data.
- **Read tools:** `inventory.risk_ranking`, `inventory.position`, `inventory.forecast`, `inventory.simulate_scenario`, and `inventory.transfer_options`.
- **Draft tools:** `inventory.propose_replenishment` and `inventory.simulate_execution`. Both have `side_effect=draft` and `requires_approval=true` in the shared registry.
- **Identity:** Read and draft calls require an active Hub identity with employee or admin role. Draft ownership is scoped by user and configured workspace; approval rights follow the existing Phase A admin policy.
- **Verification:** Hub evidence is independently rerun or checked against the owner-scoped synthetic ledger. Invalid or missing checks withhold result values.
- **Action boundary:** A proposal is a local draft after persisted approval. Simulated execution needs a second persisted approval, is idempotent, and records `real_purchase_order_created=false`.
- **Limit:** The benchmark and explanation cover only synthetic assumptions; they are not purchasing recommendations for live operations.

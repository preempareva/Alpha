# Inventory Control Tower runbook

## Start

From `ai projects/project-alpha`, start the combined Alpha workspace with:

```powershell
./run.ps1
```

Alpha bootstrap creates the ignored synthetic inventory tables if missing. Open <http://127.0.0.1:8000> and choose **Inventory Control Tower**. The original demand forecast slug and `/api/forecast/{sku}` and `/api/backtest/{sku}` routes remain available. The replenishment slug also keeps `/api/backtest` and `/api/recommend`.

## Review workflow

1. Confirm the data-quality indicator reads **VALIDATED** and the **SYNTHETIC DATA** badge is visible.
2. Select an SKU and location. Review available-to-promise, inventory position, days of cover, supplier lead time, risk ranking, and the six-week demand band.
3. Compare lean, balanced and resilient policies under supplier-delay and demand-spike conditions. Read every metric as a tradeoff.
4. Inspect transfer options. Route duration and cost, source surplus, and destination need constrain the listed options.
5. Request a replenishment draft. The Hub creates a persisted pending approval; an authorized admin reviews and approves or rejects it in **Drafts & approvals**.
6. After approval, the draft appears in the owner-scoped proposal list. Request simulation; a second persisted approval is required. The resulting record is explicitly simulated and never creates an order.

The Hub approval inbox is scoped by the configured Alpha workspace. An administrator can approve another user's pending action; the requester cannot self-approve. See `docs/inventory_formulas.md` for assumptions and formula definitions.

## Troubleshooting

- **Data quality unavailable:** Run Alpha bootstrap again. If the validator remains red, stop using the generated set and inspect the safe issue codes returned by `/tools/replenishment/api/tower/quality`.
- **No forecast or options:** Verify bootstrap generated the ignored `tower/*.csv` files; do not edit generated files by hand.
- **Approval request forbidden:** Sign in as an authorized admin in the same configured workspace. A requester cannot approve their own request.
- **Draft absent after approval:** Refresh the queue. Only the original active requester can see their owner-scoped proposal; inspect the Hub run status and safe error code.
- **No browser session:** Sign in through the Knowledge Assistant first, then reload the tower. No secrets are copied into the inventory pages.

All persistence is local to Alpha. The scenario and simulated execution routes make no external calls.

# Inventory Control Tower threat model

## Assets and boundaries

- Fixed-seed generated inventory tables and model evaluation summaries; all are explicitly SYNTHETIC.
- A local proposal ledger scoped by the authenticated Hub user and configured workspace.
- Alpha's persisted Phase A approval records and the user's signed Knowledge Assistant session/CSRF token.
- No supplier connector, ERP client, purchase-order endpoint, email route, or live inventory integration exists.

## Threats and controls

- **Malformed or inconsistent seed data:** Table/column sets, required nulls, key uniqueness, references, finite numeric values, date order, and bounded service levels are validated before tower and Hub analyses. Tests inject invalid cases.
- **Formula and overflow abuse:** Hub inputs use strict SKU/location patterns, bounded horizons, replications and result sizes. Decimal values must be finite; pack, MOQ, budget and maximum-stock bounds are checked before a draft is returned.
- **Prompt or tool misuse:** Only explicit registry entries are callable. The local planner is not offered draft tools; proposal and simulation intents use deterministic plans. Both draft tools require the persisted Phase A approval gate, and handlers run only after approval is consumed.
- **Unauthorized draft access:** Draft records are keyed to authenticated user and workspace. Approval privileges remain in Alpha's Phase A role policy, and requesters cannot self-approve. No caller-supplied identity or workspace is accepted.
- **Duplicate simulation:** Phase A step claims and idempotency keys protect execution. The local ledger returns the existing simulation rather than creating a second one.
- **External or real-world execution:** Simulation only updates a local synthetic SQLite record and explicitly returns `real_purchase_order_created=false`; it performs no network requests.
- **XSS in rendered evidence:** Dynamic text in the inventory screen is HTML-escaped. Numeric charts use bounded synthetic output from the local API.

## Residual risks

The local proposal database and Hub trace database are not encrypted at rest. The synthetic app APIs are intended for the localhost Alpha workspace and must not be exposed as a public inventory service. A user could still mistake synthetic output for an operational recommendation; badges, approvals, formula documentation, and repeated no-order notices reduce but cannot eliminate that risk. The model card and evaluation describe a fixed synthetic panel only.

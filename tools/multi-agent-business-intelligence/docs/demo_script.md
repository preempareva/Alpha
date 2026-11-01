# BI Analyst Workflow demo script

## Setup

From the Project Alpha root, install the pinned requirements and run `python -m scripts.seed_all` from a fresh clone. Start Alpha with `./run.ps1`, sign in through the local Knowledge Assistant demo account, then open **BI Analyst Workflow**. The database and generated fixtures contain fictional retail rows only.

## Walkthrough

1. Ask for monthly revenue and inspect the selected registered read tool and date bounds.
2. Ask for top categories and compare the returned evidence with the displayed result.
3. Ask an unsupported write question; confirm it is refused without a mutation.
4. Review the run trace and independent `verify_totals` result.
5. Reproduce the 40-question regression benchmark with `python -m tools.multi-agent-business-intelligence.scripts.evaluate_agent` from the repository root.

The UI and API use fixed query templates, read-only SQLite access, bound values, result limits, and independent aggregation. The optional local planner is off by default. The synthetic benchmark covers its authored cases only; it does not estimate performance on a real warehouse.

# Replenishment Calculator

Synthetic weekly demand and replenishment simulation. It reports a temporal last-eight-week backtest against simple baselines and produces a reorder-point recommendation from the recent 8-week mean, lead time, a configurable safety factor, and stock position. Every proposal is marked `NEEDS_APPROVAL`; the app cannot place orders.

## Run in Alpha

Open the unified workspace from project-alpha with powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1. This tool opens as a workflow inside the Alpha site at http://127.0.0.1:8000.

## Limits

Demand, prices, stockouts, lead times, supplier constraints, and costs are synthetic or omitted. The simple safety-stock formula is a scenario exercise, not an optimal policy or savings estimate. It should not drive real replenishment without authorized operational data, service-level objectives, uncertainty testing, and planner approval.





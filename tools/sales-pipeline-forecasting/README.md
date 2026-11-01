# Sales Pipeline Forecast

Point-in-time synthetic opportunity scoring with a calibrated logistic-regression baseline and prevalence-only dummy comparison. Each opportunity receives a 90-day win probability and a probability-weighted pipeline value. This is a planning signal, not a revenue commitment.

## Run in Alpha

Open the unified workspace from project-alpha with powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1. This tool opens as a workflow inside the Alpha site at http://127.0.0.1:8000.

## Limits

Outcomes are synthetic and easy to learn from generated rules. The chronological holdout does not establish generalization to a real CRM. No pipeline stage semantics, rep effects, seasonality, long sales cycles, or forecasting reconciliation are modeled. Never present weighted pipeline as committed bookings.





# Customer Churn Prediction

A synthetic-data prototype for ranking subscription accounts by observed churn risk over a defined 60-day horizon. It uses point-in-time snapshots, a temporal holdout, a dummy baseline, a calibrated logistic regression pipeline, and reason codes derived from model coefficients. Scores are prioritization signals for a human analyst; they do not trigger outreach or determine customer eligibility.

## Run in Alpha

Open the unified workspace from project-alpha with powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1. This tool opens as a workflow inside the Alpha site at http://127.0.0.1:8000.

## Evaluation

`python scripts/train.py` reports ROC AUC, PR AUC, Brier score, calibration bins, and precision/recall at a review threshold on the last temporal period. It compares against a prevalence-only dummy. Exact metrics are written to `artifacts/evaluation.json`; they are synthetic-data results and are not evidence of real retention impact.

## Known limits

The data generator creates labels from a known synthetic process, so the score can recover those patterns more easily than it would in a real product. There is no causal estimate, real dataset, protected-attribute fairness audit, authentication, outreach integration, or monitoring. This project is not production ready.





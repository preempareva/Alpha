# Runbook

1. Install pinned dependencies in a clean Python virtual environment.
2. Generate the synthetic CSV and train the model using the README commands.
3. Review temporal boundaries, prevalence, metrics, calibration bins, and limitations in `artifacts/evaluation.json`.
4. Start the API locally. `/health` checks process status; `/api/metrics` exposes the evaluation; `/api/score` validates and scores one record.
5. A missing model returns HTTP 503. Regenerate and retrain; do not silently use a stale or absent artifact.
6. To reset, remove only the generated files under `data/generated/` and `artifacts/`, then rerun generation and training.

Before a real pilot, replace synthetic data with authorized point-in-time records, validate label dates, set governance and retention, review fairness and calibration by appropriate groups, authenticate access, add drift/quality monitoring, and obtain domain-owner approval.

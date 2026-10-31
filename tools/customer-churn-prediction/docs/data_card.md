# Synthetic data card

- **Source:** `scripts/generate_data.py`, deterministic random seed 29.
- **Unit:** Customer snapshot at a month-start date.
- **Target:** Synthetic `churn_60d` indicator generated for a 60-day prediction exercise.
- **Features:** Tenure, active days, sessions, usage change, support contacts, late payments, monthly fee, and plan category.
- **Excluded:** Direct personal identifiers, demographic/sensitive fields, and actual company data.
- **Known limits:** Labels are generated from a known probabilistic formula; feature/label patterns are deliberately learnable and may not resemble real churn. Customers can have repeated snapshots. This is not a representative customer population.
- **Reproduction:** `python scripts/generate_data.py`; generated CSV is local and gitignored.

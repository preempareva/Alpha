# Sales model card

- **Target:** Synthetic opportunity outcome within 90 days.
- **Features:** Snapshot amount, age, stage, recent touches and stakeholder count.
- **Method:** Imputation, scaling, one-hot stage, class-weighted logistic regression with sigmoid calibration.
- **Split:** Chronological snapshot holdout; split date and scores in `artifacts/evaluation.json`.
- **Baseline:** Training-prevalence dummy.
- **Limits:** Synthetic label formula, one row per opportunity (no repeated temporal history), no real CRM data, no calibration monitoring or sales-owner review.
- **Use:** Scenario and learning prototype only; probability-weighted value is not a guarantee.

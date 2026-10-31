# Project charter

- **Problem:** Retention teams may need to prioritize limited human review when customer activity changes.
- **User:** Customer success or retention analyst.
- **Decision:** Which synthetic subscription accounts merit a closer review within a 60-day horizon?
- **Outcome measures:** PR AUC, ROC AUC, Brier score, calibration, precision/recall at the review threshold, and analyst feedback.
- **Baseline:** Prevalence-only dummy classifier.
- **Data and permission:** Fully synthetic data generated in-repository; no customer or company records.
- **Constraints:** The generated churn labels are only a learning benchmark and do not show actual customer behavior.
- **Non-goals:** Autonomous outreach, service denial, causal claims, sensitive-attribute inference, and production decisioning.

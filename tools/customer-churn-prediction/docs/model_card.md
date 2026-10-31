# Model card

- **Model:** Median/mode imputation, scaling/one-hot preprocessing, class-weighted logistic regression, sigmoid calibration.
- **Target/horizon:** Synthetic churn event within 60 days as defined by this generated snapshot exercise.
- **Split:** Chronological holdout; train snapshots end 2026-02-01, test begins 2026-03-01. No random split.
- **Metrics:** Generated at `artifacts/evaluation.json`. Report ROC AUC, PR AUC, Brier, threshold precision/recall and quantile calibration bins alongside prevalence-only baseline.
- **Review threshold:** Illustrative 0.05 operating point; not a validated business policy. Select only with an authorized owner, intervention capacity, and explicit error-cost tradeoffs.
- **Reason display:** Heuristic descriptions of values outside training medians or declining usage; these are not the fitted model's causal explanations and can omit/oversimplify drivers.
- **Use:** Educational analyst review only. Human validates context before any action.
- **Not for:** Automated contact, eligibility decisions, real customer use, or claims of retention lift.

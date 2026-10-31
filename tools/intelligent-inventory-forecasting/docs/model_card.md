# Forecast card

- **Grain:** Synthetic SKU/week.
- **Baseline:** Mean of the last eight observed weeks; uncertainty range uses their standard deviation.
- **Evaluation:** Last eight weeks held out in time and compared with a last-value naive baseline using MAE and empirical range coverage.
- **Known gaps:** No seasonal model despite generated seasonality, no multiple rolling origins, no per-SKU aggregate report, intervals are not calibrated, and synthetic demand does not represent inventory operations.

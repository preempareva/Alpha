from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/generated/customer_snapshots.csv"


def generate(n_customers: int = 1400, seed: int = 29) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    plans = np.array(["basic", "standard", "premium"])
    start = pd.Timestamp("2025-01-01")
    months = pd.date_range(start, "2026-08-01", freq="MS")
    for customer in range(n_customers):
        plan = rng.choice(plans, p=[0.45, 0.4, 0.15])
        fee = {"basic": 25, "standard": 55, "premium": 95}[plan] * rng.uniform(0.9, 1.1)
        base_tenure = int(rng.integers(2, 48))
        latent = rng.normal()
        churned = False
        for month in months:
            tenure = base_tenure + ((month.year - start.year) * 12 + month.month - 1)
            usage_trend = float(np.clip(rng.normal(0.02 + latent * 0.025, 0.16), -0.8, 0.5))
            active = float(np.clip(rng.normal(18 + latent * 2, 7), 0, 31))
            sessions = float(np.clip(rng.normal(active * 2.3, 12), 0, 200))
            tickets = int(rng.poisson(0.7 + max(0, -latent) * 0.8))
            late = int(rng.binomial(2, min(0.8, 0.12 + max(0, -latent) * 0.18)))
            logit = -3.0 - 0.025 * min(tenure, 40) - usage_trend * 2.1 - (active - 15) * 0.045 + tickets * 0.22 + late * 0.48 + latent * -0.25
            p = 1 / (1 + np.exp(-logit))
            y = int(rng.random() < p)
            rows.append({"customer_id": f"SYN-{customer:05d}", "snapshot_date": month.date().isoformat(),
                         "tenure_months": tenure, "active_days_30d": round(active, 2), "sessions_30d": round(sessions, 2),
                         "usage_change_30d": round(usage_trend, 4), "support_tickets_90d": tickets,
                         "late_payments_90d": late, "monthly_fee": round(fee, 2), "plan": plan, "churn_60d": y})
            if y:
                churned = True
                break
    return pd.DataFrame(rows)


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = generate()
    data.to_csv(OUT, index=False)
    print(f"Wrote {len(data)} synthetic snapshots to {OUT}; churn rate={data.churn_60d.mean():.3f}")

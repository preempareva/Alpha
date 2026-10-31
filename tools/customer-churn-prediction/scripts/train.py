from __future__ import annotations

import json
from pathlib import Path
from importlib import import_module

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, precision_score, recall_score, roc_auc_score
from sklearn.calibration import calibration_curve

model = import_module("tools.customer-churn-prediction.app.model")
FEATURES, TARGET = model.FEATURES, model.TARGET
REVIEW_THRESHOLD, build_pipeline = model.REVIEW_THRESHOLD, model.build_pipeline

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/generated/customer_snapshots.csv"
ARTIFACTS = ROOT / "artifacts"


def run() -> dict:
    if not DATA.exists():
        raise SystemExit("Generate data first: python scripts/generate_data.py")
    frame = pd.read_csv(DATA, parse_dates=["snapshot_date"])
    # Strict time split: no later snapshot contributes to training.
    cutoff = frame.snapshot_date.quantile(0.8)
    train = frame[frame.snapshot_date < cutoff].copy()
    test = frame[frame.snapshot_date >= cutoff].copy()
    if train[TARGET].nunique() < 2 or test[TARGET].nunique() < 2:
        raise SystemExit("Temporal split has a single class; regenerate or expand the synthetic dataset.")
    model = build_pipeline()
    model.fit(train[FEATURES], train[TARGET])
    probability = model.predict_proba(test[FEATURES])[:, 1]
    threshold = REVIEW_THRESHOLD
    baseline = DummyClassifier(strategy="prior").fit(train[FEATURES], train[TARGET])
    baseline_p = baseline.predict_proba(test[FEATURES])[:, 1]
    observed, predicted = calibration_curve(test[TARGET], probability, n_bins=5, strategy="quantile")
    metrics = {
        "dataset": "synthetic customer snapshots generated locally",
        "seed": 29,
        "train_end": str(train.snapshot_date.max().date()),
        "test_start": str(test.snapshot_date.min().date()),
        "train_rows": int(len(train)), "test_rows": int(len(test)),
        "test_prevalence": round(float(test[TARGET].mean()), 4), "review_threshold": threshold,
        "model": {"roc_auc": round(float(roc_auc_score(test[TARGET], probability)), 4),
                  "pr_auc": round(float(average_precision_score(test[TARGET], probability)), 4),
                  "brier": round(float(brier_score_loss(test[TARGET], probability)), 4),
                  "precision_at_threshold": round(float(precision_score(test[TARGET], probability >= threshold, zero_division=0)), 4),
                  "recall_at_threshold": round(float(recall_score(test[TARGET], probability >= threshold, zero_division=0)), 4)},
        "dummy_prior": {"roc_auc": round(float(roc_auc_score(test[TARGET], baseline_p)), 4),
                        "pr_auc": round(float(average_precision_score(test[TARGET], baseline_p)), 4),
                        "brier": round(float(brier_score_loss(test[TARGET], baseline_p)), 4)},
        "calibration_bins": [{"mean_predicted": round(float(p), 4), "observed_rate": round(float(o), 4)} for p, o in zip(predicted, observed)],
        "limitations": ["Synthetic labels are generated from known feature relationships.", "Temporal validation is not evidence of real-world lift.", "The review threshold is illustrative and must be set with a data owner and capacity/cost policy.", "Reasons are descriptive heuristics, not causal explanations."]
    }
    ARTIFACTS.mkdir(exist_ok=True)
    medians = train[FEATURES].select_dtypes(include=[np.number]).median().to_dict()
    joblib.dump({"model": model, "feature_medians": medians, "features": FEATURES,
                 "train_end": str(train.snapshot_date.max().date()), "horizon_days": 60}, ARTIFACTS / "churn_pipeline.joblib")
    (ARTIFACTS / "evaluation.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    run()

from __future__ import annotations

from pathlib import Path
import json
import os

import joblib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

NUMERIC = ["tenure_months", "active_days_30d", "sessions_30d", "usage_change_30d", "support_tickets_90d", "late_payments_90d", "monthly_fee"]
CATEGORICAL = ["plan"]
FEATURES = NUMERIC + CATEGORICAL
TARGET = "churn_60d"
ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = Path(os.getenv("MODEL_PATH", str(ROOT / "artifacts" / "churn_pipeline.joblib")))
METRICS_PATH = MODEL_PATH.with_name("evaluation.json")
REVIEW_THRESHOLD = 0.05  # Illustrative operating point; requires owner review on authorized data.


def build_pipeline() -> Pipeline:
    numeric = Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())])
    categorical = Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))])
    prep = ColumnTransformer([("num", numeric, NUMERIC), ("cat", categorical, CATEGORICAL)])
    base = Pipeline([("prep", prep), ("model", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=17))])
    return CalibratedClassifierCV(base, method="sigmoid", cv=3)


def load_bundle(path: Path | None = None) -> dict:
    model_path = path or MODEL_PATH
    if not model_path.exists():
        raise FileNotFoundError("Model is missing. Generate synthetic data and run scripts/train.py first.")
    return joblib.load(model_path)


def risk_reasons(bundle: dict, row: pd.DataFrame, top: int = 3) -> list[str]:
    """Model-agnostic reason preview: show unusual values versus training medians."""
    reference = bundle["feature_medians"]
    directions = {
        "usage_change_30d": (lambda x: x < 0, "declining usage"),
        "active_days_30d": (lambda x: x < reference["active_days_30d"], "few active days"),
        "sessions_30d": (lambda x: x < reference["sessions_30d"], "fewer recent sessions"),
        "support_tickets_90d": (lambda x: x > reference["support_tickets_90d"], "recent support contacts"),
        "late_payments_90d": (lambda x: x > reference["late_payments_90d"], "late payments"),
        "tenure_months": (lambda x: x < reference["tenure_months"], "shorter tenure"),
    }
    candidates = []
    for col, (condition, label) in directions.items():
        value = float(row.iloc[0][col])
        if condition(value):
            candidates.append((abs(value - reference[col]), label))
    candidates.sort(reverse=True)
    return [label for _, label in candidates[:top]]


def score_rows(bundle: dict, rows: pd.DataFrame) -> list[dict]:
    probs = bundle["model"].predict_proba(rows[FEATURES])[:, 1]
    out = []
    for i, probability in enumerate(probs):
        row = rows.iloc[[i]]
        out.append({"risk_probability": round(float(probability), 4),
                    "risk_band": "high" if probability >= 0.10 else "review" if probability >= REVIEW_THRESHOLD else "lower",
                    "reasons": risk_reasons(bundle, row)})
    return out

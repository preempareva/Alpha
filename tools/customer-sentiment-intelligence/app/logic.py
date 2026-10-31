from __future__ import annotations

from pathlib import Path
import joblib
import os
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODEL = Path(os.getenv("SENTIMENT_MODEL", str(ROOT / "artifacts" / "sentiment.joblib")))


def load_model():
    if not MODEL.exists():
        raise FileNotFoundError("Train the baseline first with python scripts/train.py")
    return joblib.load(MODEL)


def analyze(bundle: dict, text: str) -> dict:
    probs = bundle["model"].predict_proba([text])[0]
    labels = bundle["model"].classes_
    label = str(labels[int(probs.argmax())])
    themes = [name for name, words in bundle["themes"].items() if any(word in text.lower() for word in words)]
    return {"sentiment": label, "confidence": round(float(probs.max()), 4),
            "themes": themes or ["other / review"],
            "notice": "Synthetic prototype classification; review representative text before acting."}

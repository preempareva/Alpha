import os
from pathlib import Path
from importlib import import_module

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
os.environ["MODEL_PATH"] = str(ROOT / "artifacts/churn_pipeline.joblib")
app = import_module("tools.customer-churn-prediction.app.main").app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_score_returns_bounded_risk_and_notice(client):
    response = client.post("/api/score", json={"customer_id": "SYN-test", "tenure_months": 4,
        "active_days_30d": 5, "sessions_30d": 8, "usage_change_30d": -0.4,
        "support_tickets_90d": 3, "late_payments_90d": 1, "monthly_fee": 55, "plan": "standard"})
    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["risk_probability"] <= 1
    assert body["risk_band"] in {"high", "review", "lower"}
    assert body["horizon_days"] == 60
    assert "Synthetic" in body["notice"]


def test_input_validation_rejects_impossible_value(client):
    response = client.post("/api/score", json={"customer_id": "SYN-test", "tenure_months": 4,
        "active_days_30d": 99, "sessions_30d": 8, "usage_change_30d": -0.4,
        "support_tickets_90d": 3, "late_payments_90d": 1, "monthly_fee": 55, "plan": "standard"})
    assert response.status_code == 422


def test_metrics_expose_dataset_limitations(client):
    response = client.get("/api/metrics")
    assert response.status_code == 200
    assert "synthetic" in response.json()["dataset"]
    assert response.json()["model"]["roc_auc"] >= response.json()["dummy_prior"]["roc_auc"]

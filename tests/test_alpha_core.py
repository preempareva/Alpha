from __future__ import annotations

import logging
from importlib import import_module

import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.testclient import TestClient

from alpha_core.llm import FakeProvider, LLMDisabled, NoneProvider
from alpha_core.settings import Settings


class Answer(BaseModel):
    answer: str


def test_llm_disabled_by_default_and_fake_output_is_schema_checked(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert Settings.from_env().llm_provider == "none"
    with pytest.raises(LLMDisabled):
        NoneProvider().complete("system", "user")
    result = FakeProvider(['{"answer":"grounded"}']).complete("system", "user", schema=Answer)
    assert result.parsed == Answer(answer="grounded")


def test_invalid_llm_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_project_shell_exposes_every_tool_health_endpoint_and_request_id(tmp_path, monkeypatch):
    generator = import_module("tools.inventory-optimization-agent.scripts.generate_tower_data")
    tower_root = tmp_path / "synthetic-inventory"
    generator.generate(tower_root)
    monkeypatch.setenv("INVENTORY_TOWER_DATA_ROOT", str(tower_root))
    app_module = import_module("alpha_app.main")
    client = TestClient(app_module.app)
    response = client.get("/health", headers={"X-Request-ID": "alpha-check-1"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "alpha-check-1"
    payload = response.json()
    assert payload["status"] == "ok"
    assert {item["id"] for item in payload["projects"]} == {project[0] for project in app_module.PROJECTS}
    assert all(item["status"] in {"ok", "ready", "healthy"} for item in payload["projects"])
    for project_id, *_ in app_module.PROJECTS:
        assert client.get(f"/tools/{project_id}/health").status_code == 200


def test_shell_uses_the_reviewed_product_labels_without_changing_slugs():
    app_module = import_module("alpha_app.main")
    projects = {item[0]: item[2] for item in app_module.PROJECTS}
    assert projects["helpdesk"] == "Helpdesk Triage"
    assert projects["knowledge"] == "Knowledge Assistant"
    assert projects["travel"] == "Travel Itinerary Planner"
    assert projects["demand"] == "Demand Forecasting"
    assert projects["churn"] == "Customer Churn Prediction"
    assert projects["sales-forecast"] == "Sales Pipeline Forecast"
    assert projects["sentiment"] == "Customer Sentiment Insights"
    assert projects["bi"] == "BI Analyst Workflow"
    assert projects["replenishment"] == "Inventory Control Tower"
    assert projects["sales-nudge"] == "Sales Follow-up Prioritizer"
    assert projects["incidents"] == "Incident Evidence Correlator (synthetic)"
    assert projects["quotes"] == "Supplier Quote Comparison"
    assert projects["segments"] == "Customer Segmentation"
    mounted_titles = {
        project[0]: subapp.title
        for project, subapp in zip(app_module.PROJECTS, app_module._loaded_apps)
    }
    assert mounted_titles == {project[0]: project[2] for project in app_module.PROJECTS}


def test_shell_security_headers_and_same_origin_cors_policy():
    app_module = import_module("alpha_app.main")
    response = TestClient(app_module.app).get(
        "/health", headers={"Origin": "https://cross-origin.example"},
    )
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "same-origin"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "access-control-allow-origin" not in response.headers
    assert all(
        subapp.exception_handlers[Exception] is app_module.internal_error
        for subapp in app_module._loaded_apps
    )


def test_unhandled_error_response_omits_exception_details_and_logs(caplog):
    app_module = import_module("alpha_app.main")
    app = FastAPI()
    app.add_exception_handler(Exception, app_module.internal_error)

    @app.get("/failure")
    def failure():
        raise RuntimeError("synthetic-secret-sentinel")

    with caplog.at_level(logging.ERROR, logger="alpha_app"):
        response = TestClient(app, raise_server_exceptions=False).get("/failure")
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "synthetic-secret-sentinel" not in response.text
    assert "synthetic-secret-sentinel" not in caplog.text


def test_validation_errors_include_request_id():
    app_module = import_module("alpha_app.main")
    client = TestClient(app_module.app)
    response = client.post("/api/travel-weather", json={"destination": "x"}, headers={"X-Request-ID": "bad-input"})
    assert response.status_code == 422
    assert response.json()["request_id"] == "bad-input"


def test_travel_weather_uses_geocoding_and_forecast_responses(monkeypatch):
    app_module = import_module("alpha_app.main")
    responses = iter([
        {"results": [{"name": "London", "admin1": "England", "country": "United Kingdom",
                      "latitude": 51.5, "longitude": -0.1}]},
        {"timezone": "Europe/London", "daily": {
            "time": ["2026-11-01"], "weather_code": [1], "temperature_2m_max": [12],
            "temperature_2m_min": [7], "precipitation_probability_max": [20],
        }},
    ])
    requested = []

    def fake_get_json(url):
        requested.append(url)
        return next(responses)

    monkeypatch.setattr(app_module, "_get_json", fake_get_json)
    app_module._weather_cache.pop("london", None)
    response = TestClient(app_module.app).post("/api/travel-weather", json={"destination": "London"})

    assert response.status_code == 200
    assert response.json()["destination"] == "London, England, United Kingdom"
    assert response.json()["days"][0]["max_c"] == 12
    assert len(requested) == 2

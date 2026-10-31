from __future__ import annotations

from importlib import import_module

import pytest
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
    assert projects["bi"] == "BI Analyst Workflow"
    assert projects["replenishment"] == "Inventory Control Tower"
    assert projects["sales-nudge"] == "Sales Follow-up Prioritizer"
    assert projects["incidents"] == "Incident Evidence Correlator (synthetic)"
    assert projects["segments"] == "Customer Segmentation"


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

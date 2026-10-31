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


def test_project_shell_exposes_every_tool_health_endpoint_and_request_id():
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


def test_validation_errors_include_request_id():
    app_module = import_module("alpha_app.main")
    client = TestClient(app_module.app)
    response = client.post("/api/travel-weather", json={"destination": "x"}, headers={"X-Request-ID": "bad-input"})
    assert response.status_code == 422
    assert response.json()["request_id"] == "bad-input"

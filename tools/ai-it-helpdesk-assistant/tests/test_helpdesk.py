from importlib import import_module
import pytest
from fastapi.testclient import TestClient

module = import_module("tools.ai-it-helpdesk-assistant.app.main")
app, init = module.app, module.init


@pytest.fixture(autouse=True)
def reset(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "DB", tmp_path / "helpdesk.db")
    init()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_intake_suggests_but_does_not_take_action(client):
    r = client.post("/api/intake", json={"description":"My VPN stopped working today on Windows with error 807."})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "NEEDS_REVIEW" and d["category_suggestion"] == "network"
    assert d["knowledge_article"]["id"] == "kb-vpn"


def test_secret_input_is_rejected(client):
    r = client.post("/api/intake", json={"description":"My password is abc123 and I cannot login"})
    assert r.status_code == 400


def test_review_approval_is_idempotent(client):
    d = client.post("/api/intake", json={"description":"VPN connection error started today on macOS."}).json()
    assert client.post(f"/api/tickets/{d['ticket_id']}/approve").json()["status"] == "APPROVED"
    assert client.post(f"/api/tickets/{d['ticket_id']}/approve").status_code == 404

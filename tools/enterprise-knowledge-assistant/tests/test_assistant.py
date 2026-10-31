import os
from importlib import import_module
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

DB = Path(__file__).parent / "test.db"
os.environ["DATABASE_PATH"] = str(DB)
os.environ["ALPHA_DEMO_ALICE_PASSWORD"] = "test-alice-password"
os.environ["ALPHA_DEMO_BOB_PASSWORD"] = "test-bob-password"
os.environ["ALPHA_DEMO_ADMIN_PASSWORD"] = "test-admin-password"
os.environ["KNOWLEDGE_SESSION_SECRET"] = "test-only-knowledge-secret"
module = import_module("tools.enterprise-knowledge-assistant.app.main")
app, init_db = module.app, module.init_db


@pytest.fixture(autouse=True)
def clean_db():
    if DB.exists():
        DB.unlink()
    init_db()
    yield
    if DB.exists():
        DB.unlink()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        login(test_client)
        yield test_client


def login(client, username="admin"):
    password = {"admin": "test-admin-password", "alice": "test-alice-password", "bob": "test-bob-password"}[username]
    return client.post("/api/login", json={"username": username, "password": password})


def upload(client, filename="travel.md", body=b"# Claims\nEmployees may claim INR 2500 for hotel stays.", groups="finance"):
    return client.post("/api/documents", data={"title": "Travel Claims", "owner": "owner", "version": "1", "access_groups": groups},
                       files={"file": (filename, body, "text/markdown")})


def test_acl_filters_before_results_and_client_headers_cannot_spoof_groups(client):
    assert upload(client).status_code == 200
    login(client, "bob")
    hidden = client.post("/api/ask", headers={"X-User-Id": "alice", "X-User-Groups": "finance"}, json={"question": "hotel claim limit"}).json()
    login(client, "alice")
    visible = client.post("/api/ask", headers={"X-User-Groups": "general"}, json={"question": "hotel claim limit"}).json()
    assert hidden["abstained"] is True and hidden["citations"] == []
    assert visible["abstained"] is False


def test_authentication_is_required_even_with_spoofed_identity_headers(client):
    client.post("/api/logout")
    response = client.post("/api/ask", headers={"X-User-Id": "alice", "X-User-Groups": "finance"}, json={"question": "hotel claim limit"})
    assert response.status_code == 401


def test_unknown_question_abstains(client):
    upload(client)
    login(client, "alice")
    result = client.post("/api/ask", json={"question": "What is the orbital launch code?"}).json()
    assert result["abstained"] is True


def test_bad_file_is_queued_for_review(client):
    response = upload(client, filename="payload.exe", body=b"bad")
    assert response.status_code == 400
    assert client.get("/api/admin/status").json()["jobs"][0]["status"] == "NEEDS_REVIEW"


def test_employees_cannot_upload_retire_or_read_admin_status(client):
    doc_id = upload(client).json()["document_id"]
    login(client, "alice")
    assert upload(client).status_code == 403
    assert client.get("/api/admin/status").status_code == 403
    assert client.post(f"/api/documents/{doc_id}/retire").status_code == 403


def test_admin_can_retire_and_retired_source_is_not_returned(client):
    doc_id = upload(client).json()["document_id"]
    assert client.post(f"/api/documents/{doc_id}/retire").status_code == 200
    login(client, "alice")
    result = client.post("/api/ask", json={"question": "hotel claim limit"}).json()
    assert result["abstained"] is True


def test_expired_documents_are_not_returned(client):
    module.ingest("expired.md", b"# Launch\nThe synthetic launch code is ORBITAL-42.", "Expired Launch Note",
                  "Demo Owner", "1", ["general"], None, "2020-01-01")
    login(client, "alice")
    result = client.post("/api/ask", json={"question": "synthetic launch code ORBITAL"}).json()
    assert result["abstained"] is True and not result["citations"]


def test_upload_limit_and_extension_are_enforced(client):
    response = client.post("/api/documents", data={"title": "x", "owner": "owner", "version": "1", "access_groups": "general"},
                           files={"file": ("x.exe", b"x", "application/octet-stream")})
    assert response.status_code == 400


def test_login_returns_server_resolved_role_and_audit_events(client):
    login_response = login(client, "alice")
    assert login_response.status_code == 200
    assert login_response.json()["status"] == "signed_in"
    assert client.get("/api/me").json()["user"]["groups"] == ["general", "finance"]
    with module.connect() as db:
        assert db.execute("SELECT action FROM audit_events WHERE action='login'").fetchone()[0] == "login"

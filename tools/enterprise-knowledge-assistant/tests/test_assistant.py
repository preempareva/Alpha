import os
from importlib import import_module
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

DB = Path(__file__).parent / "test.db"
os.environ["DATABASE_PATH"] = str(DB)
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
    return TestClient(app)


def upload(client, filename="travel.md", body=b"# Claims\nEmployees may claim INR 2500 for hotel stays.", groups="finance"):
    return client.post("/api/documents", data={"title": "Travel Claims", "owner": "owner", "version": "1", "access_groups": groups},
                       files={"file": (filename, body, "text/markdown")})


def test_acl_filters_before_results_are_returned(client):
    assert upload(client).status_code == 200
    hidden = client.post("/api/ask", headers={"x-user-groups": "general"}, json={"question": "hotel claim limit"}).json()
    visible = client.post("/api/ask", headers={"x-user-groups": "finance"}, json={"question": "hotel claim limit"}).json()
    assert hidden["abstained"] is True and hidden["citations"] == []
    assert visible["abstained"] is False


def test_unknown_question_abstains(client):
    upload(client)
    result = client.post("/api/ask", headers={"x-user-groups": "finance"}, json={"question": "What is the orbital launch code?"}).json()
    assert result["abstained"] is True


def test_bad_file_is_queued_for_review(client):
    response = upload(client, filename="payload.exe", body=b"bad")
    assert response.status_code == 400
    jobs = client.get("/api/admin/status").json()["jobs"]
    assert jobs[0]["status"] == "NEEDS_REVIEW"


def test_retirement_revokes_search_access(client):
    doc_id = upload(client).json()["document_id"]
    assert client.post(f"/api/documents/{doc_id}/retire").status_code == 200
    result = client.post("/api/ask", headers={"x-user-groups": "finance"}, json={"question": "hotel claim limit"}).json()
    assert result["abstained"] is True


def test_upload_limit_and_extension_are_enforced(client):
    response = client.post("/api/documents", data={"title": "x"}, files={"file": ("x.exe", b"x", "application/octet-stream")})
    assert response.status_code == 400

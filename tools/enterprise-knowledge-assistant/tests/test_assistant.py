import os
import json
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


def test_ambiguous_and_historical_questions_abstain(client):
    assert client.post("/api/ask", json={"question": "Which policy applies?"}).json()["abstained"] is True
    historical = client.post("/api/ask", json={"question": "What did the expired 2023 hotel policy allow?"}).json()
    assert historical["abstained"] is True and historical["citations"] == []


def test_ollama_answer_requires_a_retrieved_citation_and_source_overlap(client, monkeypatch):
    upload(client)
    login(client, "alice")
    user = client.get("/api/me").json()["user"]
    request = module.AskRequest(question="hotel claim limit")
    source = module.retrieve(request, user)["citations"][0]
    valid = {"answer": "Employees may claim INR 2500 for hotel stays.", "citation_ids": [source["chunk_id"]], "abstain": False}
    from alpha_core.llm import FakeProvider

    monkeypatch.setattr(module, "get_provider", lambda: FakeProvider([json.dumps(valid)]))
    result = client.post("/api/ask", json={"question": "hotel claim limit"}).json()
    assert result["answer_source"] == "local-ollama"
    assert result["citations"][0]["chunk_id"] == source["chunk_id"]

    invalid = {"answer": "Unsupported claim in the answer.", "citation_ids": ["unknown-chunk"], "abstain": False}
    monkeypatch.setattr(module, "get_provider", lambda: FakeProvider([json.dumps(invalid), json.dumps(invalid)]))
    fallback = client.post("/api/ask", json={"question": "hotel claim limit"}).json()
    assert fallback["answer_source"] == "deterministic"
    assert fallback["citations"][0]["chunk_id"] == source["chunk_id"]


def test_optional_embedding_retrieval_can_find_a_non_lexical_match(client, monkeypatch):
    upload(client)
    login(client, "alice")

    class FakeEmbeddingProvider:
        embedding_model = "nomic-test"

        def embed(self, texts, *, timeout_s=30):
            return [[1.0, 0.0] for _ in texts]

        def complete(self, *args, **kwargs):
            from alpha_core.llm import LLMDisabled
            raise LLMDisabled("Synthesis disabled in this retrieval test.")

    monkeypatch.setattr(module, "get_provider", lambda: FakeEmbeddingProvider())
    assert module.index_missing_embeddings() > 0
    user = client.get("/api/me").json()["user"]
    result = module.retrieve(module.AskRequest(question="lodging reimbursement ceiling"), user)
    assert result["citations"][0]["filename"] == "travel.md"


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

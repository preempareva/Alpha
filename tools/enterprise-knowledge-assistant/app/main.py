from __future__ import annotations

import hashlib
import html
import json
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated

import bcrypt
import fitz
from bs4 import BeautifulSoup
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("DATABASE_PATH", str(ROOT / "instance" / "knowledge.db")))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "10000000"))
MIN_SCORE = float(os.getenv("MIN_RETRIEVAL_SCORE", "0.35"))
SESSION_TTL_SECONDS = 8 * 60 * 60
SESSION_COOKIE = "alpha_knowledge_session"
ALLOWED_EXTENSIONS = {".md", ".txt", ".html", ".pdf"}
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_demo_users()
    yield


app = FastAPI(title="Enterprise Knowledge Assistant", version="0.1.0", lifespan=lifespan)


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL,
          owner TEXT NOT NULL, version TEXT NOT NULL, effective_from TEXT,
          effective_to TEXT, groups_json TEXT NOT NULL, source_hash TEXT NOT NULL,
          ingested_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
          UNIQUE(filename, version)
        );
        CREATE TABLE IF NOT EXISTS chunks (
          id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
          ordinal INTEGER NOT NULL, page INTEGER, heading TEXT, body TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
          chunk_id UNINDEXED, body, heading, title, tokenize='unicode61'
        );
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, filename TEXT NOT NULL, status TEXT NOT NULL,
          reason TEXT, created_at TEXT NOT NULL, completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS feedback (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, question_hash TEXT NOT NULL,
          chunk_ids_json TEXT NOT NULL, rating INTEGER NOT NULL, reason TEXT,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash BLOB NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('employee','admin')), groups_json TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_events (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, action TEXT NOT NULL,
          resource_id TEXT, details_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """)



def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_secret() -> str:
    secret = os.getenv("KNOWLEDGE_SESSION_SECRET")
    if secret:
        return secret
    path = ROOT / "instance" / "session.secret"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        secret = secrets.token_urlsafe(48)
        try:
            path.write_text(secret, encoding="utf-8")
        except FileExistsError:
            secret = path.read_text(encoding="utf-8").strip()
        return secret


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_session_secret(), salt="alpha-knowledge-session-v1")


def seed_demo_users() -> None:
    """Create local demo accounts; generated passwords are printed only on first seed."""
    users = (
        ("alice", "employee", ["general", "finance"], "ALPHA_DEMO_ALICE_PASSWORD"),
        ("bob", "employee", ["general"], "ALPHA_DEMO_BOB_PASSWORD"),
        ("admin", "admin", ["general", "finance", "hr", "security", "procurement"], "ALPHA_DEMO_ADMIN_PASSWORD"),
    )
    generated = []
    with connect() as db:
        for username, role, groups, password_env in users:
            exists = db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
            if exists:
                continue
            password = os.getenv(password_env) or secrets.token_urlsafe(18)
            hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
            user_id = str(uuid.uuid4())
            db.execute("INSERT INTO users VALUES(?,?,?,?,?,1,?)",
                       (user_id, username, hashed, role, json.dumps(groups), now()))
            if not os.getenv(password_env):
                generated.append(f"{username}: {password}")
    if generated:
        print("Project Alpha demo passwords (save these; they are shown only at initial seed): " + " | ".join(generated))


def record_event(db: sqlite3.Connection, user: dict, action: str, resource_id: str | None = None,
                 details: dict | None = None) -> None:
    db.execute("INSERT INTO audit_events VALUES(?,?,?,?,?,?)", (
        str(uuid.uuid4()), user["id"], action, resource_id,
        json.dumps(details or {}, sort_keys=True), now()))


def current_user(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "Sign in to use the Knowledge Assistant.")
    try:
        claims = _serializer().loads(token, max_age=SESSION_TTL_SECONDS)
    except (BadSignature, SignatureExpired) as exc:
        raise HTTPException(401, "Your session has expired. Sign in again.") from exc
    with connect() as db:
        row = db.execute("SELECT id,username,role,groups_json,active FROM users WHERE id=?", (claims.get("sub"),)).fetchone()
    if not row or not row["active"]:
        raise HTTPException(401, "This account is unavailable. Sign in again.")
    return {"id": row["id"], "username": row["username"], "role": row["role"],
            "groups": json.loads(row["groups_json"])}


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Administrator access is required for this action.")
    return user


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


def extract(filename: str, raw: bytes) -> list[tuple[int | None, str]]:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type. Use Markdown, TXT, HTML, or PDF.")
    if ext == ".pdf":
        doc = fitz.open(stream=raw, filetype="pdf")
        pages = [(i + 1, p.get_text("text").strip()) for i, p in enumerate(doc)]
        if not any(text for _, text in pages):
            raise ValueError("PDF contains no extractable text; scanned PDFs need OCR and manual review.")
        return pages
    text = raw.decode("utf-8-sig")
    if ext == ".html":
        text = BeautifulSoup(text, "html.parser").get_text("\n")
    return [(None, text)]


def make_chunks(pages: list[tuple[int | None, str]], max_chars: int = 1100) -> list[tuple[int | None, str | None, str]]:
    result: list[tuple[int | None, str | None, str]] = []
    for page, text in pages:
        heading = None
        parts: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                if parts:
                    result.extend((page, heading, c) for c in split_text("\n".join(parts), max_chars))
                    parts = []
                heading = line.lstrip("# ").strip() or heading
            else:
                parts.append(line)
        if parts:
            result.extend((page, heading, c) for c in split_text("\n".join(parts), max_chars))
    return result


def split_text(text: str, max_chars: int) -> list[str]:
    paras = re.split(r"(?<=[.!?])\s+|\n+", text)
    chunks: list[str] = []
    current = ""
    for para in paras:
        para = para.strip()
        if not para:
            continue
        if current and len(current) + len(para) + 1 > max_chars:
            chunks.append(current)
            current = ""
        if len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(para[i:i + max_chars] for i in range(0, len(para), max_chars))
        else:
            current = f"{current} {para}".strip()
    if current:
        chunks.append(current)
    return chunks


def ingest(filename: str, raw: bytes, title: str, owner: str, version: str,
           groups: list[str], effective_from: str | None, effective_to: str | None) -> dict:
    job_id = str(uuid.uuid4())
    stamp = now()
    digest = hashlib.sha256(raw).hexdigest()
    with connect() as db:
        db.execute("INSERT INTO jobs VALUES(?,?, 'RUNNING',NULL,?,NULL)", (job_id, filename, stamp))
    try:
        if not groups or any(not g.strip() for g in groups):
            raise ValueError("At least one non-empty access group is required.")
        if effective_from and effective_to and effective_to < effective_from:
            raise ValueError("effective_to must be on or after effective_from.")
        pages = extract(filename, raw)
        chunks = make_chunks(pages)
        if not chunks:
            raise ValueError("No readable text was found in the source.")
        with connect() as db:
            prior = db.execute("SELECT id,source_hash FROM documents WHERE filename=? AND version=?", (filename, version)).fetchone()
            if prior and prior["source_hash"] == digest:
                db.execute("UPDATE jobs SET status='COMPLETED',completed_at=? WHERE id=?", (now(), job_id))
                return {"job_id": job_id, "document_id": prior["id"], "status": "COMPLETED", "chunks": 0, "duplicate": True}
            if prior:
                db.execute("UPDATE documents SET active=0 WHERE id=?", (prior["id"],))
            db.execute("UPDATE documents SET active=0 WHERE filename=?", (filename,))
            doc_id = str(uuid.uuid4())
            db.execute("INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,1)",
                       (doc_id, title, filename, owner, version, effective_from, effective_to,
                        json.dumps(sorted(set(groups))), digest, now()))
            for index, (page, heading, body) in enumerate(chunks):
                chunk_id = str(uuid.uuid4())
                db.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?)", (chunk_id, doc_id, index, page, heading, body))
                db.execute("INSERT INTO chunks_fts VALUES(?,?,?,?)", (chunk_id, body, heading or "", title))
            db.execute("UPDATE jobs SET status='COMPLETED',completed_at=? WHERE id=?", (now(), job_id))
        return {"job_id": job_id, "document_id": doc_id, "status": "COMPLETED", "chunks": len(chunks), "duplicate": False}
    except Exception as exc:
        with connect() as db:
            db.execute("UPDATE jobs SET status='NEEDS_REVIEW',reason=?,completed_at=? WHERE id=?", (str(exc)[:500], now(), job_id))
        raise


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    limit: int = Field(default=5, ge=1, le=10)


class FeedbackRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    chunk_ids: list[str] = Field(max_length=10)
    rating: int = Field(ge=0, le=1)
    reason: str | None = Field(default=None, max_length=500)


@app.get("/health")
def health() -> dict:
    try:
        with connect() as db:
            db.execute("SELECT 1").fetchone()
        return {"status": "ok", "time": now(), "database": "ready"}
    except sqlite3.Error:
        return {"status": "error", "database": "unavailable"}


@app.post("/api/login")
def login(payload: LoginRequest, response: Response) -> dict:
    with connect() as db:
        row = db.execute("SELECT id,password_hash,active FROM users WHERE username=?", (payload.username.strip().casefold(),)).fetchone()
    supplied = payload.password.encode("utf-8")
    try:
        valid_password = bool(row and row["active"] and bcrypt.checkpw(supplied, row["password_hash"]))
    except ValueError:
        valid_password = False
    if not valid_password:
        raise HTTPException(401, "Username or password is incorrect.")
    token = _serializer().dumps({"sub": row["id"]})
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_TTL_SECONDS, httponly=True,
                        secure=os.getenv("ALPHA_HTTPS", "0") == "1", samesite="lax", path="/")
    with connect() as db:
        record_event(db, {"id": row["id"]}, "login")
    return {"status": "signed_in"}


@app.post("/api/logout")
def logout(response: Response, user: dict = Depends(current_user)) -> dict:
    with connect() as db:
        record_event(db, user, "logout")
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")
    return {"status": "signed_out"}


@app.get("/api/me")
def me(user: dict = Depends(current_user)) -> dict:
    return {"user": user}


@app.post("/api/documents")
async def upload_document(file: Annotated[UploadFile, File()], title: Annotated[str, Form()],
                          owner: Annotated[str, Form()] = "demo-owner",
                          version: Annotated[str, Form()] = "1",
                          access_groups: Annotated[str, Form()] = "general",
                          effective_from: Annotated[str | None, Form()] = None,
                          effective_to: Annotated[str | None, Form()] = None,
                          user: dict = Depends(require_admin)) -> dict:
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds the configured upload limit.")
    try:
        for value in (effective_from, effective_to):
            if value:
                date.fromisoformat(value)
        result = ingest(file.filename or "upload.txt", raw, title.strip(), owner.strip(), version.strip(),
                        [g.strip() for g in access_groups.split(",") if g.strip()], effective_from, effective_to)
        with connect() as db:
            record_event(db, user, "document.upload", result["document_id"], {"filename": file.filename, "title": title.strip()})
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "A document with this filename and version already exists with different content.") from exc


@app.post("/api/ask")
def ask(payload: AskRequest, user: dict = Depends(current_user)) -> dict:
    return retrieve(payload, user)


def retrieve(payload: AskRequest, user: dict) -> dict:
    groups = sorted(set(user["groups"]))
    stop_words = {"what", "which", "when", "where", "who", "how", "is", "are", "the", "a", "an", "of", "to", "for", "in", "on", "i", "do", "does", "can", "my", "me", "please", "tell"}
    terms = [t for t in re.findall(r"[\w'-]{2,}", payload.question.lower()) if t not in stop_words]
    if not terms:
        return {"answer": "I cannot verify this from the available sources.", "abstained": True, "citations": []}
    # OR query supports natural questions while avoiding unsafe FTS syntax from user input.
    match = " OR ".join('"' + t.replace('"', '') + '"' for t in sorted(set(terms))[:20])
    today = date.today().isoformat()
    with connect() as db:
        group_slots = ",".join("?" for _ in groups)
        rows = db.execute(f"""
          SELECT c.id,c.document_id,c.page,c.heading,c.body,d.title,d.filename,d.version,d.groups_json,
                 d.effective_from,d.effective_to,d.ingested_at,bm25(chunks_fts) AS rank
          FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.chunk_id
          JOIN documents d ON d.id=c.document_id
          WHERE chunks_fts MATCH ? AND d.active=1
            AND (d.effective_from IS NULL OR d.effective_from<=?)
            AND (d.effective_to IS NULL OR d.effective_to>=?)
            AND EXISTS (SELECT 1 FROM json_each(d.groups_json) AS acl WHERE acl.value IN ({group_slots}))
          ORDER BY rank LIMIT 100
        """, (match, today, today, *groups)).fetchall()
    # FTS5 BM25 is negative: lower values are better. Score is normalized for a simple abstention gate.
    citations = []
    for row in rows[:payload.limit]:
        score = max(0.0, 1.0 / (1.0 + abs(float(row["rank"]))))
        haystack = " ".join((row["title"], row["heading"] or "", row["body"])).lower()
        coverage = sum(1 for term in set(terms) if term in haystack) / max(1, len(set(terms)))
        if coverage < MIN_SCORE:
            continue
        citations.append({"chunk_id": row["id"], "document_id": row["document_id"], "title": row["title"],
                          "filename": row["filename"], "version": row["version"], "page": row["page"],
                          "heading": row["heading"], "excerpt": row["body"], "effective_from": row["effective_from"],
                          "effective_to": row["effective_to"], "last_indexed": row["ingested_at"], "score": round(score, 4)})
    abstained = not citations
    answer = ("I cannot verify this from the available sources." if abstained else
              "Here are the most relevant approved source excerpts. Review the cited policy text before acting.")
    return {"answer": answer, "abstained": abstained, "citations": citations}


@app.post("/api/feedback", status_code=201)
def feedback(payload: FeedbackRequest, user: dict = Depends(current_user)) -> dict:
    with connect() as db:
        for chunk_id in payload.chunk_ids:
            row = db.execute("""SELECT d.groups_json FROM chunks c JOIN documents d ON d.id=c.document_id
                               WHERE c.id=? AND d.active=1""", (chunk_id,)).fetchone()
            if not row or not set(user["groups"]).intersection(json.loads(row[0])):
                raise HTTPException(404, "One or more cited sources are unavailable.")
        db.execute("INSERT INTO feedback VALUES(?,?,?,?,?,?,?)", (str(uuid.uuid4()), user["id"],
                   hashlib.sha256(payload.question.encode()).hexdigest(), json.dumps(payload.chunk_ids),
                   payload.rating, payload.reason, now()))
        record_event(db, user, "feedback.submit", details={"rating": payload.rating})
    return {"status": "recorded"}


@app.get("/api/admin/status")
def admin_status(user: dict = Depends(require_admin)) -> dict:
    with connect() as db:
        docs = db.execute("SELECT id,title,filename,version,owner,groups_json,effective_from,effective_to,ingested_at,active FROM documents ORDER BY ingested_at DESC").fetchall()
        jobs = db.execute("SELECT id,filename,status,reason,created_at,completed_at FROM jobs ORDER BY created_at DESC LIMIT 100").fetchall()
    return {"documents": [{**dict(r), "access_groups": json.loads(r["groups_json"])} for r in docs], "jobs": [dict(r) for r in jobs]}


@app.post("/api/documents/{document_id}/retire")
def retire(document_id: str, user: dict = Depends(require_admin)) -> dict:
    with connect() as db:
        cur = db.execute("UPDATE documents SET active=0 WHERE id=? AND active=1", (document_id,))
        if not cur.rowcount:
            raise HTTPException(404, "Active document not found.")
        # Remove from search index immediately; chunks remain for audit.
        ids = [r[0] for r in db.execute("SELECT id FROM chunks WHERE document_id=?", (document_id,))]
        db.executemany("DELETE FROM chunks_fts WHERE chunk_id=?", [(i,) for i in ids])
        record_event(db, user, "document.retire", document_id)
    return {"status": "retired", "document_id": document_id}


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Knowledge Assistant</title>
    <style>body{font:15px system-ui;max-width:900px;margin:3rem auto;padding:0 1rem;color:#17252a;background:#f7faf8}input,textarea{font:inherit;padding:.65rem;border:1px solid #c7d3cf;border-radius:6px}button{font:inherit;padding:.65rem 1rem;border:0;border-radius:6px;background:#17604c;color:white;cursor:pointer}form{display:flex;gap:.6rem;flex-wrap:wrap;margin:1rem 0}textarea{width:100%;min-height:90px}section{background:white;border:1px solid #dce5e1;border-radius:10px;padding:1rem;margin:1rem 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}.muted{color:#586a64;font-size:.9rem}</style></head><body>
    <h1>Enterprise Knowledge Assistant</h1><p class="muted">Fictional demo documents. Access groups are resolved from your signed-in account.</p>
    <section><h2 id="identity">Sign in</h2><p id="groups" class="muted">Demo credentials are printed once in the server terminal on first start.</p><form id="login"><input name="username" autocomplete="username" aria-label="Username" placeholder="Username" required><input name="password" type="password" autocomplete="current-password" aria-label="Password" placeholder="Password" required><button>Sign in</button></form><button id="logout" hidden>Sign out</button></section>
    <section><h2>Search approved documents</h2><form id="ask"><textarea name="question" minlength="3" placeholder="What is the travel claim limit?" required></textarea><button>Search sources</button></form><pre id="result" aria-live="polite"></pre></section>
    <section id="admin" hidden><h2>Administrator tools</h2><form id="upload"><input name="file" type="file" accept=".md,.txt,.html,.pdf" required><input name="title" placeholder="Document title" required><input name="access_groups" value="general" aria-label="Access groups"><button>Index document</button></form><button id="status">Refresh ingestion status</button><pre id="statusResult"></pre></section>
    <script>
    const $=s=>document.querySelector(s), api=(path,opts={})=>fetch(path,{credentials:'same-origin',...opts});
    async function refresh(){try{let r=await api('/api/me'),d=await r.json();if(!r.ok)throw Error();$('#identity').textContent='Signed in as '+d.user.username+' ('+d.user.role+')';$('#groups').textContent='Authorized groups: '+d.user.groups.join(', ');$('#login').hidden=true;$('#logout').hidden=false;$('#admin').hidden=d.user.role!=='admin'}catch{$('#identity').textContent='Sign in';$('#groups').textContent='Use the demo credentials printed once in the server terminal on first start.';$('#login').hidden=false;$('#logout').hidden=true;$('#admin').hidden=true}}
    $('#login').onsubmit=async e=>{e.preventDefault();let d=Object.fromEntries(new FormData(e.currentTarget));let r=await api('/api/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(d)});if(!r.ok){$('#result').textContent=(await r.json()).detail;return}e.currentTarget.reset();await refresh()};
    $('#logout').onclick=async()=>{await api('/api/logout',{method:'POST'});await refresh()};
    $('#ask').onsubmit=async e=>{e.preventDefault();let r=await api('/api/ask',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({question:new FormData(e.currentTarget).get('question')})});$('#result').textContent=JSON.stringify(await r.json(),null,2)};
    $('#upload').onsubmit=async e=>{e.preventDefault();let r=await api('/api/documents',{method:'POST',body:new FormData(e.currentTarget)});$('#statusResult').textContent=JSON.stringify(await r.json(),null,2)};
    $('#status').onclick=async()=>{$('#statusResult').textContent=JSON.stringify(await(await api('/api/admin/status')).json(),null,2)};refresh();
    </script></body></html>"""

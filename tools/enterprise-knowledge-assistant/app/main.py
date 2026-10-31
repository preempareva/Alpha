from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated

import fitz
from bs4 import BeautifulSoup
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("DATABASE_PATH", str(ROOT / "instance" / "knowledge.db")))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "10000000"))
MIN_SCORE = float(os.getenv("MIN_RETRIEVAL_SCORE", "0.35"))
ALLOWED_EXTENSIONS = {".md", ".txt", ".html", ".pdf"}
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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
        """)



def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def user_context(x_user_id: str = "demo-user", x_user_groups: str = "general") -> tuple[str, set[str]]:
    groups = {g.strip() for g in x_user_groups.split(",") if g.strip()}
    return x_user_id.strip() or "demo-user", groups


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
    return {"status": "ok", "time": now()}


@app.post("/api/documents")
async def upload_document(file: Annotated[UploadFile, File()], title: Annotated[str, Form()],
                          owner: Annotated[str, Form()] = "demo-owner",
                          version: Annotated[str, Form()] = "1",
                          access_groups: Annotated[str, Form()] = "general",
                          effective_from: Annotated[str | None, Form()] = None,
                          effective_to: Annotated[str | None, Form()] = None) -> dict:
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds the configured upload limit.")
    try:
        for value in (effective_from, effective_to):
            if value:
                date.fromisoformat(value)
        return ingest(file.filename or "upload.txt", raw, title.strip(), owner.strip(), version.strip(),
                      [g.strip() for g in access_groups.split(",") if g.strip()], effective_from, effective_to)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "A document with this filename and version already exists with different content.") from exc


@app.post("/api/ask")
def ask(payload: AskRequest, x_user_id: Annotated[str, Header()] = "demo-user",
        x_user_groups: Annotated[str, Header()] = "general") -> dict:
    user_id, groups = user_context(x_user_id, x_user_groups)
    stop_words = {"what", "which", "when", "where", "who", "how", "is", "are", "the", "a", "an", "of", "to", "for", "in", "on", "i", "do", "does", "can", "my", "me", "please", "tell"}
    terms = [t for t in re.findall(r"[\w'-]{2,}", payload.question.lower()) if t not in stop_words]
    if not terms:
        return {"answer": "I cannot verify this from the available sources.", "abstained": True, "citations": []}
    # OR query supports natural questions while avoiding unsafe FTS syntax from user input.
    match = " OR ".join('"' + t.replace('"', '') + '"' for t in sorted(set(terms))[:20])
    today = date.today().isoformat()
    with connect() as db:
        rows = db.execute("""
          SELECT c.id,c.document_id,c.page,c.heading,c.body,d.title,d.filename,d.version,d.groups_json,
                 d.effective_from,d.effective_to,d.ingested_at,bm25(chunks_fts) AS rank
          FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.chunk_id
          JOIN documents d ON d.id=c.document_id
          WHERE chunks_fts MATCH ? AND d.active=1
            AND (d.effective_from IS NULL OR d.effective_from<=?)
            AND (d.effective_to IS NULL OR d.effective_to>=?)
          ORDER BY rank LIMIT 100
        """, (match, today, today)).fetchall()
    visible = []
    for row in rows:
        allowed = set(json.loads(row["groups_json"]))
        if groups & allowed:
            visible.append(row)
    # FTS5 BM25 is negative: lower values are better. Score is normalized for a simple abstention gate.
    citations = []
    for row in visible[:payload.limit]:
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
def feedback(payload: FeedbackRequest, x_user_id: Annotated[str, Header()] = "demo-user") -> dict:
    user_id, groups = user_context(x_user_id)
    with connect() as db:
        for chunk_id in payload.chunk_ids:
            row = db.execute("""SELECT d.groups_json FROM chunks c JOIN documents d ON d.id=c.document_id
                               WHERE c.id=? AND d.active=1""", (chunk_id,)).fetchone()
            if not row or not groups.intersection(json.loads(row[0])):
                raise HTTPException(404, "One or more cited sources are unavailable.")
        db.execute("INSERT INTO feedback VALUES(?,?,?,?,?,?,?)", (str(uuid.uuid4()), user_id,
                   hashlib.sha256(payload.question.encode()).hexdigest(), json.dumps(payload.chunk_ids),
                   payload.rating, payload.reason, now()))
    return {"status": "recorded"}


@app.get("/api/admin/status")
def admin_status() -> dict:
    with connect() as db:
        docs = db.execute("SELECT id,title,filename,version,owner,groups_json,effective_from,effective_to,ingested_at,active FROM documents ORDER BY ingested_at DESC").fetchall()
        jobs = db.execute("SELECT id,filename,status,reason,created_at,completed_at FROM jobs ORDER BY created_at DESC LIMIT 100").fetchall()
    return {"documents": [{**dict(r), "access_groups": json.loads(r["groups_json"])} for r in docs], "jobs": [dict(r) for r in jobs]}


@app.post("/api/documents/{document_id}/retire")
def retire(document_id: str) -> dict:
    with connect() as db:
        cur = db.execute("UPDATE documents SET active=0 WHERE id=? AND active=1", (document_id,))
        if not cur.rowcount:
            raise HTTPException(404, "Active document not found.")
        # Remove from search index immediately; chunks remain for audit.
        ids = [r[0] for r in db.execute("SELECT id FROM chunks WHERE document_id=?", (document_id,))]
        db.executemany("DELETE FROM chunks_fts WHERE chunk_id=?", [(i,) for i in ids])
    return {"status": "retired", "document_id": document_id}


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Knowledge Assistant</title>
    <style>body{font:16px system-ui;max-width:850px;margin:3rem auto;padding:0 1rem;color:#20252b}textarea,input{width:100%;padding:.7rem;margin:.35rem 0 1rem;box-sizing:border-box}button{padding:.7rem 1rem;background:#164e63;color:white;border:0;border-radius:5px;cursor:pointer}article{border:1px solid #ccd5dc;padding:1rem;margin:.7rem 0;border-radius:6px}.muted{color:#566}small{display:block}</style></head><body>
    <h1>Enterprise Knowledge Assistant</h1><p class=muted>Demo corpus only. Answers show approved source excerpts; the assistant abstains when it cannot find evidence.</p>
    <label>Demo identity <select id=user><option value='alice|general,finance'>Alice (general + finance)</option><option value='bob|general'>Bob (general)</option></select></label>
    <form id=ask><label for=q>Ask a question</label><textarea id=q minlength=3 required placeholder='What is the travel claim limit?'></textarea><button>Search approved knowledge</button></form>
    <section id=result aria-live=polite></section><h2>Ingestion status</h2><button id=refresh>Refresh status</button><section id=status></section>
    <script>
    const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    document.querySelector('#ask').onsubmit=async e=>{e.preventDefault();let [id,groups]=document.querySelector('#user').value.split('|');let r=await fetch('/api/ask',{method:'POST',headers:{'content-type':'application/json','x-user-id':id,'x-user-groups':groups},body:JSON.stringify({question:document.querySelector('#q').value})});let d=await r.json();document.querySelector('#result').innerHTML=`<p><b>${esc(d.answer)}</b></p>`+d.citations.map(c=>`<article><b>${esc(c.title)}</b> · v${esc(c.version)}<small>${esc(c.filename)}${c.page?' · page '+c.page:''}${c.heading?' · '+esc(c.heading):''}</small><p>${esc(c.excerpt)}</p><small>Last indexed: ${esc(c.last_indexed)}</small></article>`).join('')};
    async function status(){let d=await(await fetch('/api/admin/status')).json();document.querySelector('#status').innerHTML=d.documents.map(x=>`<article>${esc(x.title)} · v${esc(x.version)} · ${x.active?'active':'retired'} · groups: ${esc(x.access_groups.join(', '))}</article>`).join('')||'<p>No documents indexed yet.</p>'};document.querySelector('#refresh').onclick=status;status();
    </script></body></html>"""


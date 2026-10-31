from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
import os
import re
import sqlite3
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.getenv("HELPDESK_DB", str(ROOT / "instance/helpdesk.db")))
@asynccontextmanager
async def lifespan(app: FastAPI):
    init()
    yield


app = FastAPI(title="Helpdesk Triage", version="0.1.0", lifespan=lifespan)
KB = [
    {"id":"kb-password","title":"Password reset","text":"Reset your own password using the company identity portal. Never share passwords or one-time codes with support."},
    {"id":"kb-vpn","title":"VPN connection","text":"Check your internet connection, restart the approved VPN client, and confirm the device clock is correct. Contact the service desk if the error continues."},
    {"id":"kb-device","title":"Lost device","text":"Report a lost company device to the service desk immediately. Do not try to wipe or track it yourself."},
    {"id":"kb-email","title":"Suspicious email","text":"Use the report-phishing button. Do not open unexpected attachments or follow sign-in links."},
]


@contextmanager
def dbconn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init():
    with dbconn() as con:
        con.execute("CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY, description TEXT NOT NULL, category TEXT, priority TEXT, article_id TEXT, status TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, approved_at TEXT)")



class Intake(BaseModel):
    description: str = Field(min_length=12, max_length=3000)


def classify(text: str) -> tuple[str, str]:
    t = text.lower()
    if any(w in t for w in ("lost laptop", "stolen device", "lost device")):
        return "security-device", "urgent"
    if any(w in t for w in ("phishing", "suspicious email", "malware")):
        return "security", "high"
    if any(w in t for w in ("vpn", "network", "wifi", "wi-fi")):
        return "network", "normal"
    if any(w in t for w in ("password", "login", "sign in", "account")):
        return "account", "normal"
    return "general", "normal"


def suggest(text: str) -> dict | None:
    terms = set(re.findall(r"[a-z]{3,}", text.lower()))
    ranked = []
    for article in KB:
        overlap = terms & set(re.findall(r"[a-z]{3,}", (article["title"] + " " + article["text"]).lower()))
        ranked.append((len(overlap), article))
    score, article = max(ranked, key=lambda item: item[0])
    return {"id": article["id"], "title": article["title"], "excerpt": article["text"]} if score else None


@app.get("/health")
def health():
    init()
    return {"status":"ok"}


@app.post("/api/intake")
def intake(payload: Intake):
    text = payload.description.strip()
    low = text.lower()
    if any(x in low for x in ("password is", "my password:", "one-time code", "otp is")):
        raise HTTPException(400, "Do not submit passwords or one-time codes. Remove the secret and describe the problem only.")
    category, priority = classify(text)
    article = suggest(text)
    missing = []
    if not any(re.search(r"\b" + word + r"\b", low) for word in ("windows", "mac", "linux", "ios", "android")):
        missing.append("device or operating system")
    if not any(token in low for token in ("error", "since", "started", "when", "today", "yesterday")):
        missing.append("when it started or the exact error")
    ticket_id = str(uuid.uuid4())
    with dbconn() as con:
        con.execute("INSERT INTO tickets(id,description,category,priority,article_id,status) VALUES(?,?,?,?,?,'NEEDS_REVIEW')",
                    (ticket_id, text, category, priority, article["id"] if article else None))
    return {"ticket_id":ticket_id,"status":"NEEDS_REVIEW","category_suggestion":category,
            "priority_suggestion":priority,"clarifying_questions":missing,"knowledge_article":article,
            "draft":"A technician must review and submit this ticket. No account/device action was taken."}


@app.get("/api/review")
def review_queue():
    init()
    with dbconn() as con:
        rows = con.execute("SELECT id,description,category,priority,status,created_at FROM tickets WHERE status='NEEDS_REVIEW' ORDER BY created_at DESC").fetchall()
    return {"items":[dict(r) for r in rows]}


@app.post("/api/tickets/{ticket_id}/approve")
def approve(ticket_id: str):
    # Local demo state transition only; no external ticketing integration.
    with dbconn() as con:
        cur = con.execute("UPDATE tickets SET status='APPROVED',approved_at=CURRENT_TIMESTAMP WHERE id=? AND status='NEEDS_REVIEW'", (ticket_id,))
        if cur.rowcount != 1:
            raise HTTPException(404,"Reviewable ticket not found.")
    return {"ticket_id":ticket_id,"status":"APPROVED","notice":"Demo approval recorded; no external ticket was created."}


@app.get("/", response_class=HTMLResponse)
def home():
    return """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Helpdesk Triage</title><style>body{font:16px system-ui;max-width:800px;margin:3rem auto;padding:0 1rem}textarea{width:100%;height:130px;padding:.6rem}button{padding:.7rem 1rem;background:#164e63;color:white;border:0;border-radius:5px}pre{white-space:pre-wrap;background:#f1f4f5;padding:1rem}</style></head><body><h1>Helpdesk Triage</h1><p>Synthetic prototype: offers safe KB guidance and drafts a ticket for technician review.</p><form id=f><textarea id=q required minlength=12 placeholder='Describe your IT issue; do not include passwords or codes'></textarea><button>Get help / draft ticket</button></form><pre id=o aria-live=polite></pre><script>f.onsubmit=async e=>{e.preventDefault();let r=await fetch('/api/intake',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({description:q.value})});o.textContent=JSON.stringify(await r.json(),null,2)}</script></body></html>"""

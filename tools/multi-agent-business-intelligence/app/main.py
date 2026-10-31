from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .workflow import run_workflow

app = FastAPI(title="Controlled Multi-Agent BI Prototype", version="0.1.0")


class Ask(BaseModel):
    question: str = Field(min_length=4, max_length=500)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/ask")
def ask(payload: Ask):
    try:
        return run_workflow(payload.question)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/trace")
def trace_example():
    try:
        return run_workflow("Show monthly revenue")
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/", response_class=HTMLResponse)
def home():
    return """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Controlled BI</title><style>body{font:16px system-ui;max-width:850px;margin:3rem auto;padding:0 1rem;color:#20252b}input{width:100%;padding:.7rem;margin:.5rem 0}button{padding:.7rem 1rem;background:#164e63;color:white;border:0;border-radius:5px}pre{white-space:pre-wrap;background:#f1f4f5;padding:1rem;overflow:auto}</style></head><body><h1>Controlled BI assistant</h1><p>Ask about synthetic monthly revenue, top products, or refund rates. The workflow only uses approved read-only tools.</p><form id=f><input id=q value='Show monthly revenue'><button>Run analysis</button></form><pre id=o aria-live=polite></pre><script>f.onsubmit=async e=>{e.preventDefault();const r=await fetch('/api/ask',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({question:q.value})});o.textContent=JSON.stringify(await r.json(),null,2)}</script></body></html>"""

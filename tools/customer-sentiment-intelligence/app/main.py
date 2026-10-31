from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from .logic import analyze, load_model

app = FastAPI(title="Customer Sentiment Intelligence", version="0.1.0")


class Review(BaseModel):
    text: str = Field(min_length=5, max_length=3000)


@app.get("/health")
def health():
    return {"status":"ok"}


@app.post("/api/analyze")
def analyze_review(payload: Review):
    try:
        return analyze(load_model(), payload.text)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/", response_class=HTMLResponse)
def home():
    return """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Review Insights</title><style>body{font:16px system-ui;max-width:800px;margin:3rem auto;padding:0 1rem}textarea{width:100%;height:120px;padding:.7rem}button{padding:.7rem 1rem;background:#164e63;color:white;border:0;border-radius:5px}pre{background:#f1f4f5;padding:1rem}</style></head><body><h1>Customer sentiment insights</h1><p>Synthetic demonstration. Theme labels are simple keyword signals; they are not discovered business facts.</p><form id=f><textarea id=t minlength=5 placeholder='Paste a synthetic customer review'></textarea><button>Analyze</button></form><pre id=o aria-live=polite></pre><script>f.onsubmit=async e=>{e.preventDefault();let r=await fetch('/api/analyze',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({text:t.value})});o.textContent=JSON.stringify(await r.json(),null,2)}</script></body></html>"""

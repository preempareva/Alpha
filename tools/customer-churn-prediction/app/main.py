from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .model import FEATURES, METRICS_PATH, load_bundle, score_rows

app = FastAPI(title="Customer Churn Risk Prototype", version="0.1.0")


class CustomerFeatures(BaseModel):
    customer_id: str = Field(min_length=1, max_length=80)
    tenure_months: float = Field(ge=0, le=600)
    active_days_30d: float = Field(ge=0, le=31)
    sessions_30d: float = Field(ge=0, le=10000)
    usage_change_30d: float = Field(ge=-1, le=10)
    support_tickets_90d: float = Field(ge=0, le=500)
    late_payments_90d: float = Field(ge=0, le=90)
    monthly_fee: float = Field(ge=0, le=1000000)
    plan: str = Field(min_length=1, max_length=40)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Churn Risk Review</title>
    <style>body{font:16px system-ui;max-width:780px;margin:3rem auto;padding:0 1rem;color:#20252b}label{display:block;margin:.65rem 0}input,select{padding:.5rem;margin-left:.5rem}button{padding:.7rem 1rem;background:#164e63;color:white;border:0;border-radius:5px;cursor:pointer}article{border:1px solid #ccd5dc;padding:1rem;margin:.7rem 0;border-radius:6px}.notice{color:#566}</style></head><body>
    <h1>Customer churn risk review</h1><p class=notice>Synthetic demonstration only. Scores are uncertain prioritization signals, not reasons to deny service or automatic outreach.</p>
    <form id=form><label>Demo customer ID <input name=customer_id value='SYN-demo' required></label>
    <label>Tenure (months) <input name=tenure_months type=number min=0 value=8 required></label>
    <label>Active days (last 30) <input name=active_days_30d type=number min=0 max=31 value=8 required></label>
    <label>Sessions (last 30) <input name=sessions_30d type=number min=0 value=14 required></label>
    <label>Usage change <input name=usage_change_30d type=number min=-1 max=10 step=.01 value=-.25 required></label>
    <label>Support tickets (last 90) <input name=support_tickets_90d type=number min=0 value=2 required></label>
    <label>Late payments (last 90) <input name=late_payments_90d type=number min=0 value=1 required></label>
    <label>Monthly fee <input name=monthly_fee type=number min=0 value=55 required></label>
    <label>Plan <select name=plan><option>basic</option><option selected>standard</option><option>premium</option></select></label>
    <button>Score for analyst review</button></form><section id=result aria-live=polite></section>
    <script>document.querySelector('#form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target),v=Object.fromEntries(f);for(const k of ['tenure_months','active_days_30d','sessions_30d','usage_change_30d','support_tickets_90d','late_payments_90d','monthly_fee'])v[k]=Number(v[k]);const r=await fetch('/api/score',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(v)});const d=await r.json();document.querySelector('#result').innerHTML=r.ok?`<article><h2>${Math.round(d.risk_probability*100)}% · ${d.risk_band} review band</h2><p>Possible review signals: ${d.reasons.join(', ')||'no unusual signals identified'}</p><p>${d.notice}</p></article>`:`<p role=alert>${d.detail||'Request failed'}</p>`};</script></body></html>"""


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/metrics")
def metrics() -> dict:
    if not METRICS_PATH.exists():
        raise HTTPException(503, "Train a model before requesting metrics.")
    return json.loads(METRICS_PATH.read_text(encoding="utf-8"))


@app.post("/api/score")
def score(payload: CustomerFeatures) -> dict:
    try:
        bundle = load_bundle()
        values = payload.model_dump()
        customer_id = values.pop("customer_id")
        rows = pd.DataFrame([{k: values[k] for k in FEATURES}])
        result = score_rows(bundle, rows)[0]
        return {"customer_id": customer_id, **result,
                "horizon_days": 60,
                "notice": "Synthetic prototype score. Review evidence with a human; this is not a certainty or causal explanation."}
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc

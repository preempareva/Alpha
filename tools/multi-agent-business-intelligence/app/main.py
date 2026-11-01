import os
from importlib import import_module
from pathlib import Path
from typing import Annotated, Any

from alpha_core.agent import AgentIdentity, TraceStore
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .agent import AmbiguousQuestion, UnsupportedQuestion, run_bi_agent
from .workflow import run_workflow

app = FastAPI(title="BI Analyst Workflow", version="0.1.0")
ROOT = Path(__file__).resolve().parents[1]
TRACE_PATH = Path(os.getenv("ALPHA_BI_TRACE_PATH", str(ROOT / "data/runtime/bi-agent-traces.db")))
TRACE_STORE = TraceStore(TRACE_PATH)


class Ask(BaseModel):
    question: str = Field(min_length=4, max_length=500)


def authenticated_user(request: Request) -> dict:
    """Resolve the shared Knowledge Assistant signed session at request time."""
    current_user = import_module("tools.enterprise-knowledge-assistant.app.main").current_user
    return current_user(request)


def agent_identity(user: dict) -> AgentIdentity:
    """Convert only the server-resolved current_user record to runtime identity."""
    return AgentIdentity(
        user_id=str(user["id"]),
        roles=frozenset({str(user["role"])}),
        groups=frozenset(str(group) for group in user.get("groups", [])),
        workspace_id=str(user.get("workspace_id") or user["id"]),
        active=True,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/ask")
def ask(payload: Ask) -> dict[str, Any]:
    try:
        return run_workflow(payload.question)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/trace")
def trace_example() -> dict[str, Any]:
    try:
        return run_workflow("Show monthly revenue")
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/agent/ask")
def ask_agent(
    payload: Ask,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128, alias="Idempotency-Key")],
    user: dict = Depends(authenticated_user),
) -> dict[str, Any]:
    try:
        return run_bi_agent(payload.question, agent_identity(user), TRACE_STORE,
                            idempotency_key=idempotency_key)
    except AmbiguousQuestion as exc:
        return {"answer": str(exc), "findings": [], "data": [], "evidence_ids": [],
                "limitations": ["Clarify the requested analysis before running tools."],
                "trace": {"run_id": None, "steps": [], "timings": []},
                "mode": "deterministic", "status": "needs_clarification", "data_label": "SYNTHETIC"}
    except UnsupportedQuestion as exc:
        raise HTTPException(422, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, "The synthetic BI warehouse is unavailable.") from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, "BI analysis failed safely.") from exc


@app.get("/api/agent/runs/{run_id}")
def get_agent_run(run_id: str, user: dict = Depends(authenticated_user)) -> dict[str, Any]:
    identity = agent_identity(user)
    try:
        run = TRACE_STORE.get_run_for(run_id, identity)
        if run is None:
            raise HTTPException(404, "Run not found.")
        steps = TRACE_STORE.list_steps_for(run_id, identity)
        verification_passed = any(
            step["tool_name"] == "verify_totals"
            and step["state"] == "completed"
            and isinstance(step.get("result"), dict)
            and step["result"].get("verified") is True
            for step in steps
        )
        if not verification_passed:
            for step in steps:
                if step["tool_name"] != "verify_totals" and step.get("result") is not None:
                    step["result"] = {"withheld": "verification_failed"}
        return {"run": run, "steps": steps}
    except PermissionError as exc:
        raise HTTPException(404, "Run not found.") from exc


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>BI Analyst Workflow</title><style>body{font:16px system-ui;max-width:850px;margin:3rem auto;padding:0 1rem;color:#20252b;background:#f8fafb}textarea{box-sizing:border-box;width:100%;min-height:6rem;padding:.8rem;margin:.5rem 0;border:1px solid #b8c7cc;border-radius:8px;font:inherit}button{padding:.7rem 1rem;background:#164e63;color:white;border:0;border-radius:6px;font:inherit;cursor:pointer}.badge{display:inline-block;padding:.3rem .65rem;margin:.2rem;border-radius:99px;background:#dcefeb;color:#145047;font-size:.9rem}pre{white-space:pre-wrap;background:#edf2f4;padding:1rem;overflow:auto;border-radius:8px}</style></head><body><h1>BI Analyst Workflow</h1><p>Analyze the synthetic retail dataset with bounded, read-only tools. Sign in through the Knowledge Assistant session first.</p><p><span id=mode class=badge>Deterministic planner</span><span class=badge>SYNTHETIC DATA</span><span class=badge>READ ONLY</span></p><form id=f><label for=q>What would you like to analyze?</label><textarea id=q minlength=4 maxlength=500 required>Show monthly revenue</textarea><button id=run>Run analysis</button></form><pre id=o aria-live=polite></pre><script>f.onsubmit=async e=>{e.preventDefault();run.disabled=true;o.textContent='Running analysis…';try{const r=await fetch('/api/agent/ask',{method:'POST',headers:{'content-type':'application/json','Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({question:q.value})});const result=await r.json();if(result.mode)mode.textContent=result.mode==='llm_planned'?'LLM-planned (local)':'Deterministic planner';o.textContent=JSON.stringify(result,null,2)}catch(err){o.textContent='The request could not be completed.'}finally{run.disabled=false}}</script></body></html>"""

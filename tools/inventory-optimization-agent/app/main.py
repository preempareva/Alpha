"""Legacy replenishment API and the combined Inventory Control Tower screen."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from alpha_app.agent_hub import agent_identity, authenticated_user
from .logic import backtest, history, recommend
from .tower_data import InventoryTables, load_tables, validate_tables
from .tower_forecast import forecast_series
from .tower_logic import ProposalStore, inventory_position_report, json_safe
from .tower_logic import propose_transfers, risk_ranking, simulate_scenarios

SCREEN = Path(__file__).with_name("tower_screen.html")
app = FastAPI(title="Inventory Control Tower", version="1.0.0")


class Replenish(BaseModel):
    sku: str = Field(min_length=1, max_length=40)
    lead_time_weeks: int = Field(ge=1, le=26)
    on_hand: float = Field(ge=0)
    incoming: float = Field(default=0, ge=0)
    policy: str = "balanced"


def _tables() -> InventoryTables:
    try:
        tables = load_tables()
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not validate_tables(tables)["valid"]:
        raise HTTPException(503, "Synthetic inventory tables failed data-quality validation.")
    return tables


def _call(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return json_safe(function(*args, **kwargs))
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/health")
def health() -> dict[str, str]:
    try:
        report = validate_tables(load_tables())
    except FileNotFoundError:
        return {"status": "degraded"}
    return {"status": "ok" if report["valid"] else "degraded"}


# Existing API paths remain available to callers of the original two inventory demos.
@app.get("/api/backtest")
def get_backtest(sku: str = "SKU-001") -> dict[str, Any]:
    try:
        frame = history()
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    selected = frame.loc[frame.sku == sku]
    if selected.empty:
        raise HTTPException(404, "SKU not found.")
    try:
        return {"sku": sku, **backtest(selected)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/recommend")
def suggestion(payload: Replenish) -> dict[str, Any]:
    try:
        return recommend(history(), payload.sku, payload.lead_time_weeks,
                         payload.on_hand, payload.incoming, payload.policy)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/tower/quality")
def tower_quality() -> dict[str, Any]:
    try:
        return validate_tables(load_tables())
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/tower/risk")
def tower_risk(weeks: int = 6, limit: int = 20) -> dict[str, Any]:
    if not 1 <= weeks <= 26 or not 1 <= limit <= 100:
        raise HTTPException(422, "Risk horizon or row limit is outside its allowed range.")
    return _call(risk_ranking, _tables(), weeks, limit)


@app.get("/api/tower/position/{sku}/{location}")
def tower_position(sku: str, location: str) -> dict[str, Any]:
    return _call(inventory_position_report, _tables(), sku.upper(), location.upper())


@app.get("/api/tower/forecast/{sku}/{location}")
def tower_forecast(sku: str, location: str, horizon: int = 6, model: str = "auto") -> dict[str, Any]:
    return _call(forecast_series, _tables().sales_history, sku.upper(), location.upper(), horizon, model)


@app.get("/api/tower/transfers")
def tower_transfers(sku: str | None = None, limit: int = 20) -> dict[str, Any]:
    if not 1 <= limit <= 100:
        raise HTTPException(422, "Transfer row limit is outside its allowed range.")
    return _call(propose_transfers, _tables(), sku=sku.upper() if sku else None, limit=limit)


@app.get("/api/tower/scenarios")
def tower_scenarios(sku: str = "SKU-001", location: str = "LOC-001",
                    replications: int = 200) -> dict[str, Any]:
    return _call(simulate_scenarios, _tables(), sku=sku.upper(), location=location.upper(),
                 replications=replications)


@app.get("/api/tower/proposals")
def tower_proposals(user: dict[str, Any] = Depends(authenticated_user)) -> dict[str, Any]:
    return {"proposals": ProposalStore().list_for(agent_identity(user))}


@app.get("/", response_class=FileResponse)
def home() -> FileResponse:
    return FileResponse(SCREEN, media_type="text/html; charset=utf-8")

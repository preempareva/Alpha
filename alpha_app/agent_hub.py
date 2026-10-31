"""Authenticated Alpha Agent Hub routes and its bounded cross-project tool set."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Annotated, Any, Callable, cast
from uuid import uuid4

from alpha_core.agent import (
    AgentIdentity,
    AgentPlan,
    BoundedExecutor,
    LLMPlanner,
    PlanningResult,
    PolicyEngine,
    PlannerWithMode,
    ToolCall,
    ToolCallContext,
    ToolRegistry,
    ToolSpec,
    TraceState,
    TraceStore,
)
from alpha_core.auth import InvalidCsrfToken
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/agent", tags=["agent-hub"])
ROOT = Path(__file__).resolve().parents[1]
TRACE_PATH = Path(os.getenv("ALPHA_AGENT_HUB_TRACE_PATH", str(ROOT / "data/runtime/agent-hub-traces.db")))
TRACE_STORE = TraceStore(TRACE_PATH)
ANALYST_ROLES = frozenset({"employee", "admin"})
READ_TOOL_TIMEOUT_SECONDS = 8
MAX_ANALYSIS_STEPS = 4
MAX_QUESTION_LENGTH = 1000


class HubAsk(BaseModel):
    question: str = Field(min_length=4, max_length=MAX_QUESTION_LENGTH)


class ApprovalDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class ClarificationNeeded(ValueError):
    """The available information is insufficient to choose tools safely."""


class UnsupportedRequest(ValueError):
    """The Hub has no authorized read-only tool for the requested action."""


class UserRateLimiter:
    """Small process-local sliding window limiter keyed by authenticated user ID."""

    def __init__(self, *, limit: int = 30, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, user_id: str) -> None:
        now = time.monotonic()
        with self._lock:
            for key, stamps in list(self._events.items()):
                if not any(now - stamp < self.window_seconds for stamp in stamps):
                    self._events.pop(key, None)
            events = [stamp for stamp in self._events.get(user_id, [])
                      if now - stamp < self.window_seconds]
            if len(events) >= self.limit:
                self._events[user_id] = events
                raise HTTPException(429, "Request limit reached. Wait briefly and try again.")
            events.append(now)
            self._events[user_id] = events
            if len(self._events) > 10_000:
                oldest = min(self._events, key=lambda key: self._events[key][0])
                if oldest != user_id:
                    self._events.pop(oldest, None)


@dataclass
class EvidenceEntry:
    tool_name: str
    arguments: dict[str, Any]
    raw: Any
    elapsed_ms: float
    created_at: float = field(default_factory=time.monotonic)


class EvidenceCache:
    MAX_RUNS = 256
    MAX_AGE_SECONDS = 900

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, EvidenceEntry]] = {}
        self._lock = threading.RLock()

    def record(self, run_id: str, call_id: str, entry: EvidenceEntry) -> None:
        with self._lock:
            now = time.monotonic()
            for stale_run, entries in list(self._runs.items()):
                if entries and all(now - item.created_at >= self.MAX_AGE_SECONDS for item in entries.values()):
                    self._runs.pop(stale_run, None)
            self._runs.setdefault(run_id, {})[call_id] = copy.deepcopy(entry)
            while len(self._runs) > self.MAX_RUNS:
                self._runs.pop(next(iter(self._runs)))

    def get(self, run_id: str, call_id: str) -> EvidenceEntry | None:
        with self._lock:
            entry = self._runs.get(run_id, {}).get(call_id)
            if entry is None or time.monotonic() - entry.created_at >= self.MAX_AGE_SECONDS:
                return None
            return copy.deepcopy(entry)

    def drop(self, run_id: str) -> None:
        with self._lock:
            self._runs.pop(run_id, None)


RATE_LIMITER = UserRateLimiter()
EVIDENCE = EvidenceCache()


def _module(name: str) -> Any:
    return cast(Any, import_module(name))


def _knowledge_module() -> Any:
    return _module("tools.enterprise-knowledge-assistant.app.main")


def authenticated_user(request: Request) -> dict[str, Any]:
    """Resolve the signed session and user record through the existing Knowledge Assistant."""
    return _knowledge_module().current_user(request)


def agent_identity(user: dict[str, Any]) -> AgentIdentity:
    return AgentIdentity(
        user_id=str(user["id"]),
        roles=frozenset({str(user["role"])}),
        groups=frozenset(str(group) for group in user.get("groups", [])),
        workspace_id=str(user.get("workspace_id") or user["id"]),
        active=True,
    )


def _rate_limit(user: dict[str, Any]) -> None:
    RATE_LIMITER.check(str(user["id"]))


def _resolve_workspace_user(user_id: str, workspace_id: str) -> AgentIdentity:
    """Reload the original runner's active role and groups from the server account store."""
    knowledge = _knowledge_module()
    if workspace_id != str(knowledge.WORKSPACE_ID):
        raise PermissionError("approval run is outside the configured workspace")
    with knowledge.connect() as db:
        row = db.execute(
            "SELECT id,role,groups_json,active FROM users WHERE id=?", (user_id,)
        ).fetchone()
    if not row or not row["active"]:
        raise PermissionError("the original requester is no longer active")
    return agent_identity({
        "id": row["id"], "role": row["role"], "groups": json.loads(row["groups_json"]),
        "workspace_id": workspace_id,
    })


def csrf_user(
    request: Request,
    user: dict[str, Any] = Depends(authenticated_user),
) -> dict[str, Any]:
    token = request.headers.get("X-CSRF-Token", "")
    if not token:
        raise HTTPException(403, "A session CSRF token is required.")
    try:
        _knowledge_module()._session_codec().verify_csrf(token, str(user["id"]))
    except (InvalidCsrfToken, ValueError) as exc:
        raise HTTPException(403, "The session CSRF token is invalid or expired.") from exc
    _rate_limit(user)
    return user


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}


DATE_RANGE_SCHEMA = _schema({
    "start": {"type": "string", "pattern": r"^20\d\d-\d\d-\d\d$"},
    "end": {"type": "string", "pattern": r"^20\d\d-\d\d-\d\d$"},
}, ["start", "end"])
DEFAULT_DATE_RANGE = {"start": "2025-01-01", "end": "2025-12-31"}
DEMO_OPPORTUNITIES: dict[str, dict[str, Any]] = {
    "SYN-OPP-204": {"amount": 24000.0, "age_days": 32, "stage": "evaluation",
                    "touches_30d": 5, "stakeholder_count": 3},
    "SYN-OPP-205": {"amount": 81000.0, "age_days": 74, "stage": "proposal",
                    "touches_30d": 2, "stakeholder_count": 5},
}
DEMO_CUSTOMERS: dict[str, dict[str, Any]] = {
    "SYN-1042": {"tenure_months": 8, "active_days_30d": 8, "sessions_30d": 12,
                 "usage_change_30d": -0.2, "support_tickets_90d": 3, "late_payments_90d": 1,
                 "monthly_fee": 49.0, "plan": "standard"},
    "SYN-1043": {"tenure_months": 31, "active_days_30d": 25, "sessions_30d": 68,
                 "usage_change_30d": 0.12, "support_tickets_90d": 0, "late_payments_90d": 0,
                 "monthly_fee": 79.0, "plan": "premium"},
}
DEMO_SKUS = ("SKU-001", "SKU-002", "SKU-003", "SKU-004")


def _bi_data_tools() -> Any:
    return _module("tools.multi-agent-business-intelligence.app.data_tools")


def _bi_worker(tool_name: str) -> Callable[[AgentIdentity, dict[str, Any]], Any]:
    def execute(identity: AgentIdentity, arguments: dict[str, Any]) -> Any:
        del identity
        return _bi_data_tools().execute_tool(tool_name, arguments)
    return execute


def _knowledge_search(identity: AgentIdentity, arguments: dict[str, Any]) -> dict[str, Any]:
    knowledge = _knowledge_module()
    payload = knowledge.AskRequest(question=arguments["question"], limit=arguments["limit"])
    principal = {"id": identity.user_id, "role": next(iter(identity.roles)),
                 "groups": sorted(identity.groups), "workspace_id": identity.workspace_id}
    return knowledge.retrieve(payload, principal)


def _sales_score(_identity: AgentIdentity, arguments: dict[str, Any]) -> dict[str, Any]:
    sales = _module("tools.sales-pipeline-forecasting.app.main")
    demo_id = arguments["demo_id"]
    return sales.score(sales.Opportunity(opportunity_id=demo_id, **DEMO_OPPORTUNITIES[demo_id]))


def _churn_score(_identity: AgentIdentity, arguments: dict[str, Any]) -> dict[str, Any]:
    churn = _module("tools.customer-churn-prediction.app.main")
    demo_id = arguments["demo_id"]
    return churn.score(churn.CustomerFeatures(customer_id=demo_id, **DEMO_CUSTOMERS[demo_id]))


def _demand_forecast(_identity: AgentIdentity, arguments: dict[str, Any]) -> dict[str, Any]:
    forecast_module = _module("tools.intelligent-inventory-forecasting.app.forecast")
    frame = forecast_module.data()
    return forecast_module.forecast(frame, arguments["sku"], arguments["horizon"])


def _copilot_profile(identity: AgentIdentity, _arguments: dict[str, Any]) -> dict[str, Any]:
    copilot = _module("tools.business-data-copilot.app.main")
    return copilot.SERVICE.store.profile_for_hub(identity)


def _copilot_query(identity: AgentIdentity, arguments: dict[str, Any]) -> dict[str, Any]:
    copilot = _module("tools.business-data-copilot.app.main")
    return copilot.SERVICE.query(identity, arguments["question"])


def _inventory_components() -> tuple[Any, Any, Any]:
    data = _module("tools.inventory-optimization-agent.app.tower_data")
    logic = _module("tools.inventory-optimization-agent.app.tower_logic")
    forecast = _module("tools.inventory-optimization-agent.app.tower_forecast")
    return data, logic, forecast


def _inventory_read(tool_name: str) -> Callable[[AgentIdentity, dict[str, Any]], Any]:
    def execute(_identity: AgentIdentity, arguments: dict[str, Any]) -> Any:
        data, logic, forecast = _inventory_components()
        tables = data.load_tables()
        if not data.validate_tables(tables)["valid"]:
            raise ValueError("Synthetic inventory tables failed data-quality validation.")
        if tool_name == "inventory.risk_ranking":
            result = logic.risk_ranking(tables, arguments["horizon_weeks"], arguments["limit"])
        elif tool_name == "inventory.position":
            result = logic.inventory_position_report(tables, arguments["sku"], arguments["location"])
        elif tool_name == "inventory.forecast":
            result = forecast.forecast_series(
                tables.sales_history, arguments["sku"], arguments["location"], arguments["horizon_weeks"]
            )
        elif tool_name == "inventory.simulate_scenario":
            result = logic.simulate_scenarios(
                tables, sku=arguments["sku"], location=arguments["location"],
                replications=arguments["replications"], seed=arguments["seed"],
            )
        elif tool_name == "inventory.transfer_options":
            result = logic.propose_transfers(tables, sku=arguments["sku"], limit=arguments["limit"])
        else:
            raise ValueError("Inventory tool is not registered.")
        return logic.json_safe(result)
    return execute


def _inventory_propose(identity: AgentIdentity, arguments: dict[str, Any], context: ToolCallContext) -> Any:
    data, logic, _forecast = _inventory_components()
    tables = data.load_tables()
    if not data.validate_tables(tables)["valid"]:
        raise ValueError("Synthetic inventory tables failed data-quality validation.")
    return logic.make_replenishment_draft(
        tables, identity, context.idempotency_key, arguments["sku"], arguments["location"],
        arguments.get("budget"),
    )


def _inventory_simulate(identity: AgentIdentity, arguments: dict[str, Any], context: ToolCallContext) -> Any:
    _data, logic, _forecast = _inventory_components()
    result = logic.ProposalStore().simulate(
        identity, arguments["proposal_id"], context.idempotency_key
    )
    return logic.json_safe(result)


TOOL_WORKERS: dict[str, Callable[..., Any]] = {}
TOOL_LABELS: dict[str, str] = {}


def _mark_evidence(value: Any, evidence_id: str) -> Any:
    if isinstance(value, list):
        return [_mark_evidence(item, evidence_id) for item in value]
    if isinstance(value, dict):
        marked = {key: _mark_evidence(item, evidence_id) for key, item in value.items()}
        marked.setdefault("tool_result_id", evidence_id)
        return marked
    return value


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()

    def register_read(
        name: str,
        description: str,
        schema: dict[str, Any],
        worker: Callable[..., Any],
        *,
        data_label: str = "SYNTHETIC",
        max_rows: int = 20,
    ) -> None:
        TOOL_WORKERS[name] = worker
        TOOL_LABELS[name] = data_label

        async def handler(
            identity: AgentIdentity,
            arguments: dict[str, Any],
            *,
            context: ToolCallContext,
        ) -> dict[str, Any]:
            started = time.perf_counter()
            if worker is _verify_sources:
                raw = await _verify_sources(identity, arguments, context=context)
            else:
                raw = await asyncio.to_thread(worker, identity, arguments)
            elapsed_ms = (time.perf_counter() - started) * 1000
            EVIDENCE.record(context.run_id, context.call_id,
                            EvidenceEntry(name, arguments, raw, elapsed_ms))
            return {
                "tool_result_id": context.call_id,
                "tool": name,
                "data": _mark_evidence(raw, context.call_id),
                "data_label": data_label,
                "elapsed_ms": round(elapsed_ms, 3),
            }

        registry.register(ToolSpec(
            name=name,
            description=description,
            input_schema=schema,
            output_schema={"type": "object"},
            module=__name__,
            allowed_roles=ANALYST_ROLES,
            side_effect="read",
            timeout_seconds=READ_TOOL_TIMEOUT_SECONDS,
            max_rows=max_rows,
            max_bytes=150_000,
        ), handler, module=__name__)

    register_read("bi.revenue_trend", "Read synthetic BI revenue by month or week.", _schema({
        "grain": {"type": "string", "enum": ["month", "week"]},
        "date_range": DATE_RANGE_SCHEMA,
    }, ["grain", "date_range"]), _bi_worker("revenue_trend"))
    for tool_name, column_label in (("bi.top_categories", "categories"), ("bi.top_products", "products")):
        register_read(tool_name, f"Rank synthetic {column_label} by revenue or units.", _schema({
            "metric": {"type": "string", "enum": ["revenue", "units"]},
            "n": {"type": "integer", "minimum": 1, "maximum": 20},
            "date_range": DATE_RANGE_SCHEMA,
        }, ["metric", "n", "date_range"]), _bi_worker(tool_name.removeprefix("bi.")))
    register_read("bi.refund_rate", "Read synthetic refund rates by product, category, or region.", _schema({
        "by": {"type": "string", "enum": ["product", "category", "region"]},
    }, ["by"]), _bi_worker("refund_rate"))
    register_read("bi.anomaly_check", "Inspect unusual synthetic monthly revenue, units, or refund rates.", _schema({
        "metric": {"type": "string", "enum": ["revenue", "units", "refund_rate"]},
        "window": {"type": "integer", "minimum": 3, "maximum": 12},
        "z_threshold": {"type": "number", "minimum": 0.5, "maximum": 5},
    }, ["metric", "window", "z_threshold"]), _bi_worker("anomaly_check"))
    register_read("bi.region_breakdown", "Read synthetic revenue totals by region.", _schema({
        "date_range": DATE_RANGE_SCHEMA,
    }, ["date_range"]), _bi_worker("region_breakdown"))
    register_read("knowledge.search", "Search approved documents using the caller's access groups.", _schema({
        "question": {"type": "string", "minLength": 3, "maxLength": 500},
        "limit": {"type": "integer", "minimum": 1, "maximum": 5},
    }, ["question", "limit"]), _knowledge_search, data_label="ACCESS_FILTERED", max_rows=5)
    register_read("sales_forecast.score_demo", "Score a fixed synthetic sales opportunity for review.", _schema({
        "demo_id": {"type": "string", "enum": list(DEMO_OPPORTUNITIES)},
    }, ["demo_id"]), _sales_score)
    register_read("churn.score_demo", "Score a fixed synthetic customer snapshot for analyst review.", _schema({
        "demo_id": {"type": "string", "enum": list(DEMO_CUSTOMERS)},
    }, ["demo_id"]), _churn_score)
    register_read("demand.forecast_demo", "Read a synthetic demand baseline for an allowlisted SKU.", _schema({
        "sku": {"type": "string", "enum": list(DEMO_SKUS)},
        "horizon": {"type": "integer", "minimum": 1, "maximum": 8},
    }, ["sku", "horizon"]), _demand_forecast, max_rows=8)
    register_read("copilot.profile", "Read the caller's confirmed schema without sensitive fields or sample rows.",
                  _schema({}, []), _copilot_profile, data_label="USER_SCOPED", max_rows=100)
    register_read("copilot.query", "Run verified, parameterized analysis against the caller's confirmed dataset.",
                  _schema({"question": {"type": "string", "minLength": 4, "maxLength": 1000}}, ["question"]),
                  _copilot_query, data_label="USER_SCOPED", max_rows=100)
    sku_schema = {"type": "string", "pattern": r"^SKU-\d{3}$"}
    location_schema = {"type": "string", "pattern": r"^LOC-\d{3}$"}
    register_read("inventory.risk_ranking", "Rank synthetic inventory positions by projected stock risk.",
                  _schema({"horizon_weeks": {"type": "integer", "minimum": 1, "maximum": 26},
                           "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                          ["horizon_weeks", "limit"]),
                  _inventory_read("inventory.risk_ranking"), max_rows=20)
    register_read("inventory.position", "Read sellable stock, inbound, backorders, supplier and cover for a synthetic SKU/location.",
                  _schema({"sku": sku_schema, "location": location_schema}, ["sku", "location"]),
                  _inventory_read("inventory.position"), max_rows=1)
    register_read("inventory.forecast", "Read an empirical-residual demand forecast for a synthetic SKU/location.",
                  _schema({"sku": sku_schema, "location": location_schema,
                           "horizon_weeks": {"type": "integer", "minimum": 1, "maximum": 8}},
                          ["sku", "location", "horizon_weeks"]),
                  _inventory_read("inventory.forecast"), max_rows=8)
    register_read("inventory.simulate_scenario", "Compare fixed-seed synthetic inventory policies under disruption scenarios.",
                  _schema({"sku": sku_schema, "location": location_schema,
                           "replications": {"type": "integer", "minimum": 20, "maximum": 500},
                           "seed": {"type": "integer", "const": 20261101}},
                          ["sku", "location", "replications", "seed"]),
                  _inventory_read("inventory.simulate_scenario"), max_rows=6)
    register_read("inventory.transfer_options", "Read feasible synthetic transfers bounded by surplus, shortage, route time and cost.",
                  _schema({"sku": {"type": "string", "pattern": r"^SKU-\d{3}$"},
                           "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                          ["sku", "limit"]),
                  _inventory_read("inventory.transfer_options"), max_rows=20)

    def register_draft(name: str, description: str, schema: dict[str, Any], worker: Callable[..., Any]) -> None:
        TOOL_WORKERS[name] = worker
        TOOL_LABELS[name] = "SYNTHETIC"

        async def handler(identity: AgentIdentity, arguments: dict[str, Any], *,
                          context: ToolCallContext) -> dict[str, Any]:
            started = time.perf_counter()
            raw = await asyncio.to_thread(worker, identity, arguments, context)
            elapsed_ms = (time.perf_counter() - started) * 1000
            EVIDENCE.record(context.run_id, context.call_id,
                            EvidenceEntry(name, arguments, raw, elapsed_ms))
            return {"tool_result_id": context.call_id, "tool": name,
                    "data": _mark_evidence(raw, context.call_id), "data_label": "SYNTHETIC",
                    "elapsed_ms": round(elapsed_ms, 3)}

        registry.register(ToolSpec(
            name=name, description=description, input_schema=schema,
            output_schema={"type": "object"}, module=__name__, allowed_roles=ANALYST_ROLES,
            side_effect="draft", requires_approval=True, timeout_seconds=READ_TOOL_TIMEOUT_SECONDS,
            max_rows=20, max_bytes=150_000,
        ), handler, module=__name__)

    register_draft("inventory.propose_replenishment",
                    "Create a local replenishment draft only after persisted human approval.",
                    _schema({"sku": sku_schema, "location": location_schema,
                             "budget": {"type": "number", "minimum": 0}}, ["sku", "location"]),
                    _inventory_propose)
    register_draft("inventory.simulate_execution",
                    "Record an isolated simulated execution only after persisted human approval; never place an order.",
                    _schema({"proposal_id": {"type": "string", "pattern":
                                              r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-"
                                              r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"}},
                            ["proposal_id"]), _inventory_simulate)
    register_read("hub.verify_results", "Independently check evidence returned by the planned tools.", _schema({
        "source_call_ids": {"type": "array", "items": {"type": "string", "minLength": 1},
                            "minItems": 1, "maxItems": MAX_ANALYSIS_STEPS, "uniqueItems": True},
    }, ["source_call_ids"]), _verify_sources, max_rows=MAX_ANALYSIS_STEPS)
    return registry


def _json_equal(left: Any, right: Any) -> bool:
    try:
        return json.dumps(left, sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(
            right, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError):
        return False


async def _verify_sources(
    identity: AgentIdentity,
    arguments: dict[str, Any],
    *,
    context: ToolCallContext,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for call_id in arguments["source_call_ids"]:
        entry = EVIDENCE.get(context.run_id, call_id)
        if entry is None:
            checks.append({"tool_result_id": call_id, "verified": False, "reason": "evidence_missing"})
            continue
        try:
            if entry.tool_name.startswith("bi."):
                bi = _bi_data_tools()
                expected = await asyncio.to_thread(
                    bi.reference_rows, entry.tool_name.removeprefix("bi."), entry.arguments
                )
                verified = bi.results_match(entry.raw, expected)
            elif entry.tool_name == "knowledge.search":
                verified = isinstance(entry.raw, dict) and (
                    entry.raw.get("abstained") is True
                    or isinstance(entry.raw.get("citations"), list)
                )
            elif entry.tool_name == "copilot.query":
                worker = TOOL_WORKERS[entry.tool_name]
                expected = await asyncio.to_thread(worker, identity, entry.arguments)
                verified = (
                    isinstance(entry.raw, dict) and entry.raw.get("verified") is True
                    and isinstance(expected, dict) and expected.get("verified") is True
                    and _json_equal(entry.raw.get("rows"), expected.get("rows"))
                )
            elif entry.tool_name == "inventory.propose_replenishment":
                _data, inventory, _forecast = _inventory_components()
                expected = await asyncio.to_thread(
                    inventory.ProposalStore().get, identity, str(entry.raw.get("proposal_id", ""))
                ) if isinstance(entry.raw, dict) else None
                verified = isinstance(expected, dict) and _json_equal(entry.raw, expected)
            elif entry.tool_name == "inventory.simulate_execution":
                _data, inventory, _forecast = _inventory_components()
                proposal_id = str(entry.raw.get("proposal_id", "")) if isinstance(entry.raw, dict) else ""
                expected_proposal = await asyncio.to_thread(
                    inventory.ProposalStore().get, identity, proposal_id
                ) if proposal_id else None
                expected = expected_proposal.get("simulation") if isinstance(expected_proposal, dict) else None
                verified = isinstance(expected, dict) and _json_equal(entry.raw, expected)
            else:
                worker = TOOL_WORKERS[entry.tool_name]
                expected = await asyncio.to_thread(worker, identity, entry.arguments)
                verified = _json_equal(entry.raw, expected)
        except Exception:
            verified = False
        checks.append({"tool_result_id": call_id, "verified": verified,
                       "tamper_detected": not verified})
    return {"verified": bool(checks) and all(item["verified"] for item in checks), "checks": checks}


REGISTRY = build_registry()
POLICY = PolicyEngine()
EXECUTOR = BoundedExecutor(REGISTRY, POLICY, TRACE_STORE)
TOOL_NAMES = tuple(tool.spec.name for tool in REGISTRY)


def _preflight(question: str) -> str:
    text = question.strip().casefold()
    if not 4 <= len(question.strip()) <= MAX_QUESTION_LENGTH:
        raise UnsupportedRequest("Question must be between 4 and 1000 characters.")
    if any(fragment in text for fragment in (
        "ignore previous", "ignore the above", "ignore all rules", "disregard previous",
        "disregard all", "system prompt", "developer message", "reveal your prompt",
        "bypass policy", "override policy", "jailbreak", "act as an unrestricted", "delete ",
        "drop table", "insert into", "update ", "write to", "send email", "purchase order",
        "raw sql", "select *", "--", ";",
    )):
        raise UnsupportedRequest("This Hub only accepts bounded read-only analysis requests.")
    dataset_scope = (
        bool(re.search(r"\b(uploaded|dataset|spreadsheet|worksheet|csv|xlsx)\b", text))
        or "my data" in text or "this data" in text
    )
    if re.search(r"\b(margin|profit|payroll|salary|weather)\b", text) and not dataset_scope:
        raise UnsupportedRequest("That data or action is not available in the Hub catalogue.")
    return text


def deterministic_plan(question: str) -> AgentPlan:
    text = _preflight(question)
    clauses = [part.strip(" ,.?\n\t") for part in re.split(r"\b(?:and then|and also|and|also|plus)\b", text)]
    calls: list[ToolCall] = []
    for clause in clauses:
        if len(clause) < 3:
            continue
        tokens = set(re.findall(r"[a-z0-9-]+", clause))
        copilot_domain = (
            bool(tokens.intersection({"uploaded", "upload", "dataset", "spreadsheet", "worksheet", "csv", "xlsx"}))
            or "my data" in clause or "this data" in clause or "this dataset" in clause
        )
        if copilot_domain:
            if tokens.intersection({"profile", "schema", "columns"}):
                calls.append(ToolCall(tool_name="copilot.profile", arguments={}))
            else:
                calls.append(ToolCall(tool_name="copilot.query", arguments={"question": clause[:1000]}))
            continue
        inventory_domain = (
            bool(tokens.intersection({"inventory", "stock", "stockout", "replenishment", "supplier",
                                      "transfer", "sku", "skus"}))
            or bool(re.search(r"\bskus?\s+(?:are\s+)?at\s+risk\b", clause))
        )
        if inventory_domain:
            sku_match = re.search(r"\bSKU-\d{3}\b", clause, re.IGNORECASE)
            location_match = re.search(r"\bLOC-\d{3}\b", clause, re.IGNORECASE)
            sku = sku_match.group(0).upper() if sku_match else "SKU-001"
            location = location_match.group(0).upper() if location_match else "LOC-001"
            horizon_match = re.search(r"\b(\d{1,2})\s+weeks?\b", clause)
            horizon = min(int(horizon_match.group(1)), 8) if horizon_match else 6
            proposal_match = re.search(
                r"\bproposal\s+([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\b",
                clause, re.IGNORECASE,
            )
            if "simulate" in tokens and "execution" in tokens and proposal_match:
                calls.append(ToolCall(tool_name="inventory.simulate_execution", arguments={
                    "proposal_id": proposal_match.group(1),
                }))
            elif tokens.intersection({"draft", "propose", "replenishment"}) and "scenario" not in tokens:
                arguments: dict[str, Any] = {"sku": sku, "location": location}
                budget_match = re.search(r"\bbudget\s+(\d+(?:\.\d{1,2})?)\b", clause)
                if budget_match:
                    arguments["budget"] = float(budget_match.group(1))
                calls.append(ToolCall(tool_name="inventory.propose_replenishment", arguments=arguments))
            elif tokens.intersection({"scenario", "scenarios", "spike", "delay", "delayed"}):
                calls.append(ToolCall(tool_name="inventory.simulate_scenario", arguments={
                    "sku": sku, "location": location, "replications": 200, "seed": 20261101,
                }))
            elif "transfer" in tokens:
                calls.append(ToolCall(tool_name="inventory.transfer_options", arguments={
                    "sku": sku, "limit": 20,
                }))
            elif tokens.intersection({"risk", "risky", "stockout", "shortage", "cover", "weeks"}) or "at risk" in clause:
                calls.extend((
                    ToolCall(tool_name="inventory.risk_ranking", arguments={
                        "horizon_weeks": horizon, "limit": 20,
                    }),
                    ToolCall(tool_name="inventory.position", arguments={"sku": sku, "location": location}),
                    ToolCall(tool_name="inventory.forecast", arguments={
                        "sku": sku, "location": location, "horizon_weeks": horizon,
                    }),
                ))
            else:
                calls.append(ToolCall(tool_name="inventory.position", arguments={"sku": sku, "location": location}))
            continue
        sales_domain = bool(tokens.intersection({"opportunity", "pipeline", "win", "crm"}))
        demand_domain = bool(tokens.intersection({"forecast", "demand"})) and not sales_domain
        churn_domain = bool(tokens.intersection({"churn", "retention"})) or "account health" in clause
        knowledge_domain = bool(tokens.intersection({"policy", "document", "guidance", "procedure", "knowledge"}))
        bi_domain = bool(tokens.intersection({
            "revenue", "product", "products", "category", "categories", "refund", "region", "regions",
            "regional", "refunds", "anomaly", "anomalies", "units", "quantity", "monthly", "weekly",
        })) or ("sales" in tokens and not sales_domain)

        if bi_domain:
            bi = _module("tools.multi-agent-business-intelligence.app.agent")
            try:
                selected = bi.route_question(clause)
            except bi.AmbiguousQuestion as exc:
                raise ClarificationNeeded(str(exc)) from exc
            except bi.UnsupportedQuestion:
                raise
            calls.append(ToolCall(tool_name=f"bi.{selected.tool_name}", arguments=selected.arguments))
        if knowledge_domain:
            query = clause if len(clause) >= 3 else question
            calls.append(ToolCall(tool_name="knowledge.search", arguments={"question": query[:500], "limit": 5}))
        if demand_domain:
            sku_match = re.search(r"\bSKU-\d{3}\b", clause, re.IGNORECASE)
            if not sku_match:
                raise ClarificationNeeded("Which synthetic SKU should I forecast (for example SKU-001)?")
            horizon_match = re.search(r"\b(\d{1,2})\s+weeks?\b", clause)
            horizon = int(horizon_match.group(1)) if horizon_match else 8
            if not 1 <= horizon <= 8:
                raise UnsupportedRequest("Demo demand forecasts are limited to one through eight weeks.")
            calls.append(ToolCall(tool_name="demand.forecast_demo", arguments={
                "sku": sku_match.group(0).upper(), "horizon": horizon,
            }))
        if churn_domain:
            customer_match = re.search(r"\bSYN-\d{4}\b", clause, re.IGNORECASE)
            customer_id = customer_match.group(0).upper() if customer_match else "SYN-1042"
            if customer_id not in DEMO_CUSTOMERS:
                raise UnsupportedRequest("Choose one of the synthetic customer IDs listed in the tool catalogue.")
            calls.append(ToolCall(tool_name="churn.score_demo", arguments={"demo_id": customer_id}))
        if sales_domain:
            opportunity_match = re.search(r"\bSYN-OPP-\d{3}\b", clause, re.IGNORECASE)
            opportunity_id = opportunity_match.group(0).upper() if opportunity_match else "SYN-OPP-204"
            if opportunity_id not in DEMO_OPPORTUNITIES:
                raise UnsupportedRequest("Choose one of the synthetic opportunity IDs listed in the tool catalogue.")
            calls.append(ToolCall(tool_name="sales_forecast.score_demo", arguments={"demo_id": opportunity_id}))

    if not calls:
        if tokens_intersect(text, {"analyze", "analysis", "help", "business", "something", "recommend"}):
            raise ClarificationNeeded("Which analysis should I run: BI, an approved document search, demand, churn, or sales?")
        raise UnsupportedRequest("No supported read-only tool matches this request.")
    if len(calls) > MAX_ANALYSIS_STEPS:
        raise UnsupportedRequest("A Hub plan can contain at most four analysis calls plus verification.")
    return AgentPlan(agent_name="Alpha Agent Hub", goal="Run bounded read-only project tools", steps=tuple(calls))


def tokens_intersect(text: str, values: set[str]) -> bool:
    return bool(set(re.findall(r"[a-z]+", text)).intersection(values))


class HubDeterministicPlanner:
    def plan(self, question: str) -> AgentPlan:
        return self.plan_with_mode(question).plan

    def plan_with_mode(self, question: str) -> PlanningResult:
        return PlanningResult(plan=deterministic_plan(question), mode="deterministic")


def _verified_plan(plan: AgentPlan) -> AgentPlan:
    calls = tuple(call for call in plan.steps if call.tool_name != "hub.verify_results")
    if not calls:
        raise UnsupportedRequest("No registered analysis tools were selected.")
    if len(calls) > MAX_ANALYSIS_STEPS:
        raise UnsupportedRequest("A Hub plan can contain at most four analysis calls plus verification.")
    verifier = ToolCall(tool_name="hub.verify_results",
                        arguments={"source_call_ids": [call.call_id for call in calls]})
    return AgentPlan(agent_name="Alpha Agent Hub", goal="Run and verify bounded project tools",
                     steps=(*calls, verifier))


def plan_hub(question: str) -> PlanningResult:
    _preflight(question)
    if re.search(r"\b(?:draft|propose|simulate execution)\b", question, re.IGNORECASE) and re.search(
        r"\b(?:inventory|replenishment|sku|stock)\b", question, re.IGNORECASE
    ):
        return PlanningResult(plan=_verified_plan(deterministic_plan(question)), mode="deterministic")
    fallback: PlannerWithMode = HubDeterministicPlanner()
    readonly = tuple(item.spec.name for item in REGISTRY
                     if item.spec.name != "hub.verify_results" and item.spec.side_effect == "read")
    planner = LLMPlanner(fallback, tool_names=readonly)
    planning = planner.plan_with_mode(question)
    return PlanningResult(plan=_verified_plan(planning.plan), mode=planning.mode)


def _step_elapsed(step: dict[str, Any]) -> float | None:
    started, finished = step.get("started_at"), step.get("finished_at")
    if not started or not finished:
        return None
    try:
        from datetime import datetime

        return round(max(0.0, (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds() * 1000), 3)
    except (TypeError, ValueError):
        return None


def run_hub_agent(
    question: str,
    identity: AgentIdentity,
    *,
    trace: TraceStore | None = None,
    executor: BoundedExecutor | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    selected_trace = trace or TRACE_STORE
    selected_executor = executor or EXECUTOR
    planning = plan_hub(question)
    outcome = asyncio.run(selected_executor.run(
        planning.plan, identity, idempotency_key=idempotency_key or str(uuid4())
    ))
    steps = selected_trace.list_steps_for(outcome.run_id, identity)
    results = [cast(dict[str, Any], item) for item in outcome.results if isinstance(item, dict)]
    source_results = [item for item in results if item.get("tool_result_id")
                      and item.get("tool") != "hub.verify_results"]
    verifier = next((item for item in results if item.get("tool") == "hub.verify_results"), None)
    verifier_data = verifier.get("data", {}) if verifier else {}
    checks = verifier_data.get("checks", []) if isinstance(verifier_data, dict) else []
    verified_ids = {str(check["tool_result_id"]) for check in checks if check.get("verified")}
    evidence_ids = [str(item["tool_result_id"]) for item in source_results]
    all_verified = bool(source_results) and set(evidence_ids).issubset(verified_ids)
    data = source_results if all_verified else []
    findings = [{
        "text": f"{item['tool']} completed with independently checked evidence."
        if str(item["tool_result_id"]) in verified_ids else f"{item['tool']} evidence was withheld after verification failed.",
        "evidence_ids": [str(item["tool_result_id"])] if str(item["tool_result_id"]) in verified_ids else [],
        "data_label": item.get("data_label", "UNKNOWN"),
    } for item in source_results]
    trace_steps = [{
        "step_index": step["step_index"], "tool": step["tool_name"], "state": step["state"],
        "arguments": step["arguments"], "error_code": step["error_code"],
        "elapsed_ms": next((item.get("elapsed_ms") for item in source_results
                             if item.get("tool_result_id") == step["call_id"]), None) or _step_elapsed(step),
        "evidence_id": step["call_id"] if step["call_id"] in evidence_ids else None,
    } for step in steps]
    if outcome.state != TraceState.WAITING_APPROVAL.value:
        EVIDENCE.drop(outcome.run_id)
    safe = outcome.state == TraceState.COMPLETED.value and all_verified
    return {
        "answer": "The requested read-only analysis completed and passed evidence checks."
        if safe else "The run did not pass all evidence checks; numeric results were withheld.",
        "findings": findings,
        "data": data if safe else [],
        "evidence_ids": evidence_ids if safe else [],
        "limitations": ["Synthetic BI/model outputs are demonstrations, not business advice.",
                        "Knowledge results are limited to documents allowed by the signed-in user's groups."],
        "trace": {"run_id": outcome.run_id, "steps": trace_steps,
                  "timings": [{"step_index": step["step_index"], "tool": step["tool"],
                               "elapsed_ms": step["elapsed_ms"]} for step in trace_steps],
                  "correlation_id": outcome.correlation_id, "error_code": outcome.error_code},
        "mode": planning.mode,
        "data_label": "SYNTHETIC DEMOS; ACCESS-FILTERED DOCUMENTS",
        "status": "complete" if safe else outcome.state,
    }


@router.get("/csrf")
def get_csrf_token(user: dict[str, Any] = Depends(authenticated_user)) -> dict[str, str]:
    return {"csrf_token": _knowledge_module()._session_codec().issue_csrf(str(user["id"]))}


@router.get("/tools")
def get_tool_catalogue(user: dict[str, Any] = Depends(authenticated_user)) -> dict[str, Any]:
    identity = agent_identity(user)
    entries = []
    for registered in REGISTRY:
        spec = registered.spec
        if not identity.active or not identity.roles.intersection(spec.allowed_roles):
            continue
        if spec.allowed_workspaces is not None and identity.workspace_id not in spec.allowed_workspaces:
            continue
        entries.append({
            "name": spec.name,
            "description": spec.description,
            "side_effect": spec.side_effect,
            "requires_approval": spec.requires_approval,
            "input_schema": spec.input_schema,
            "output_schema": spec.output_schema,
            "data_label": TOOL_LABELS.get(spec.name, "INTERNAL"),
        })
    mode_default = "local_llm_available" if os.getenv("LLM_PROVIDER", "none").casefold() == "ollama" else "deterministic"
    return {"tools": entries, "mode_default": mode_default, "max_steps": 5}


@router.post("/preview")
def preview_plan(payload: HubAsk, _user: dict[str, Any] = Depends(csrf_user)) -> dict[str, Any]:
    try:
        planning = plan_hub(payload.question)
    except ClarificationNeeded as exc:
        return {"status": "needs_clarification", "question": str(exc), "mode": "deterministic", "steps": []}
    except UnsupportedRequest as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"status": "ready", "mode": planning.mode,
            "steps": [{"tool": call.tool_name, "arguments": call.arguments} for call in planning.plan.steps]}


@router.post("/ask")
def ask_hub(
    payload: HubAsk,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128, alias="Idempotency-Key")],
    user: dict[str, Any] = Depends(csrf_user),
) -> dict[str, Any]:
    try:
        return run_hub_agent(payload.question, agent_identity(user), idempotency_key=idempotency_key)
    except ClarificationNeeded as exc:
        return {"answer": str(exc), "findings": [], "data": [], "evidence_ids": [],
                "limitations": [], "trace": {"run_id": None, "steps": [], "timings": []},
                "mode": "deterministic", "status": "needs_clarification",
                "data_label": "SYNTHETIC DEMOS; ACCESS-FILTERED DOCUMENTS"}
    except UnsupportedRequest as exc:
        raise HTTPException(422, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, "A synthetic demo dataset or model is unavailable; run Alpha bootstrap.") from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, "Agent Hub run failed safely.") from exc


@router.get("/runs")
def list_runs(
    limit: int = Query(default=50, ge=1, le=100),
    user: dict[str, Any] = Depends(authenticated_user),
) -> dict[str, Any]:
    return {"runs": TRACE_STORE.list_runs_for(agent_identity(user), limit=limit)}


@router.get("/runs/{run_id}")
def get_run(run_id: str, user: dict[str, Any] = Depends(authenticated_user)) -> dict[str, Any]:
    identity = agent_identity(user)
    try:
        run = TRACE_STORE.get_run_for(run_id, identity)
        if run is None:
            raise HTTPException(404, "Run not found.")
        steps = TRACE_STORE.list_steps_for(run_id, identity)
        verification_passed = any(
            step["tool_name"] == "hub.verify_results"
            and step["state"] == TraceState.COMPLETED.value
            and isinstance(step.get("result"), dict)
            and isinstance(step["result"].get("data"), dict)
            and step["result"]["data"].get("verified") is True
            for step in steps
        )
        if not verification_passed:
            for step in steps:
                if step["tool_name"] != "hub.verify_results" and step.get("result") is not None:
                    step["result"] = {"withheld": "verification_failed"}
        return {"run": run, "steps": steps}
    except PermissionError as exc:
        raise HTTPException(404, "Run not found.") from exc


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, user: dict[str, Any] = Depends(csrf_user)) -> dict[str, Any]:
    try:
        if TRACE_STORE.get_run_for(run_id, agent_identity(user)) is None:
            raise HTTPException(404, "Run not found.")
        EXECUTOR.cancel(run_id, agent_identity(user))
    except (PermissionError, KeyError) as exc:
        raise HTTPException(404, "Run not found.") from exc
    return {"run_id": run_id, "status": "cancel_requested"}


@router.get("/approvals")
def list_approvals(
    status: str = Query(default="pending", pattern="^(pending|approved|rejected|expired)$"),
    user: dict[str, Any] = Depends(authenticated_user),
) -> dict[str, Any]:
    identity = agent_identity(user)
    approvals = TRACE_STORE.approvals.list_for(identity, status=status, limit=100)
    return {"approvals": approvals}


@router.post("/approvals/{approval_id}/approve")
def approve(
    approval_id: str,
    payload: ApprovalDecision,
    user: dict[str, Any] = Depends(csrf_user),
) -> dict[str, Any]:
    try:
        record = EXECUTOR.approve(approval_id, agent_identity(user), reason=payload.reason)
    except PermissionError as exc:
        raise HTTPException(403, "This approval cannot be approved by the current user.") from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(404, "Approval not found or no longer pending.") from exc
    try:
        requester = _resolve_workspace_user(str(record["requested_by"]), str(record["workspace_id"]))
        resumed = asyncio.run(EXECUTOR.run(None, requester, run_id=str(record["run_id"])))
    except PermissionError as exc:
        raise HTTPException(409, "The original requester is unavailable; the approved run was not resumed.") from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, "The approved run could not be resumed safely.") from exc
    if resumed.state != TraceState.WAITING_APPROVAL.value:
        EVIDENCE.drop(str(record["run_id"]))
    return {"approval": record, "run": {
        "run_id": resumed.run_id, "status": resumed.state, "error_code": resumed.error_code,
    }}


@router.post("/approvals/{approval_id}/reject")
def reject(
    approval_id: str,
    payload: ApprovalDecision,
    user: dict[str, Any] = Depends(csrf_user),
) -> dict[str, Any]:
    try:
        record = EXECUTOR.reject(approval_id, agent_identity(user), reason=payload.reason)
    except PermissionError as exc:
        raise HTTPException(403, "This approval cannot be rejected by the current user.") from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(404, "Approval not found or no longer pending.") from exc
    EVIDENCE.drop(str(record["run_id"]))
    return {"approval": record}

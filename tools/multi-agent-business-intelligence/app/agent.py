"""Tool registration, deterministic routing, and report composition for BI asks."""

from __future__ import annotations

import asyncio
import copy
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from alpha_core.agent import (
    AgentIdentity,
    AgentPlan,
    BoundedExecutor,
    DeterministicPlanner,
    LLMPlanner,
    PolicyEngine,
    ToolCall,
    ToolCallContext,
    ToolRegistry,
    ToolSpec,
    TraceStore,
)

from . import data_tools

DATE_RANGE_SCHEMA = {
    "type": "object",
    "required": ["start", "end"],
    "properties": {
        "start": {"type": "string", "pattern": r"^20\d\d-\d\d-\d\d$"},
        "end": {"type": "string", "pattern": r"^20\d\d-\d\d-\d\d$"},
    },
    "additionalProperties": False,
}
ANALYST_ROLES = frozenset({"employee", "admin"})
DATE_RANGE_DEFAULT = {"start": "2025-01-01", "end": "2025-12-31"}


class AmbiguousQuestion(ValueError):
    """The deterministic planner needs the user to clarify the requested analysis."""


class UnsupportedQuestion(ValueError):
    """The BI demo cannot safely answer the requested analysis."""


@dataclass
class CachedToolResult:
    tool_name: str
    arguments: dict[str, Any]
    rows: list[dict[str, Any]]
    elapsed_ms: float


class ResultCache:
    """Per-run evidence cache used only by the independent verifier."""

    def __init__(self) -> None:
        self.entries: dict[str, CachedToolResult] = {}

    def record(self, call_id: str, name: str, arguments: dict[str, Any],
               rows: list[dict[str, Any]], elapsed_ms: float) -> None:
        self.entries[call_id] = CachedToolResult(name, copy.deepcopy(arguments), copy.deepcopy(rows), elapsed_ms)

    def get(self, call_id: str) -> CachedToolResult | None:
        entry = self.entries.get(call_id)
        return copy.deepcopy(entry) if entry is not None else None


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}


def build_bi_registry(cache: ResultCache) -> ToolRegistry:
    registry = ToolRegistry()
    # Each wrapper fixes its tool name in trusted code; the plan cannot supply SQL or a callable.
    def register_query(name: str, description: str, input_schema: dict[str, Any]) -> None:
        async def handler(identity: AgentIdentity, arguments: dict[str, Any], *, context: ToolCallContext) -> dict[str, Any]:
            del identity
            started = time.perf_counter()
            rows = data_tools.execute_tool(name, arguments)
            elapsed_ms = (time.perf_counter() - started) * 1000
            cache.record(context.call_id, name, arguments, rows, elapsed_ms)
            return _evidence_payload(context.call_id, name, arguments, rows, elapsed_ms)

        registry.register(ToolSpec(
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema={"type": "object"},
            module=__name__,
            allowed_roles=ANALYST_ROLES,
            side_effect="read",
            timeout_seconds=5,
            max_rows=data_tools.MAX_ROWS,
            max_bytes=100_000,
        ), handler, module=__name__)

    register_query("revenue_trend", "Revenue by month or week over a bounded date range.", _schema({
        "grain": {"type": "string", "enum": ["month", "week"]},
        "date_range": DATE_RANGE_SCHEMA,
    }, ["grain", "date_range"]))
    register_query("top_categories", "Top synthetic product categories by revenue or units.", _schema({
        "metric": {"type": "string", "enum": ["revenue", "units"]},
        "n": {"type": "integer", "minimum": 1, "maximum": data_tools.MAX_ROWS},
        "date_range": DATE_RANGE_SCHEMA,
    }, ["metric", "n", "date_range"]))
    register_query("top_products", "Top synthetic products by revenue or units.", _schema({
        "metric": {"type": "string", "enum": ["revenue", "units"]},
        "n": {"type": "integer", "minimum": 1, "maximum": data_tools.MAX_ROWS},
        "date_range": DATE_RANGE_SCHEMA,
    }, ["metric", "n", "date_range"]))
    register_query("refund_rate", "Refund percentage grouped by product, category, or region.", _schema({
        "by": {"type": "string", "enum": ["product", "category", "region"]},
    }, ["by"]))
    register_query("anomaly_check", "Flag unusual monthly synthetic revenue, units, or refund-rate values.", _schema({
        "metric": {"type": "string", "enum": ["revenue", "units", "refund_rate"]},
        "window": {"type": "integer", "minimum": 3, "maximum": 12},
        "z_threshold": {"type": "number", "minimum": 0.5, "maximum": 5},
    }, ["metric", "window", "z_threshold"]))
    register_query("region_breakdown", "Synthetic gross/net revenue and order lines by region.", _schema({
        "date_range": DATE_RANGE_SCHEMA,
    }, ["date_range"]))

    async def verify_handler(identity: AgentIdentity, arguments: dict[str, Any], *, context: ToolCallContext) -> dict[str, Any]:
        del identity, context
        checks = []
        for call_id in arguments["source_call_ids"]:
            entry = cache.get(call_id)
            if entry is None:
                checks.append({"tool_result_id": call_id, "verified": False, "reason": "evidence_missing"})
                continue
            expected = data_tools.reference_rows(entry.tool_name, entry.arguments)
            matched = data_tools.results_match(entry.rows, expected)
            checks.append({
                "tool_result_id": call_id,
                "verified": matched,
                "expected_rows": len(expected),
                "actual_rows": len(entry.rows),
                "tamper_detected": not matched,
            })
        return {"verified": bool(checks) and all(item["verified"] for item in checks), "checks": checks}

    registry.register(ToolSpec(
        name="verify_totals",
        description="Independently recompute BI results from raw synthetic order rows.",
        input_schema=_schema({
            "source_call_ids": {"type": "array", "items": {"type": "string", "minLength": 1},
                                "minItems": 1, "maxItems": 4, "uniqueItems": True},
        }, ["source_call_ids"]),
        output_schema={"type": "object"},
        module=__name__,
        allowed_roles=ANALYST_ROLES,
        side_effect="read",
        timeout_seconds=5,
        max_rows=5,
        max_bytes=20_000,
    ), verify_handler, module=__name__)
    return registry


def _evidence_payload(call_id: str, name: str, arguments: dict[str, Any],
                      rows: list[dict[str, Any]], elapsed_ms: float) -> dict[str, Any]:
    return {
        "tool_result_id": call_id,
        "tool": name,
        "query": copy.deepcopy(arguments),
        "row_count": len(rows),
        "rows": [{**row, "tool_result_id": call_id} for row in rows],
        "elapsed_ms": round(elapsed_ms, 3),
        "data_label": "SYNTHETIC",
    }


def make_verified_plan(plan: AgentPlan) -> AgentPlan:
    calls = tuple(call for call in plan.steps if call.tool_name != "verify_totals")
    if not calls:
        raise UnsupportedQuestion("No supported read-only BI analysis was selected.")
    if len(calls) > 4:
        raise UnsupportedQuestion("A BI plan may contain at most four analysis calls plus verification.")
    verifier = ToolCall(
        tool_name="verify_totals",
        arguments={"source_call_ids": [call.call_id for call in calls]},
    )
    return AgentPlan(
        agent_name="BI Analyst Workflow",
        goal="Analyze and verify synthetic retail data",
        steps=(*calls, verifier),
    )


def route_question(question: str) -> ToolCall:
    if not 4 <= len(question.strip()) <= 500:
        raise UnsupportedQuestion("Question must be between 4 and 500 characters.")
    text = question.casefold()
    if any(token in text for token in ("ignore all rules", "ignore previous", "system prompt", "bypass policy",
                                        "delete all", "drop table", "update orders", "insert into", ";", "--")):
        raise UnsupportedQuestion("The request contains an instruction or query fragment this read-only demo rejects.")
    tokens = set(re.findall(r"[a-z]+", text))
    if tokens.intersection({"margin", "profit", "forecast", "weather", "payroll", "salary"}) or any(
        phrase in text for phrase in ("customer names", "personal data")
    ):
        raise UnsupportedQuestion("That metric or data is not available in the synthetic BI catalogue.")

    has_anomaly = bool(tokens.intersection({"anomaly", "anomalies", "unusual", "spike", "outlier"}))
    has_refund = "refund" in tokens or {"return", "rate"}.issubset(tokens)
    has_region = bool(tokens.intersection({"region", "regions", "regional"}))
    has_category = bool(tokens.intersection({"category", "categories"}))
    has_product = bool(tokens.intersection({"product", "products", "sku", "skus"}))
    if has_anomaly:
        selected = "anomaly_check"
    elif has_refund:
        selected = "refund_rate"
    elif has_category and has_product:
        raise AmbiguousQuestion("Should I rank product categories or individual products?")
    elif has_category:
        selected = "top_categories"
    elif has_product:
        selected = "top_products"
    elif has_region:
        if tokens.intersection({"month", "monthly", "week", "weekly", "trend"}):
            raise AmbiguousQuestion("The demo can show regional totals or a time trend; which view do you want?")
        selected = "region_breakdown"
    elif tokens.intersection({"month", "monthly", "weekly", "week", "trend", "revenue", "sales"}):
        selected = "revenue_trend"
    else:
        raise UnsupportedQuestion("I can analyze revenue trends, top categories/products, refund rates, anomalies, or regions.")

    date_range = _date_range_from_question(text)
    if selected == "anomaly_check":
        metric = "units" if "units" in tokens else "refund_rate" if "refund" in tokens else "revenue"
        window_match = re.search(r"\b(3|4|5|6|7|8|9|10|11|12)\s+months?\b", text)
        return ToolCall(tool_name="anomaly_check", arguments={
            "metric": metric,
            "window": int(window_match.group(1)) if window_match else 3,
            "z_threshold": 2.0,
        })
    if selected == "refund_rate":
        by = "product" if has_product else "region" if has_region else "category"
        return ToolCall(tool_name="refund_rate", arguments={"by": by})
    if selected == "region_breakdown":
        return ToolCall(tool_name="region_breakdown", arguments={"date_range": date_range})
    if selected in {"top_categories", "top_products"}:
        metric = "units" if tokens.intersection({"units", "quantity", "volume"}) else "revenue"
        limit_match = re.search(r"\btop\s+(\d+)\b", text)
        n = int(limit_match.group(1)) if limit_match else 5
        if not 1 <= n <= data_tools.MAX_ROWS:
            raise UnsupportedQuestion(f"The result limit must be between one and {data_tools.MAX_ROWS}.")
        return ToolCall(tool_name=selected, arguments={"metric": metric, "n": n, "date_range": date_range})
    grain = "week" if "week" in tokens or "weekly" in tokens else "month"
    return ToolCall(tool_name="revenue_trend", arguments={"grain": grain, "date_range": date_range})


def _date_range_from_question(text: str) -> dict[str, Any]:
    if "last six months" in text or "last 6 months" in text:
        return {"start": "2025-07-01", "end": "2025-12-31"}
    month = re.search(r"\b(2025)-(0[1-9]|1[0-2])\b", text)
    if month:
        year, number = month.group(1), month.group(2)
        last_day = {"01": 31, "02": 28, "03": 31, "04": 30, "05": 31, "06": 30,
                    "07": 31, "08": 31, "09": 30, "10": 31, "11": 30, "12": 31}[number]
        return {"start": f"{year}-{number}-01", "end": f"{year}-{number}-{last_day:02}"}
    return dict(DATE_RANGE_DEFAULT)


def run_bi_agent(
    question: str,
    identity: AgentIdentity,
    trace: TraceStore,
    *,
    planner: DeterministicPlanner | LLMPlanner | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    # Reject unsafe or unsupported asks before an optional planner sees the prompt.
    route_question(question)
    fallback = DeterministicPlanner(route_question, agent_name="BI Analyst Workflow")
    selected_planner = planner or LLMPlanner(
        fallback,
        tool_names=("revenue_trend", "top_categories", "top_products", "refund_rate",
                    "anomaly_check", "region_breakdown"),
    )
    planning = selected_planner.plan_with_mode(question)
    plan = make_verified_plan(planning.plan)
    cache = ResultCache()
    registry = build_bi_registry(cache)
    executor = BoundedExecutor(registry, PolicyEngine(), trace)
    outcome = asyncio.run(executor.run(plan, identity, idempotency_key=idempotency_key))
    steps = trace.list_steps_for(outcome.run_id, identity)
    analytics: list[dict[str, Any]] = []
    verifier: dict[str, Any] | None = None
    for result in outcome.results:
        if not isinstance(result, dict):
            continue
        result_dict = cast(dict[str, Any], result)
        if result_dict.get("tool_result_id"):
            analytics.append(result_dict)
        elif "checks" in result_dict:
            verifier = result_dict
    checks: list[dict[str, Any]] = verifier.get("checks", []) if verifier else []
    verified_ids = {str(item["tool_result_id"]) for item in checks if item.get("verified")}
    all_verified = bool(analytics) and len(verified_ids) == len(analytics)
    evidence_ids = [item["tool_result_id"] for item in analytics]
    data: list[dict[str, Any]] = []
    for item in analytics:
        evidence_id = item["tool_result_id"]
        if evidence_id not in verified_ids:
            continue
        data.extend(item["rows"])
    report_evidence_ids = evidence_ids if all_verified else []
    findings = [{
        "text": "The selected synthetic analysis passed independent result verification."
        if all_verified else "Independent verification did not pass; numeric findings were withheld.",
        "evidence_ids": report_evidence_ids,
    }]
    trace_steps = []
    for step in steps:
        cached_result = cache.entries.get(step["call_id"])
        elapsed_ms = cached_result.elapsed_ms if cached_result is not None else None
        if elapsed_ms is None and step.get("started_at") and step.get("finished_at"):
            try:
                started = datetime.fromisoformat(step["started_at"])
                finished = datetime.fromisoformat(step["finished_at"])
                elapsed_ms = max(0.0, (finished - started).total_seconds() * 1000)
            except (TypeError, ValueError):
                elapsed_ms = None
        trace_steps.append({
            "step_index": step["step_index"],
            "tool": step["tool_name"],
            "state": step["state"],
            "arguments": step["arguments"],
            "error_code": step["error_code"],
            "elapsed_ms": round(elapsed_ms, 3) if elapsed_ms is not None else None,
            "evidence_id": step["call_id"] if step["call_id"] in evidence_ids else None,
        })
    safe = outcome.state == "completed" and all_verified
    return {
        "answer": "The requested analysis passed independent verification over synthetic retail data."
        if safe else "The analysis could not be verified; no numeric findings are provided.",
        "findings": findings,
        "data": data if safe else [],
        "evidence_ids": evidence_ids if safe else [],
        "limitations": ["Synthetic retail data only.", "Read-only analysis; results are not business advice."],
        "trace": {"run_id": outcome.run_id, "steps": trace_steps,
                  "timings": [{"step_index": step["step_index"], "tool": step["tool"],
                               "elapsed_ms": step["elapsed_ms"]} for step in trace_steps],
                  "correlation_id": outcome.correlation_id, "error_code": outcome.error_code},
        "mode": planning.mode,
        "data_label": "SYNTHETIC",
        "status": "complete" if safe else "verification_failed" if outcome.state == "completed" else outcome.state,
    }

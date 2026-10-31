"""Bounded execution, independent verification, audit, and safe CSV export."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import threading
import time
from collections import OrderedDict
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

import duckdb
import pandas as pd

from alpha_core.agent import AgentIdentity

from .models import QueryPlan
from .planner import CopilotClarification, CopilotPlanner, CopilotUnsupported
from .query import MAX_QUERY_ROWS, MAX_RESULT_BYTES, compile_query, verify_with_pandas
from .storage import CopilotStore

QUERY_TIMEOUT_SECONDS = 5
EXPORT_TTL_SECONDS = 900
MAX_EXPORTS = 64


class VerificationFailed(RuntimeError):
    """The independent result path disagreed with DuckDB."""


class QueryTimedOut(TimeoutError):
    """DuckDB exceeded the configured wall clock query limit."""


class CopilotService:
    def __init__(self, store: CopilotStore, planner: CopilotPlanner | None = None) -> None:
        self.store = store
        self.planner = planner or CopilotPlanner()
        self._exports: OrderedDict[str, tuple[str, float, bytes]] = OrderedDict()
        self._lock = threading.RLock()

    def query(self, identity: AgentIdentity, question: str) -> dict[str, Any]:
        started = time.perf_counter()
        query_id = str(uuid4())
        question_hash = hashlib.sha256(question.encode("utf-8", errors="replace")).hexdigest()
        plan_json: dict[str, Any] = {}
        columns: list[dict[str, Any]] = []
        try:
            manifest = self.store.manifest(identity)
            columns = manifest["columns"]
            safe_profile = self.store.profile_for_hub(identity)
            plan, mode = self.planner.plan(
                question, columns, profile=safe_profile,
                allow_local_llm=os.getenv("COPILOT_LOCAL_PLANNER", "0") == "1",
            )
            plan_json = _audit_plan(plan, columns)
            self.planner.validate_plan(plan, columns)
            compiled = compile_query(plan, table_name=str(manifest["table_name"]), columns=columns)
            with self.store._workspace_lock(identity):
                latest_manifest = self.store.manifest(identity)
                if latest_manifest["source_sha256"] != manifest["source_sha256"]:
                    raise CopilotUnsupported("The dataset changed while preparing this question; retry it.")
                manifest = latest_manifest
                source = self.store.read_frame(identity, manifest)
                actual = self._execute(identity, compiled)
            verification = verify_with_pandas(source, plan, columns=columns, actual_rows=actual)
            if not verification["verified"]:
                raise VerificationFailed("The independent verifier rejected this result; no rows were released.")
            encoded = json.dumps(actual, default=_json_default, separators=(",", ":"), allow_nan=False).encode("utf-8")
            if len(encoded) > MAX_RESULT_BYTES:
                raise CopilotUnsupported("The result exceeds the 750 KB response limit; narrow the question.")
            safe_plan = _public_plan(plan, columns)
            elapsed_ms = (time.perf_counter() - started) * 1000
            self.store.audit(
                identity, question_hash=question_hash, status="verified", query_id=query_id,
                plan=plan_json, result_rows=len(actual), elapsed_ms=elapsed_ms,
            )
            response = {
                "query_id": query_id,
                "rows": actual,
                "chart": _chart_spec(actual, compiled.output_fields),
                "plan": safe_plan,
                "assumptions": list(plan.assumptions),
                "planner_mode": mode,
                "provenance": {
                    "dataset_sha256": manifest["source_sha256"], "query_id": query_id,
                    "source_row_count": int(manifest["row_count"]),
                    "source_rows_after_filters": int(verification["source_rows_after_filters"]),
                    "result_row_count": len(actual), "generated_at": _now(),
                    "duration_ms": round(elapsed_ms, 3),
                },
                "verified": True,
                "verification": verification,
                "data_label": manifest["data_label"],
            }
            self._remember_export(identity, query_id, actual, compiled.output_fields)
            return response
        except Exception as exc:
            status = "clarification" if isinstance(exc, CopilotClarification) else (
                "refused" if isinstance(exc, CopilotUnsupported) else "failed"
            )
            try:
                self.store.audit(
                    identity, question_hash=question_hash, status=status, query_id=query_id,
                    plan=plan_json, elapsed_ms=(time.perf_counter() - started) * 1000,
                )
            except Exception:
                pass
            raise

    def _execute(self, identity: AgentIdentity, compiled: Any) -> list[dict[str, Any]]:
        path = self.store._database_path(identity)
        connection = duckdb.connect(str(path), read_only=True, config={"threads": 2})
        fired = threading.Event()

        def interrupt() -> None:
            fired.set()
            try:
                connection.interrupt()
            except duckdb.Error:
                pass

        timer = threading.Timer(QUERY_TIMEOUT_SECONDS, interrupt)
        timer.daemon = True
        try:
            timer.start()
            cursor = connection.execute(compiled.sql, list(compiled.parameters))
            rows = cursor.fetchmany(MAX_QUERY_ROWS + 1)
            if fired.is_set():
                raise QueryTimedOut("The analytics query exceeded its five second time limit.")
            if len(rows) > MAX_QUERY_ROWS:
                raise CopilotUnsupported(f"Queries are limited to {MAX_QUERY_ROWS} result rows.")
            names = [str(item[0]) for item in cursor.description]
            return [
                {name: _json_value(value) for name, value in zip(names, row)}
                for row in rows
            ]
        except duckdb.Error as exc:
            if fired.is_set():
                raise QueryTimedOut("The analytics query exceeded its five second time limit.") from exc
            raise CopilotUnsupported("The analytics query could not be safely completed.") from exc
        finally:
            timer.cancel()
            connection.close()

    def export_csv(self, identity: AgentIdentity, query_id: str) -> bytes:
        with self._lock:
            self._expire_exports()
            entry = self._exports.get(query_id)
        if entry is None:
            raise LookupError("This verified export expired; run the question again.")
        scope, _expires_at, value = entry
        if scope != self.store._scope_key(identity):
            raise PermissionError("This verified export belongs to another user or workspace.")
        return value

    def _remember_export(
        self, identity: AgentIdentity, query_id: str, rows: list[dict[str, Any]], fields: tuple[str, ...],
    ) -> None:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(fields), extrasaction="ignore", lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fields})
        raw = output.getvalue().encode("utf-8-sig")
        if len(raw) > MAX_RESULT_BYTES:
            return
        with self._lock:
            self._expire_exports()
            self._exports[query_id] = (
                self.store._scope_key(identity), time.monotonic() + EXPORT_TTL_SECONDS, raw,
            )
            while len(self._exports) > MAX_EXPORTS:
                self._exports.popitem(last=False)

    def _expire_exports(self) -> None:
        now = time.monotonic()
        for key, (_, expiry, _) in list(self._exports.items()):
            if expiry <= now:
                self._exports.pop(key, None)


def _public_plan(plan: QueryPlan, columns: list[dict[str, Any]]) -> QueryPlan:
    result = plan.model_dump(mode="json")
    by_name = {str(column["name"]): column for column in columns}
    for index, measure in enumerate(plan.measures):
        column = by_name[measure.column]
        if column.get("sensitive"):
            result["measures"][index]["column"] = "[sensitive aggregate]"
    return QueryPlan.model_validate(result)


def _audit_plan(plan: QueryPlan, columns: list[dict[str, Any]]) -> dict[str, Any]:
    result = plan.model_dump(mode="json")
    by_name = {str(column["name"]): column for column in columns}
    for measure in result["measures"]:
        column = by_name.get(str(measure["column"]))
        if column is not None and column.get("sensitive"):
            measure["column"] = "[sensitive aggregate]"
    return result


def _chart_spec(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, Any]:
    dimensions = [field for field in fields if field.startswith("d_") or field.startswith("date_")]
    measures = [field for field in fields if field not in dimensions]
    return {
        "type": "table" if not dimensions or not rows else ("line" if dimensions[0].startswith("date_") else "bar"),
        "x": dimensions[0] if dimensions else None,
        "y": measures[0] if measures else None,
        "rows": min(len(rows), MAX_QUERY_ROWS),
    }


def _csv_value(value: Any) -> Any:
    if isinstance(value, str):
        first_visible = value.lstrip(" \t\r\n")[:1]
        if value.startswith(("\t", "\r", "\n")) or first_visible in {"=", "+", "-", "@"}:
            return "'" + value
    return value


def _json_value(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _json_default(value: Any) -> Any:
    cleaned = _json_value(value)
    if cleaned is value:
        raise TypeError(f"value of type {type(value).__name__} is not JSON serializable")
    return cleaned


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

"""SQLite run ledger with scoped reads, bounded redacted traces, and state guards."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import AgentIdentity, AgentPlan, TraceState

RUN_TRANSITIONS = {
    TraceState.REQUESTED: {TraceState.PLANNED, TraceState.FAILED, TraceState.CANCELLED},
    TraceState.PLANNED: {TraceState.VALIDATED, TraceState.FAILED, TraceState.CANCELLED},
    TraceState.VALIDATED: {TraceState.RUNNING, TraceState.WAITING_APPROVAL, TraceState.COMPLETED,
                            TraceState.FAILED, TraceState.CANCELLED},
    TraceState.RUNNING: {TraceState.WAITING_APPROVAL, TraceState.COMPLETED, TraceState.FAILED,
                         TraceState.CANCELLED},
    TraceState.WAITING_APPROVAL: {TraceState.RUNNING, TraceState.FAILED, TraceState.CANCELLED},
    TraceState.COMPLETED: set(),
    TraceState.FAILED: set(),
    TraceState.CANCELLED: set(),
}
STEP_TRANSITIONS = {
    TraceState.REQUESTED: {TraceState.PLANNED, TraceState.VALIDATED, TraceState.FAILED,
                           TraceState.CANCELLED},
    TraceState.PLANNED: {TraceState.VALIDATED, TraceState.FAILED, TraceState.CANCELLED},
    TraceState.VALIDATED: {TraceState.RUNNING, TraceState.WAITING_APPROVAL, TraceState.FAILED,
                           TraceState.CANCELLED},
    TraceState.WAITING_APPROVAL: {TraceState.VALIDATED, TraceState.RUNNING, TraceState.FAILED,
                                  TraceState.CANCELLED},
    TraceState.RUNNING: {TraceState.COMPLETED, TraceState.FAILED, TraceState.CANCELLED},
    TraceState.COMPLETED: set(),
    TraceState.FAILED: set(),
    TraceState.CANCELLED: set(),
}
_UNSET = object()
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class InvalidTransition(ValueError):
    """Raised when a trace attempts to skip or reverse a lifecycle state."""


class TraceAccessDenied(PermissionError):
    """Raised when a caller asks for a run outside their authorized scope."""


class TraceStore:
    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        retention_days: int | None = None,
        max_field_bytes: int = 16_384,
        max_run_bytes: int = 524_288,
        redact_email: bool = False,
        redact_keys: frozenset[str] | None = None,
    ) -> None:
        if retention_days is None:
            try:
                retention_days = int(os.getenv("RETENTION_DAYS", "30"))
            except ValueError as exc:
                raise ValueError("RETENTION_DAYS must be an integer") from exc
        if retention_days < 1 or max_field_bytes < 128 or max_run_bytes < max_field_bytes:
            raise ValueError("invalid trace retention or size limits")
        path_str = str(path)
        if path_str != ":memory:":
            Path(path_str).parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self.max_field_bytes = max_field_bytes
        self.max_run_bytes = max_run_bytes
        self.redact_keys = frozenset(
            key.casefold() for key in (redact_keys or frozenset({
                "password", "token", "secret", "api_key", "authorization", "cookie"
            }))
        ) | (frozenset({"email"}) if redact_email else frozenset())
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path_str, check_same_thread=False, timeout=30)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA busy_timeout=30000")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS agent_runs (
              run_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              workspace_id TEXT NOT NULL,
              request_key TEXT,
              plan_hash TEXT NOT NULL,
              plan_json TEXT NOT NULL,
              goal TEXT NOT NULL,
              state TEXT NOT NULL,
              error_code TEXT,
              correlation_id TEXT NOT NULL,
              trace_bytes INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_agent_runs_scope ON agent_runs(workspace_id,user_id,created_at);
            CREATE TABLE IF NOT EXISTS agent_steps (
              run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
              step_index INTEGER NOT NULL,
              call_id TEXT NOT NULL,
              tool_name TEXT NOT NULL,
              arguments_json TEXT NOT NULL,
              result_json TEXT,
              state TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              error_code TEXT,
              correlation_id TEXT NOT NULL,
              idempotency_key TEXT NOT NULL,
              started_at TEXT,
              finished_at TEXT,
              PRIMARY KEY (run_id, step_index),
              UNIQUE (run_id, call_id),
              UNIQUE (run_id, idempotency_key)
            );
        """)
        self._migrate_existing_tables()
        for row in self._db.execute(
            "SELECT s.run_id,s.call_id,r.plan_hash FROM agent_steps s "
            "JOIN agent_runs r ON r.run_id=s.run_id WHERE s.idempotency_key=''"
        ).fetchall():
            self._db.execute(
                "UPDATE agent_steps SET idempotency_key=? WHERE run_id=? AND call_id=?",
                (_idempotency_key(row["run_id"], row["call_id"], row["plan_hash"]),
                 row["run_id"], row["call_id"]),
            )
        self._db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_steps_idempotency "
            "ON agent_steps(run_id,idempotency_key)"
        )
        self._db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_runs_request_key "
            "ON agent_runs(workspace_id,user_id,request_key) WHERE request_key IS NOT NULL"
        )
        self._db.commit()
        from .approvals import ApprovalStore

        self.approvals = ApprovalStore(self)

    def _migrate_existing_tables(self) -> None:
        """Add safe metadata columns for a database created by the first runtime draft."""
        run_columns = {row["name"] for row in self._db.execute("PRAGMA table_info(agent_runs)")}
        for name, sql_type, default in (
            ("request_key", "TEXT", "NULL"),
            ("plan_json", "TEXT", "''"),
            ("correlation_id", "TEXT", "''"),
            ("trace_bytes", "INTEGER", "0"),
            ("created_at", "TEXT", "''"),
            ("updated_at", "TEXT", "''"),
        ):
            if name not in run_columns:
                nullable = name == "request_key"
                required = "" if nullable else " NOT NULL"
                self._db.execute(
                    f"ALTER TABLE agent_runs ADD COLUMN {name} {sql_type}{required} DEFAULT {default}"
                )
        step_columns = {row["name"] for row in self._db.execute("PRAGMA table_info(agent_steps)")}
        for name, sql_type, default in (
            ("correlation_id", "TEXT", "''"),
            ("idempotency_key", "TEXT", "''"),
        ):
            if name not in step_columns:
                self._db.execute(f"ALTER TABLE agent_steps ADD COLUMN {name} {sql_type} NOT NULL DEFAULT {default}")

    def create_run(
        self,
        run_id: str,
        identity: AgentIdentity,
        plan: AgentPlan,
        plan_hash: str,
        plan_json: str,
        *,
        request_key: str | None = None,
        correlation_id: str | None = None,
    ) -> str:
        correlation_id = correlation_id or str(uuid4())
        now = _now()
        if any(_contains_redacted_key(call.arguments, self.redact_keys) for call in plan.steps):
            raise ValueError("plan arguments contain a field excluded from persisted traces")
        plan_bytes = len(plan_json.encode("utf-8"))
        if plan_bytes > self.max_run_bytes:
            raise ValueError("canonical plan exceeds the configured per-run trace limit")
        stored_arguments = [_trace_json(call.arguments, self.redact_keys, self.max_field_bytes)
                            for call in plan.steps]
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO agent_runs(run_id,user_id,workspace_id,request_key,plan_hash,plan_json,goal,state,"
                "correlation_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, identity.user_id, identity.workspace_id, request_key, plan_hash, plan_json,
                 plan.goal, TraceState.REQUESTED.value, correlation_id, now, now),
            )
            total_bytes = plan_bytes
            for index, (call, arguments_json) in enumerate(zip(plan.steps, stored_arguments)):
                size = len(arguments_json.encode("utf-8"))
                remaining_fields = len(stored_arguments) - index - 1
                available = self.max_run_bytes - total_bytes - remaining_fields
                if size > available:
                    marker = _json({"_truncated": "run_size_limit"})
                    arguments_json = marker if len(marker.encode("utf-8")) <= available else "0"
                    size = len(arguments_json.encode("utf-8"))
                total_bytes += size
                idem = _idempotency_key(run_id, call.call_id, plan_hash)
                self._db.execute(
                    "INSERT INTO agent_steps(run_id,step_index,call_id,tool_name,arguments_json,state,"
                    "correlation_id,idempotency_key) VALUES(?,?,?,?,?,?,?,?)",
                    (run_id, index, call.call_id, call.tool_name, arguments_json,
                     TraceState.REQUESTED.value, correlation_id, idem),
                )
            self._db.execute("UPDATE agent_runs SET trace_bytes=? WHERE run_id=?", (total_bytes, run_id))
        return correlation_id

    def get_by_request_key(self, request_key: str, identity: AgentIdentity) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM agent_runs WHERE workspace_id=? AND user_id=? AND request_key=?",
                (identity.workspace_id, identity.user_id, request_key),
            ).fetchone()
        if row is None:
            return None
        run = dict(row)
        run.pop("plan_json", None)
        return run

    def get_run(
        self, run_id: str, identity: AgentIdentity,
        *, admin_roles: frozenset[str] = frozenset({"admin"}),
    ) -> dict[str, Any] | None:
        """Workspace-scoped run lookup for application and API callers."""
        run = self._get_run(run_id)
        if run is None:
            return None
        self._assert_scope(run, identity, admin_roles)
        run.pop("plan_json", None)
        return run

    def _get_run(self, run_id: str) -> dict[str, Any] | None:
        """Unscoped lookup for trusted runtime internals only."""
        with self._lock:
            row = self._db.execute("SELECT * FROM agent_runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def get_run_for(
        self, run_id: str, identity: AgentIdentity, *, admin_roles: frozenset[str] = frozenset({"admin"})
    ) -> dict[str, Any] | None:
        return self.get_run(run_id, identity, admin_roles=admin_roles)

    def list_runs_for(
        self,
        identity: AgentIdentity,
        *,
        limit: int = 100,
        admin_roles: frozenset[str] = frozenset({"admin"}),
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500:
            raise ValueError("run list limit must be between 1 and 500")
        admin = bool(identity.roles.intersection(admin_roles))
        with self._lock:
            if admin:
                rows = self._db.execute(
                    "SELECT run_id,user_id,workspace_id,plan_hash,goal,state,error_code,correlation_id,"
                    "trace_bytes,created_at,updated_at FROM agent_runs WHERE workspace_id=? "
                    "ORDER BY created_at DESC LIMIT ?", (identity.workspace_id, limit)
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT run_id,user_id,workspace_id,plan_hash,goal,state,error_code,correlation_id,"
                    "trace_bytes,created_at,updated_at FROM agent_runs WHERE workspace_id=? AND user_id=? "
                    "ORDER BY created_at DESC LIMIT ?", (identity.workspace_id, identity.user_id, limit)
                ).fetchall()
        return [dict(row) for row in rows]

    def list_steps(
        self, run_id: str, identity: AgentIdentity,
        *, admin_roles: frozenset[str] = frozenset({"admin"}),
    ) -> list[dict[str, Any]]:
        """Workspace-scoped step lookup for application and API callers."""
        self.get_run(run_id, identity, admin_roles=admin_roles)
        steps = self._list_steps(run_id)
        for step in steps:
            step.pop("idempotency_key", None)
        return steps

    def _list_steps(self, run_id: str) -> list[dict[str, Any]]:
        """Unscoped lookup for trusted runtime internals only."""
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM agent_steps WHERE run_id=? ORDER BY step_index", (run_id,)
            ).fetchall()
        result = []
        for row in rows:
            step = dict(row)
            step["arguments"] = json.loads(step.pop("arguments_json"))
            step["result"] = json.loads(step.pop("result_json")) if step["result_json"] is not None else None
            result.append(step)
        return result

    def list_steps_for(
        self, run_id: str, identity: AgentIdentity,
        *, admin_roles: frozenset[str] = frozenset({"admin"}),
    ) -> list[dict[str, Any]]:
        return self.list_steps(run_id, identity, admin_roles=admin_roles)

    def load_plan(self, run_id: str, identity: AgentIdentity) -> tuple[AgentPlan, str]:
        run = self._get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        self._assert_scope(run, identity)
        return AgentPlan.model_validate_json(run["plan_json"]), str(run["plan_hash"])

    def claim_run(self, run_id: str, *, resume: bool = False) -> bool:
        allowed = (TraceState.WAITING_APPROVAL.value,) if resume else (TraceState.VALIDATED.value,)
        placeholders = ",".join("?" for _ in allowed)
        with self._lock, self._db:
            cursor = self._db.execute(
                f"UPDATE agent_runs SET state=?,updated_at=? WHERE run_id=? AND state IN ({placeholders})",
                (TraceState.RUNNING.value, _now(), run_id, *allowed),
            )
            return cursor.rowcount == 1

    def claim_step(self, run_id: str, step_index: int) -> bool:
        """Compare-and-set the validated step to running before any handler can execute."""
        with self._lock, self._db:
            cursor = self._db.execute(
                "UPDATE agent_steps SET state=?,attempts=attempts+1,started_at=? "
                "WHERE run_id=? AND step_index=? AND state=?",
                (TraceState.RUNNING.value, _now(), run_id, step_index, TraceState.VALIDATED.value),
            )
            return cursor.rowcount == 1

    def set_run_state(self, run_id: str, state: TraceState, *, error_code: str | None = None) -> None:
        if error_code is not None:
            _validate_error_code(error_code)
        with self._lock, self._db:
            row = self._db.execute("SELECT state FROM agent_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            old = TraceState(row["state"])
            if old != state and state not in RUN_TRANSITIONS[old]:
                raise InvalidTransition(f"run cannot move from {old.value} to {state.value}")
            self._db.execute(
                "UPDATE agent_runs SET state=?,error_code=?,updated_at=? WHERE run_id=?",
                (state.value, error_code, _now(), run_id),
            )

    def set_step_state(
        self,
        run_id: str,
        step_index: int,
        state: TraceState,
        *,
        result: Any = _UNSET,
        error_code: str | None = None,
        attempts: int | None = None,
    ) -> None:
        if error_code is not None:
            _validate_error_code(error_code)
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT state,attempts FROM agent_steps WHERE run_id=? AND step_index=?",
                (run_id, step_index),
            ).fetchone()
            if row is None:
                raise KeyError((run_id, step_index))
            old = TraceState(row["state"])
            if old != state and state not in STEP_TRANSITIONS[old]:
                raise InvalidTransition(f"step cannot move from {old.value} to {state.value}")
            result_json: str | None = None
            if result is not _UNSET:
                result_json = _trace_json(result, self.redact_keys, self.max_field_bytes)
                current_bytes = self._db.execute(
                    "SELECT trace_bytes FROM agent_runs WHERE run_id=?", (run_id,)
                ).fetchone()[0]
                old_size = self._db.execute(
                    "SELECT length(CAST(COALESCE(result_json,'') AS BLOB)) FROM agent_steps "
                    "WHERE run_id=? AND step_index=?", (run_id, step_index)
                ).fetchone()[0]
                new_size = len(result_json.encode("utf-8"))
                available = self.max_run_bytes - (current_bytes - old_size)
                if new_size > available:
                    marker = _json({"_truncated": "run_size_limit"})
                    result_json = marker if len(marker.encode("utf-8")) <= available else (
                        "null" if available >= 4 else None
                    )
                    new_size = len(result_json.encode("utf-8")) if result_json is not None else 0
                self._db.execute("UPDATE agent_runs SET trace_bytes=? WHERE run_id=?",
                                 (current_bytes - old_size + new_size, run_id))
            assignments = ["state=?", "error_code=?", "attempts=?"]
            params: list[Any] = [state.value, error_code,
                                 row["attempts"] if attempts is None else attempts]
            if result is not _UNSET:
                assignments.append("result_json=?")
                params.append(result_json)
            if state in {TraceState.COMPLETED, TraceState.FAILED, TraceState.CANCELLED}:
                assignments.append("finished_at=?")
                params.append(_now())
            params.extend([run_id, step_index])
            self._db.execute(
                f"UPDATE agent_steps SET {','.join(assignments)} WHERE run_id=? AND step_index=?", params
            )

    def purge_expired(self, *, retention_days: int | None = None) -> int:
        days = self.retention_days if retention_days is None else retention_days
        if days < 1:
            raise ValueError("retention must be at least one day")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock, self._db:
            cursor = self._db.execute("DELETE FROM agent_runs WHERE created_at<?", (cutoff,))
            self._db.execute("DELETE FROM agent_approvals WHERE created_at<?", (cutoff,))
            return cursor.rowcount

    def cancel_for(self, run_id: str, identity: AgentIdentity) -> None:
        run = self._get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        self._assert_scope(run, identity)
        state = TraceState(run["state"])
        if state in {TraceState.COMPLETED, TraceState.FAILED, TraceState.CANCELLED}:
            return
        for step in self._list_steps(run_id):
            step_state = TraceState(step["state"])
            if step_state not in {TraceState.COMPLETED, TraceState.FAILED, TraceState.CANCELLED}:
                self.set_step_state(run_id, step["step_index"], TraceState.CANCELLED)
        self.set_run_state(run_id, TraceState.CANCELLED)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> TraceStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _assert_scope(run: dict[str, Any], identity: AgentIdentity,
                      admin_roles: frozenset[str] = frozenset({"admin"})) -> None:
        if run["workspace_id"] != identity.workspace_id:
            raise TraceAccessDenied("run is unavailable in this workspace")
        if run["user_id"] != identity.user_id and not identity.roles.intersection(admin_roles):
            raise TraceAccessDenied("run belongs to another user")


def _trace_json(value: Any, redact_keys: frozenset[str], max_field_bytes: int) -> str:
    try:
        sanitized = _sanitize(value, redact_keys, max_field_bytes)
        return _json(sanitized)
    except (TypeError, ValueError, OverflowError):
        return _json({"_trace_error": "non_json_value"})


def _contains_redacted_key(value: Any, redact_keys: frozenset[str]) -> bool:
    if isinstance(value, dict):
        return any(str(key).casefold() in redact_keys or _contains_redacted_key(item, redact_keys)
                   for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_redacted_key(item, redact_keys) for item in value)
    return False


def _sanitize(value: Any, redact_keys: frozenset[str], max_field_bytes: int, depth: int = 0) -> Any:
    if depth > 12:
        return "[depth-limited]"
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 100:
                cleaned["_truncated"] = "field_count_limit"
                break
            key_str = str(key)[:256]
            if key_str.casefold() in redact_keys:
                cleaned[key_str] = "[REDACTED]"
            else:
                cleaned[key_str] = _sanitize(item, redact_keys, max_field_bytes, depth + 1)
        return cleaned
    if isinstance(value, (list, tuple)):
        entries = [_sanitize(item, redact_keys, max_field_bytes, depth + 1) for item in value[:200]]
        if len(value) > 200:
            entries.append("[truncated]")
        return entries
    if isinstance(value, str):
        byte_count = len(value.encode("utf-8"))
        if byte_count > max_field_bytes:
            prefix_bytes = max(1, max_field_bytes - 20)
            return value.encode("utf-8")[:prefix_bytes].decode("utf-8", errors="ignore") + "...[truncated]"
        return value
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("non-finite number")
        return value
    raise TypeError("trace values must be JSON data")


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _idempotency_key(run_id: str, call_id: str, plan_hash: str) -> str:
    import hashlib

    return hashlib.sha256(f"{run_id}\0{call_id}\0{plan_hash}".encode("utf-8")).hexdigest()


def _validate_error_code(value: str) -> None:
    if not _ERROR_CODE.fullmatch(value):
        raise ValueError("trace error_code must be a safe code token")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

"""Per-workspace DuckDB storage with owner-scoped tables and redacted SQLite audit."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
import pandas as pd

from alpha_core.agent import AgentIdentity

from .ingest import profile_frame, preview_rows
from .models import ColumnConfig, ConfirmSchema, UploadProfile

SCHEMA_VERSION = 1
RETENTION_DAYS = 30
AUDIT_RETENTION_DAYS = 90
STAGING_TTL_SECONDS = 900
MAX_STAGED_UPLOADS = 256
MAX_STAGED_BYTES = 100 * 1024 * 1024


class DatasetUnavailable(LookupError):
    """The authenticated user has no active Copilot dataset."""


class DatasetExpired(LookupError):
    """The user's dataset reached its manifest retention deadline."""


class DatasetAccessDenied(PermissionError):
    """The dataset does not belong to the authenticated owner and workspace."""


@dataclass
class StagedUpload:
    identity_scope: str
    frame: pd.DataFrame
    source_sha256: str
    label: str
    created_at: float
    profile: UploadProfile


class CopilotStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self._staged: dict[str, StagedUpload] = {}
        self._lock = threading.RLock()
        self._workspace_locks: dict[str, threading.RLock] = {}

    def _workspace_hash(self, identity: AgentIdentity) -> str:
        return hashlib.sha256(identity.workspace_id.encode("utf-8")).hexdigest()[:24]

    def _owner_hash(self, identity: AgentIdentity) -> str:
        return hashlib.sha256(identity.user_id.encode("utf-8")).hexdigest()[:24]

    def _workspace_dir(self, identity: AgentIdentity) -> Path:
        workspace_dir = (self.root / self._workspace_hash(identity)).resolve()
        if workspace_dir.parent != self.root:
            raise DatasetAccessDenied("Workspace path is outside the configured data root.")
        return workspace_dir

    def _database_path(self, identity: AgentIdentity) -> Path:
        return self._workspace_dir(identity) / "copilot.duckdb"

    def _table_name(self, identity: AgentIdentity) -> str:
        return f"d_{self._owner_hash(identity)[:16]}"

    def _scope_key(self, identity: AgentIdentity) -> str:
        return f"{self._workspace_hash(identity)}:{self._owner_hash(identity)}"

    def _workspace_lock(self, identity: AgentIdentity) -> threading.RLock:
        key = self._workspace_hash(identity)
        with self._lock:
            return self._workspace_locks.setdefault(key, threading.RLock())

    def stage_frame(
        self,
        identity: AgentIdentity,
        frame: pd.DataFrame,
        *,
        content: bytes,
        filename_label: str,
        data_label: str = "USER_UPLOADED",
    ) -> UploadProfile:
        if not identity.active:
            raise DatasetAccessDenied("An active signed-in user is required.")
        columns, warnings, duplicate_rows = profile_frame(frame)
        upload_id = str(uuid4())
        profile = UploadProfile(
            upload_id=upload_id,
            filename_label=filename_label,
            source_sha256=hashlib.sha256(content).hexdigest(),
            row_count=len(frame),
            column_count=len(frame.columns),
            duplicate_rows=duplicate_rows,
            columns=columns,
            warnings=warnings,
            preview=preview_rows(frame),
            data_label=data_label,  # type: ignore[arg-type]
        )
        staged = StagedUpload(
            identity_scope=self._scope_key(identity), frame=frame.copy(deep=True),
            source_sha256=profile.source_sha256, label=data_label,
            created_at=time.monotonic(), profile=profile,
        )
        staged_bytes = int(staged.frame.memory_usage(index=True, deep=True).sum())
        with self._lock:
            self._expire_staging()
            if len(self._staged) >= MAX_STAGED_UPLOADS:
                raise ValueError("Temporary upload queue is full; confirm or discard an upload and retry.")
            if sum(
                int(item.frame.memory_usage(index=True, deep=True).sum())
                for item in self._staged.values()
            ) + staged_bytes > MAX_STAGED_BYTES:
                raise ValueError("Temporary previews reached the 100 MB memory limit; confirm an upload and retry.")
            self._staged[upload_id] = staged
        return profile

    def confirm(self, identity: AgentIdentity, request: ConfirmSchema) -> dict[str, Any]:
        with self._lock:
            self._expire_staging()
            staged = self._staged.get(request.upload_id)
        if staged is None:
            raise DatasetUnavailable("Upload preview expired; upload the file again.")
        if staged.identity_scope != self._scope_key(identity):
            raise DatasetAccessDenied("This preview belongs to another signed-in user or workspace.")
        config_by_name = {item.name: item for item in request.columns}
        if set(config_by_name) != {str(name) for name in staged.frame.columns}:
            raise ValueError("Confirm exactly one schema choice for every uploaded column.")
        if len(config_by_name) != len(request.columns):
            raise ValueError("A column can only be configured once.")
        if sum(item.role == "date" for item in request.columns) > 1:
            raise ValueError("Choose at most one date column.")
        if any(item.role == "date" and item.data_type != "date" for item in request.columns):
            raise ValueError("A date-role column must use the date data type.")
        if any(item.role == "measure" and item.data_type not in {"integer", "number"} for item in request.columns):
            raise ValueError("Measure columns must use an integer or number type.")
        manifest = self._write_dataset(identity, staged, request.columns)
        with self._lock:
            self._staged.pop(request.upload_id, None)
        return manifest

    def _write_dataset(
        self, identity: AgentIdentity, staged: StagedUpload, config: list[ColumnConfig],
    ) -> dict[str, Any]:
        workspace = self._workspace_dir(identity)
        workspace.mkdir(parents=True, exist_ok=True)
        path = self._database_path(identity)
        table = self._table_name(identity)
        typed = _typed_frame(staged.frame, config)
        columns = _columns_manifest(staged.frame, typed, config)
        issued_at = _now()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)).isoformat()
        user_hash, workspace_hash = self._owner_hash(identity), self._workspace_hash(identity)
        profile_summary = {
            "row_count": len(typed), "duplicate_rows": int(typed.duplicated().sum()),
            "columns": [
                {"name": column["name"], "data_type": column["data_type"],
                 "null_count": int(typed[column["safe_name"]].isna().sum()),
                 "cardinality": int(typed[column["safe_name"]].nunique(dropna=True)),
                 "minimum": _profile_bound(typed[column["safe_name"]].min()),
                 "maximum": _profile_bound(typed[column["safe_name"]].max()),
                 "sensitive": column["sensitive"]}
                for column in columns
            ],
        }
        schema_json = json.dumps(columns, sort_keys=True, separators=(",", ":"), allow_nan=False)
        profile_json = json.dumps(profile_summary, sort_keys=True, separators=(",", ":"), allow_nan=False)
        safe_table = _identifier(table)
        lock = self._workspace_lock(identity)
        with lock:
            connection = duckdb.connect(str(path), read_only=False, config={"threads": 2})
            try:
                connection.execute("BEGIN TRANSACTION")
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS copilot_manifest ("
                    "owner_hash VARCHAR PRIMARY KEY, workspace_hash VARCHAR NOT NULL, table_name VARCHAR NOT NULL, "
                    "source_sha256 VARCHAR NOT NULL, ingested_at VARCHAR NOT NULL, expires_at VARCHAR NOT NULL, "
                    "row_count BIGINT NOT NULL, schema_version INTEGER NOT NULL, schema_json VARCHAR NOT NULL, "
                    "profile_json VARCHAR NOT NULL, data_label VARCHAR NOT NULL)"
                )
                connection.register("_incoming_copilot_frame", typed)
                projection = ", ".join(_identifier(str(item["safe_name"])) for item in columns)
                connection.execute(f"CREATE OR REPLACE TABLE {safe_table} AS SELECT {projection} FROM _incoming_copilot_frame")
                connection.unregister("_incoming_copilot_frame")
                connection.execute("DELETE FROM copilot_manifest WHERE owner_hash=?", [user_hash])
                connection.execute(
                    "INSERT INTO copilot_manifest VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [user_hash, workspace_hash, table, staged.source_sha256, issued_at, expires_at,
                     len(typed), SCHEMA_VERSION, schema_json, profile_json, staged.label],
                )
                connection.execute("COMMIT")
            except Exception:
                try:
                    connection.execute("ROLLBACK")
                except duckdb.Error:
                    pass
                raise
            finally:
                connection.close()
        return {
            "row_count": len(typed), "source_sha256": staged.source_sha256,
            "ingested_at": issued_at, "expires_at": expires_at, "schema_version": SCHEMA_VERSION,
            "data_label": staged.label,
            "columns": [_public_column(column) for column in columns],
            "warnings": [
                warning.model_dump(mode="json") for warning in staged.profile.warnings
                if warning.column not in {str(item["name"]) for item in columns if item["sensitive"]}
            ],
        }

    def manifest(self, identity: AgentIdentity) -> dict[str, Any]:
        path = self._database_path(identity)
        if not path.is_file():
            raise DatasetUnavailable("Upload or select a dataset before querying.")
        try:
            with self._workspace_lock(identity):
                connection = duckdb.connect(str(path), read_only=True, config={"threads": 2})
                try:
                    row = connection.execute(
                        "SELECT * FROM copilot_manifest WHERE owner_hash=? AND workspace_hash=?",
                        [self._owner_hash(identity), self._workspace_hash(identity)],
                    ).fetchone()
                finally:
                    connection.close()
        except duckdb.Error as exc:
            raise DatasetUnavailable("The workspace dataset store is unavailable.") from exc
        if row is None:
            raise DatasetUnavailable("Upload or select a dataset before querying.")
        columns = [
            "owner_hash", "workspace_hash", "table_name", "source_sha256", "ingested_at", "expires_at",
            "row_count", "schema_version", "schema_json", "profile_json", "data_label",
        ]
        value = dict(zip(columns, row))
        if value["expires_at"] <= _now():
            self.remove_expired(identity)
            raise DatasetExpired("The uploaded dataset reached its retention deadline; upload it again to continue.")
        if value["table_name"] != self._table_name(identity):
            raise DatasetAccessDenied("The workspace manifest does not match the signed-in owner.")
        value["columns"] = json.loads(value.pop("schema_json"))
        value["profile"] = json.loads(value.pop("profile_json"))
        return value

    def read_frame(self, identity: AgentIdentity, manifest: dict[str, Any] | None = None) -> pd.DataFrame:
        current = manifest or self.manifest(identity)
        table = str(current["table_name"])
        if not re.fullmatch(r"d_[a-f0-9]{16}", table) or table != self._table_name(identity):
            raise DatasetAccessDenied("Dataset table is outside the signed-in owner's scope.")
        with self._workspace_lock(identity):
            connection = duckdb.connect(str(self._database_path(identity)), read_only=True, config={"threads": 2})
            try:
                return connection.execute(f"SELECT * FROM {_identifier(table)}").fetchdf()
            finally:
                connection.close()

    def profile(self, identity: AgentIdentity, *, include_preview: bool = True) -> dict[str, Any]:
        manifest = self.manifest(identity)
        profile = dict(manifest["profile"])
        columns = manifest["columns"]
        public_columns = [_public_column(column) for column in columns]
        profile.update({
            "source_sha256": manifest["source_sha256"], "ingested_at": manifest["ingested_at"],
            "expires_at": manifest["expires_at"], "schema_version": manifest["schema_version"],
            "data_label": manifest["data_label"], "columns": public_columns,
        })
        if include_preview:
            frame = self.read_frame(identity, manifest)
            by_safe = {str(column["safe_name"]): str(column["name"]) for column in columns}
            frame = frame.rename(columns=by_safe)
            visible_names = [str(column["name"]) for column in columns if not column["sensitive"]]
            profile["preview"] = preview_rows(frame[visible_names])
        return profile

    def profile_for_hub(self, identity: AgentIdentity) -> dict[str, Any]:
        manifest = self.manifest(identity)
        public_columns = [{
            "name": column["name"], "data_type": column["data_type"], "role": column["role"],
            "null_count": manifest["profile"]["columns"][index]["null_count"],
            "cardinality": manifest["profile"]["columns"][index]["cardinality"],
            **({
                "minimum": manifest["profile"]["columns"][index]["minimum"],
                "maximum": manifest["profile"]["columns"][index]["maximum"],
            } if column["role"] == "date" else {}),
        } for index, column in enumerate(manifest["columns"]) if not column["sensitive"] and column["role"] != "exclude"]
        return {
            "row_count": manifest["row_count"], "columns": public_columns,
            "data_label": manifest["data_label"], "source_sha256": manifest["source_sha256"],
        }

    def audit(self, identity: AgentIdentity, *, question_hash: str, status: str,
              plan: dict[str, Any] | None = None, query_id: str | None = None,
              result_rows: int = 0, elapsed_ms: float | None = None) -> None:
        workspace = self._workspace_dir(identity)
        workspace.mkdir(parents=True, exist_ok=True)
        path = workspace / "copilot-audit.sqlite"
        connection = sqlite3.connect(path, timeout=5)
        try:
            with connection as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS query_audit ("
                    "audit_id TEXT PRIMARY KEY, owner_hash TEXT NOT NULL, query_hash TEXT NOT NULL, "
                    "query_id TEXT, status TEXT NOT NULL, plan_json TEXT NOT NULL, result_rows INTEGER NOT NULL, "
                    "elapsed_ms REAL, created_at TEXT NOT NULL)"
                )
                cutoff = (datetime.now(timezone.utc) - timedelta(days=AUDIT_RETENTION_DAYS)).isoformat()
                db.execute("DELETE FROM query_audit WHERE created_at<?", [cutoff])
                redacted = _redact_plan(plan or {})
                db.execute(
                    "INSERT INTO query_audit VALUES (?,?,?,?,?,?,?,?,?)",
                    (str(uuid4()), self._owner_hash(identity), question_hash, query_id, status,
                     json.dumps(redacted, sort_keys=True, separators=(",", ":")), result_rows,
                     elapsed_ms, _now()),
                )
        finally:
            connection.close()

    def remove_expired(self, identity: AgentIdentity) -> None:
        path = self._database_path(identity)
        if not path.is_file():
            return
        with self._workspace_lock(identity):
            connection = duckdb.connect(str(path), read_only=False, config={"threads": 2})
            try:
                row = connection.execute(
                    "SELECT table_name FROM copilot_manifest WHERE owner_hash=? AND expires_at<=?",
                    [self._owner_hash(identity), _now()],
                ).fetchone()
                if row and re.fullmatch(r"d_[a-f0-9]{16}", row[0]):
                    connection.execute(f"DROP TABLE IF EXISTS {_identifier(row[0])}")
                    connection.execute("DELETE FROM copilot_manifest WHERE owner_hash=?", [self._owner_hash(identity)])
            finally:
                connection.close()

    def purge_expired(self) -> int:
        removed = 0
        if not self.root.is_dir():
            return removed
        for path in self.root.glob("*/copilot.duckdb"):
            try:
                connection = duckdb.connect(str(path), read_only=False, config={"threads": 1})
                try:
                    expired = connection.execute(
                        "SELECT owner_hash,table_name FROM copilot_manifest WHERE expires_at<=?", [_now()],
                    ).fetchall()
                    for owner_hash, table in expired:
                        if re.fullmatch(r"d_[a-f0-9]{16}", table):
                            connection.execute(f"DROP TABLE IF EXISTS {_identifier(table)}")
                            connection.execute("DELETE FROM copilot_manifest WHERE owner_hash=?", [owner_hash])
                            removed += 1
                finally:
                    connection.close()
            except duckdb.Error:
                # A broken workspace is left untouched and remains unavailable to queries.
                continue
        return removed

    def _expire_staging(self) -> None:
        now = time.monotonic()
        expired = [upload_id for upload_id, entry in self._staged.items()
                   if now - entry.created_at >= STAGING_TTL_SECONDS]
        for upload_id in expired:
            self._staged.pop(upload_id, None)


def _typed_frame(frame: pd.DataFrame, config: list[ColumnConfig]) -> pd.DataFrame:
    result = pd.DataFrame(index=frame.index)
    seen: set[str] = set()
    for index, item in enumerate(config):
        safe = _safe_column_name(item.name, index, seen)
        series = frame[item.name]
        if item.data_type == "text":
            converted = series.astype("string").str.strip().replace("", pd.NA)
        elif item.data_type == "integer":
            numeric = pd.to_numeric(series, errors="coerce")
            fractional = numeric.notna() & (numeric % 1 != 0)
            numeric = numeric.mask(fractional)
            converted = numeric.astype("Int64")
        elif item.data_type == "number":
            converted = pd.to_numeric(series, errors="coerce").astype("float64")
        elif item.data_type == "date":
            converted = pd.to_datetime(series, errors="coerce", format="mixed", utc=True).dt.tz_convert(None)
        else:
            values = series.astype("string").str.strip().str.casefold()
            converted = values.map({"true": True, "yes": True, "1": True,
                                    "false": False, "no": False, "0": False}).astype("boolean")
        result[safe] = converted
    return result


def _columns_manifest(frame: pd.DataFrame, typed: pd.DataFrame, config: list[ColumnConfig]) -> list[dict[str, Any]]:
    result = []
    seen: set[str] = set()
    for index, item in enumerate(config):
        safe_name = _safe_column_name(item.name, index, seen)
        source = frame[item.name]
        converted = typed[safe_name]
        invalid_count = int(source.notna().sum() - converted.notna().sum())
        result.append({
            "name": item.name, "safe_name": safe_name, "data_type": item.data_type,
            "role": item.role, "sensitive": item.sensitive,
            "null_count": int(converted.isna().sum()), "invalid_count": max(0, invalid_count),
            "cardinality": int(converted.nunique(dropna=True)),
            "minimum": _profile_bound(converted.min()), "maximum": _profile_bound(converted.max()),
            "outlier_count": _outlier_count(converted) if item.data_type in {"integer", "number"} else 0,
        })
    return result


def _safe_column_name(value: str, index: int, seen: set[str]) -> str:
    normalized = value.casefold()
    normalized = re.sub(r"[^a-z0-9_]+", "_", normalized).strip("_")
    if not normalized:
        normalized = f"column_{index + 1}"
    if normalized[0].isdigit():
        normalized = f"c_{normalized}"
    normalized = normalized[:96]
    candidate = normalized
    suffix = 2
    while candidate in seen:
        candidate = f"{normalized[:88]}_{suffix}"
        suffix += 1
    seen.add(candidate)
    return candidate


def _public_column(column: dict[str, Any]) -> dict[str, Any]:
    if column.get("sensitive"):
        return {
            "name": column["name"], "data_type": column["data_type"],
            "role": column["role"], "sensitive": True,
        }
    return dict(column)


def _profile_bound(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not pd.notna(value):
        return None
    return value


def _outlier_count(series: pd.Series) -> int:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if not len(values):
        return 0
    q1, q3 = values.quantile(0.25), values.quantile(0.75)
    spread = q3 - q1
    return int(((values < q1 - 1.5 * spread) | (values > q3 + 1.5 * spread)).sum())


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", value):
        raise ValueError("unsafe generated identifier")
    return f'"{value}"'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_plan(plan: dict[str, Any]) -> dict[str, Any]:
    result = dict(plan)
    filters = result.get("filters")
    if isinstance(filters, list):
        result["filters"] = [
            {key: value for key, value in item.items() if key != "value"}
            for item in filters if isinstance(item, dict)
        ]
    for measure in result.get("measures", []):
        if isinstance(measure, dict) and measure.get("sensitive"):
            measure["column"] = "[sensitive aggregate]"
    return result


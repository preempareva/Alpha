"""SQLite-backed, identity-bound approval records for side-effecting tools."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from .models import AgentIdentity

if TYPE_CHECKING:
    from .trace import TraceStore


class ApprovalError(PermissionError):
    """An approval request is invalid, unauthorized, expired, or already consumed."""


class ApprovalStore:
    def __init__(self, trace: TraceStore) -> None:
        self._trace = trace
        self._db = trace._db
        self._lock = trace._lock
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS agent_approvals (
              approval_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
              call_id TEXT NOT NULL,
              plan_hash TEXT NOT NULL,
              user_id TEXT NOT NULL,
              workspace_id TEXT NOT NULL,
              requested_by TEXT NOT NULL,
              approver_id TEXT,
              status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','expired')),
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              decided_at TEXT,
              consumed_at TEXT,
              reason TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_agent_approvals_pending
              ON agent_approvals(run_id,call_id,status,expires_at);
        """)
        self._db.commit()

    def request_approval(
        self,
        run_id: str,
        call_id: str,
        requester: AgentIdentity,
        *,
        expires_in_seconds: int = 900,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if not 1 <= expires_in_seconds <= 86_400:
            raise ValueError("approval expiry must be between 1 second and 1 day")
        now = _now()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                run = self._db.execute("SELECT * FROM agent_runs WHERE run_id=?", (run_id,)).fetchone()
                if run is None or run["user_id"] != requester.user_id or run["workspace_id"] != requester.workspace_id:
                    raise ApprovalError("approval requester does not own this workspace run")
                if run["state"] not in {"validated", "running", "waiting_approval"}:
                    raise ApprovalError("run is not eligible for approval")
                step = self._db.execute(
                    "SELECT 1 FROM agent_steps WHERE run_id=? AND call_id=?", (run_id, call_id)
                ).fetchone()
                if step is None:
                    raise ApprovalError("approval call does not belong to the run")
                existing = self._db.execute(
                    "SELECT * FROM agent_approvals WHERE run_id=? AND call_id=? AND plan_hash=? "
                    "AND status='pending' AND expires_at>? ORDER BY created_at DESC LIMIT 1",
                    (run_id, call_id, run["plan_hash"], now),
                ).fetchone()
                if existing:
                    self._db.commit()
                    return dict(existing)
                approval_id = str(uuid.uuid4())
                expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)).isoformat()
                self._db.execute(
                    "INSERT INTO agent_approvals(approval_id,run_id,call_id,plan_hash,user_id,workspace_id,"
                    "requested_by,status,created_at,expires_at,reason) VALUES(?,?,?,?,?,?,?,'pending',?,?,?)",
                    (approval_id, run_id, call_id, run["plan_hash"], requester.user_id,
                     requester.workspace_id, requester.user_id, now, expires_at, _reason(reason)),
                )
                row = self._db.execute(
                    "SELECT * FROM agent_approvals WHERE approval_id=?", (approval_id,)
                ).fetchone()
                self._db.commit()
                return dict(row)
            except Exception:
                self._db.rollback()
                raise

    def approve(
        self,
        approval_id: str,
        approver: AgentIdentity,
        *,
        allowed_roles: frozenset[str] = frozenset({"admin"}),
        allow_self_approval: bool = False,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return self._decide(approval_id, approver, "approved", allowed_roles,
                            allow_self_approval=allow_self_approval, reason=reason)

    def reject(
        self,
        approval_id: str,
        approver: AgentIdentity,
        *,
        allowed_roles: frozenset[str] = frozenset({"admin"}),
        reason: str | None = None,
    ) -> dict[str, Any]:
        return self._decide(approval_id, approver, "rejected", allowed_roles,
                            allow_self_approval=False, reason=reason)

    def list_for(
        self,
        identity: AgentIdentity,
        *,
        status: str = "pending",
        admin_roles: frozenset[str] = frozenset({"admin"}),
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if status not in {"pending", "approved", "rejected", "expired"} or not 1 <= limit <= 500:
            raise ValueError("invalid approval status or result limit")
        admin = bool(identity.roles.intersection(admin_roles))
        requester_filter = "" if admin else " AND a.requested_by=?"
        params: tuple[Any, ...] = ((identity.workspace_id, status, limit) if admin else
                                   (identity.workspace_id, status, identity.user_id, limit))
        with self._lock:
            rows = self._db.execute(
                "SELECT a.approval_id,a.run_id,a.call_id,a.plan_hash,a.user_id,a.workspace_id,"
                "a.requested_by,a.approver_id,a.status,a.created_at,a.expires_at,a.decided_at,"
                "a.consumed_at,a.reason FROM agent_approvals a "
                "WHERE a.workspace_id=? AND a.status=?" + requester_filter +
                " ORDER BY a.created_at DESC LIMIT ?", params,
            ).fetchall()
        return [dict(row) for row in rows]

    def _decide(
        self,
        approval_id: str,
        approver: AgentIdentity,
        status: str,
        allowed_roles: frozenset[str],
        *,
        allow_self_approval: bool,
        reason: str | None,
    ) -> dict[str, Any]:
        if not approver.active or not approver.roles.intersection(allowed_roles):
            raise ApprovalError("approver role is not authorized")
        now = _now()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    "SELECT * FROM agent_approvals WHERE approval_id=?", (approval_id,)
                ).fetchone()
                if row is None or row["workspace_id"] != approver.workspace_id:
                    raise ApprovalError("approval is unavailable in this workspace")
                if status == "approved" and row["requested_by"] == approver.user_id and not allow_self_approval:
                    raise ApprovalError("self-approval is not permitted")
                if row["status"] != "pending" or row["consumed_at"] is not None:
                    raise ApprovalError("approval is no longer pending")
                if row["expires_at"] <= now:
                    self._db.execute(
                        "UPDATE agent_approvals SET status='expired',decided_at=? "
                        "WHERE approval_id=? AND status='pending'",
                        (now, approval_id),
                    )
                    self._db.commit()
                    raise ApprovalError("approval has expired")
                self._db.execute(
                    "UPDATE agent_approvals SET status=?,approver_id=?,decided_at=?,reason=? "
                    "WHERE approval_id=? AND status='pending'",
                    (status, approver.user_id, now, _reason(reason), approval_id),
                )
                decided = self._db.execute(
                    "SELECT * FROM agent_approvals WHERE approval_id=?", (approval_id,)
                ).fetchone()
                self._db.commit()
                return dict(decided)
            except Exception:
                if self._db.in_transaction:
                    self._db.rollback()
                raise

    def expire_stale(self) -> int:
        with self._lock, self._db:
            cursor = self._db.execute(
                "UPDATE agent_approvals SET status='expired',decided_at=? "
                "WHERE status IN ('pending','approved') AND consumed_at IS NULL AND expires_at<=?",
                (_now(), _now()),
            )
            return cursor.rowcount

    def get_pending_for_call(
        self, run_id: str, call_id: str, identity: AgentIdentity,
        *, admin_roles: frozenset[str] = frozenset({"admin"}),
    ) -> dict[str, Any] | None:
        owner_clause = "1=1" if identity.roles.intersection(admin_roles) else "a.user_id=?"
        params: tuple[Any, ...] = ((run_id, call_id, _now(), identity.workspace_id)
                                   if owner_clause == "1=1" else
                                   (run_id, call_id, _now(), identity.workspace_id, identity.user_id))
        with self._lock:
            row = self._db.execute(
                "SELECT a.* FROM agent_approvals a JOIN agent_runs r ON r.run_id=a.run_id "
                "WHERE a.run_id=? AND a.call_id=? AND a.status='pending' AND a.consumed_at IS NULL "
                f"AND a.expires_at>? AND a.workspace_id=? AND {owner_clause} AND a.plan_hash=r.plan_hash "
                "ORDER BY a.created_at DESC LIMIT 1", params,
            ).fetchone()
        return dict(row) if row else None

    def get_approved_for_call(
        self, run_id: str, call_id: str, identity: AgentIdentity,
        *, admin_roles: frozenset[str] = frozenset({"admin"}),
    ) -> dict[str, Any] | None:
        owner_clause = "1=1" if identity.roles.intersection(admin_roles) else "a.user_id=?"
        params: tuple[Any, ...] = ((run_id, call_id, _now(), identity.workspace_id)
                                   if owner_clause == "1=1" else
                                   (run_id, call_id, _now(), identity.workspace_id, identity.user_id))
        with self._lock:
            row = self._db.execute(
                "SELECT a.* FROM agent_approvals a JOIN agent_runs r ON r.run_id=a.run_id "
                "WHERE a.run_id=? AND a.call_id=? AND a.status='approved' AND a.consumed_at IS NULL "
                f"AND a.expires_at>? AND a.workspace_id=? AND {owner_clause} AND a.plan_hash=r.plan_hash "
                "ORDER BY a.created_at DESC LIMIT 1", params,
            ).fetchone()
        return dict(row) if row else None

    def get_terminal_for_call(
        self, run_id: str, call_id: str, identity: AgentIdentity,
        *, admin_roles: frozenset[str] = frozenset({"admin"}),
    ) -> dict[str, Any] | None:
        owner_clause = "1=1" if identity.roles.intersection(admin_roles) else "a.user_id=?"
        params: tuple[Any, ...] = ((run_id, call_id, identity.workspace_id) if owner_clause == "1=1" else
                                   (run_id, call_id, identity.workspace_id, identity.user_id))
        with self._lock:
            row = self._db.execute(
                "SELECT a.* FROM agent_approvals a JOIN agent_runs r ON r.run_id=a.run_id "
                "WHERE a.run_id=? AND a.call_id=? AND a.status IN ('rejected','expired') "
                "AND a.workspace_id=? AND " + owner_clause + " AND a.plan_hash=r.plan_hash "
                "ORDER BY a.created_at DESC LIMIT 1", params,
            ).fetchone()
        return dict(row) if row else None

    def consume(
        self,
        approval_id: str,
        identity: AgentIdentity,
        *,
        run_id: str,
        call_id: str,
        plan_hash: str,
        admin_roles: frozenset[str] = frozenset({"admin"}),
    ) -> bool:
        now = _now()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    "SELECT * FROM agent_approvals WHERE approval_id=?", (approval_id,)
                ).fetchone()
                valid = bool(
                    row
                    and row["run_id"] == run_id
                    and row["call_id"] == call_id
                    and row["plan_hash"] == plan_hash
                    and (row["user_id"] == identity.user_id or identity.roles.intersection(admin_roles))
                    and row["workspace_id"] == identity.workspace_id
                    and row["status"] == "approved"
                    and row["consumed_at"] is None
                    and row["expires_at"] > now
                )
                if not valid:
                    if row and row["status"] in {"pending", "approved"} and row["expires_at"] <= now:
                        self._db.execute(
                            "UPDATE agent_approvals SET status='expired',decided_at=? "
                            "WHERE approval_id=? AND status IN ('pending','approved') "
                            "AND consumed_at IS NULL", (now, approval_id)
                        )
                    self._db.commit()
                    return False
                cursor = self._db.execute(
                    "UPDATE agent_approvals SET consumed_at=? WHERE approval_id=? "
                    "AND status='approved' AND consumed_at IS NULL AND expires_at>?",
                    (now, approval_id, now),
                )
                self._db.commit()
                return cursor.rowcount == 1
            except Exception:
                self._db.rollback()
                raise


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reason(value: str | None) -> str | None:
    if value is None:
        return None
    return value[:500]

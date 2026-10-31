"""Five-step, async dispatcher with persisted approvals and atomic step claims."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import sqlite3
import threading
from collections.abc import Awaitable
from typing import Any
from uuid import uuid4

from .models import AgentIdentity, AgentPlan, RunOutcome, ToolCallContext, TraceState
from .policy import PolicyEngine
from .registry import RetryableToolError, ToolNotFound, ToolRegistry
from .trace import TraceStore


class RunInProgress(RuntimeError):
    """Raised when another request currently owns a run's execution lease."""


class BoundedExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        policy: PolicyEngine,
        trace: TraceStore,
        *,
        max_steps: int = 5,
        retries: int = 1,
        approval_roles: frozenset[str] = frozenset({"admin"}),
        allow_self_approval: bool = False,
    ) -> None:
        if not 1 <= max_steps <= 5:
            raise ValueError("max_steps must be between 1 and 5")
        if not 0 <= retries <= 1:
            raise ValueError("retries must be 0 or 1")
        if not approval_roles:
            raise ValueError("at least one approval role is required")
        self.registry = registry
        self.policy = policy
        self.trace = trace
        self.max_steps = max_steps
        self.retries = retries
        self.approval_roles = approval_roles
        self.allow_self_approval = allow_self_approval
        self._guard = threading.RLock()
        self._run_locks: dict[str, threading.Lock] = {}
        self._active_events: dict[str, tuple[asyncio.Event, asyncio.AbstractEventLoop]] = {}

    async def run(
        self,
        plan: AgentPlan | dict[str, Any] | None,
        identity: AgentIdentity,
        *,
        run_id: str | None = None,
        idempotency_key: str | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> RunOutcome:
        if not identity.active:
            raise PermissionError("an active authenticated identity is required")
        resuming = run_id is not None
        if resuming:
            assert run_id is not None
            if idempotency_key is not None:
                raise ValueError("resume does not accept a new idempotency key")
            if plan is not None:
                raise ValueError("resume accepts only run_id; the saved plan is authoritative")
            saved, plan_hash = self.trace.load_plan(run_id, identity)
            stored = self.trace._get_run(run_id)
            if stored is None or stored["state"] != TraceState.WAITING_APPROVAL.value:
                raise ValueError("only a run waiting for approval can be resumed")
            plan_snapshot = saved.model_copy(deep=True)
        else:
            if plan is None:
                raise ValueError("a new run requires a plan")
            if idempotency_key is not None and not 1 <= len(idempotency_key) <= 128:
                raise ValueError("idempotency key must contain 1 to 128 characters")
            if idempotency_key is not None:
                existing = self.trace.get_by_request_key(idempotency_key, identity)
                if existing is not None:
                    if existing["state"] == TraceState.RUNNING.value:
                        raise RunInProgress("a request with this idempotency key is already running")
                    return self._outcome_for_existing(existing, identity)
            plan_snapshot = _snapshot_plan(plan)
            if len(plan_snapshot.steps) > self.max_steps:
                raise ValueError(f"plan exceeds the executor limit of {self.max_steps} steps")
            canonical = _canonical_plan(plan_snapshot)
            plan_snapshot = AgentPlan.model_validate_json(canonical)
            plan_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            run_id = str(uuid4())
            try:
                self.trace.create_run(run_id, identity, plan_snapshot, plan_hash, canonical,
                                      request_key=idempotency_key)
            except sqlite3.IntegrityError:
                if idempotency_key is None:
                    raise
                existing = self.trace.get_by_request_key(idempotency_key, identity)
                if existing is None or existing["state"] == TraceState.RUNNING.value:
                    raise RunInProgress("a concurrent request claimed this idempotency key")
                return self._outcome_for_existing(existing, identity)
            self.trace.set_run_state(run_id, TraceState.PLANNED)
            for index in range(len(plan_snapshot.steps)):
                self.trace.set_step_state(run_id, index, TraceState.PLANNED)
                self.trace.set_step_state(run_id, index, TraceState.VALIDATED)
            self.trace.set_run_state(run_id, TraceState.VALIDATED)
            stored = self.trace._get_run(run_id)

        assert run_id is not None and stored is not None
        if len(plan_snapshot.steps) > self.max_steps:
            raise ValueError(f"saved plan exceeds the executor limit of {self.max_steps} steps")
        TraceStore._assert_scope(stored, identity)
        if stored["plan_hash"] != plan_hash:
            raise ValueError("saved plan integrity check failed")

        lock = self._acquire_run_lock(run_id)
        if lock is None:
            raise RunInProgress("another request is already executing this run")
        event = cancel_event or asyncio.Event()
        loop = asyncio.get_running_loop()
        with self._guard:
            self._active_events[run_id] = (event, loop)
        correlation_id = str(stored["correlation_id"])
        try:
            if not self.trace.claim_run(run_id, resume=resuming):
                raise RunInProgress("run state was claimed by another request")
            for index, call in enumerate(plan_snapshot.steps):
                step = self.trace._list_steps(run_id)[index]
                step_state = TraceState(step["state"])
                if step_state == TraceState.COMPLETED:
                    continue
                if step_state in {TraceState.FAILED, TraceState.CANCELLED}:
                    return self._outcome(run_id)
                if event.is_set():
                    self.trace.cancel_for(run_id, identity)
                    return self._outcome(run_id)
                try:
                    tool = self.registry.get(call.tool_name)
                except ToolNotFound:
                    self._fail_step(run_id, index, "TOOL_NOT_ALLOWLISTED")
                    return self._outcome(run_id)

                approval: dict[str, Any] | None = None
                decision = self.policy.authorize(tool, call, identity)
                if not decision.allowed and decision.reason == "approval_required":
                    self.trace.approvals.expire_stale()
                    approval = self.trace.approvals.get_approved_for_call(
                        run_id, call.call_id, identity, admin_roles=self.approval_roles
                    )
                    if approval is None:
                        pending = self.trace.approvals.get_pending_for_call(
                            run_id, call.call_id, identity, admin_roles=self.approval_roles
                        )
                        if pending is None:
                            terminal = self.trace.approvals.get_terminal_for_call(
                                run_id, call.call_id, identity, admin_roles=self.approval_roles
                            )
                            if terminal is not None:
                                code = "APPROVAL_REJECTED" if terminal["status"] == "rejected" else "APPROVAL_EXPIRED"
                                self._fail_step(run_id, index, code)
                                return self._outcome(run_id)
                        if pending is None:
                            pending = self.trace.approvals.request_approval(
                                run_id, call.call_id, identity,
                                reason=f"Approval required for {tool.spec.name}",
                            )
                        self._wait_for_approval(run_id, index)
                        return self._outcome(
                            run_id, pending_call_id=call.call_id,
                            pending_approval_id=str(pending["approval_id"]),
                        )
                    self.trace.set_step_state(run_id, index, TraceState.VALIDATED)
                elif not decision.allowed:
                    self._fail_step(run_id, index, decision.reason.upper())
                    return self._outcome(run_id)

                if not self.trace.claim_step(run_id, index):
                    raise RunInProgress("step was already claimed; refusing duplicate execution")
                attempts = 1
                while True:
                    # Re-check identity, workspace, allowlist, arguments and approval at dispatch.
                    decision = self.policy.authorize(tool, call, identity, approved=approval is not None)
                    if not decision.allowed:
                        self._fail_step(run_id, index, decision.reason.upper(), attempts=attempts)
                        return self._outcome(run_id)
                    if approval is not None and not self.trace.approvals.consume(
                        str(approval["approval_id"]), identity, run_id=run_id,
                        call_id=call.call_id, plan_hash=plan_hash, admin_roles=self.approval_roles,
                    ):
                        self._fail_step(run_id, index, "APPROVAL_INVALID", attempts=attempts)
                        return self._outcome(run_id)
                    step_now = self.trace._list_steps(run_id)[index]
                    context = ToolCallContext(
                        run_id=run_id,
                        step_index=index,
                        call_id=call.call_id,
                        idempotency_key=step_now["idempotency_key"],
                        correlation_id=correlation_id,
                    )
                    try:
                        result = await _await_bounded(
                            tool.invoke(identity, dict(call.arguments), context),
                            tool.spec.timeout_seconds,
                            event,
                        )
                        output_error = self.policy.validate_output(tool, result)
                        if output_error:
                            self._fail_step(run_id, index, output_error.upper(), attempts=attempts)
                            return self._outcome(run_id)
                        self.trace.set_step_state(
                            run_id, index, TraceState.COMPLETED, result=result, attempts=attempts
                        )
                        break
                    except _Cancelled:
                        self.trace.cancel_for(run_id, identity)
                        return self._outcome(run_id)
                    except TimeoutError:
                        self._fail_step(run_id, index, "TIMEOUT", attempts=attempts)
                        return self._outcome(run_id)
                    except RetryableToolError:
                        if tool.spec.side_effect != "read" or attempts > self.retries:
                            self._fail_step(run_id, index, "RETRY_DENIED", attempts=attempts)
                            return self._outcome(run_id)
                        attempts += 1
                        self.trace.set_step_state(
                            run_id, index, TraceState.RUNNING, attempts=attempts
                        )
                    except Exception:
                        self._fail_step(run_id, index, "TOOL_ERROR", attempts=attempts)
                        return self._outcome(run_id)

            self.trace.set_run_state(run_id, TraceState.COMPLETED)
            return self._outcome(run_id)
        except asyncio.CancelledError:
            self.trace.cancel_for(run_id, identity)
            raise
        finally:
            with self._guard:
                self._active_events.pop(run_id, None)
            self._release_run_lock(run_id, lock)

    def approve(self, approval_id: str, approver: AgentIdentity, *, reason: str | None = None) -> dict[str, Any]:
        return self.trace.approvals.approve(
            approval_id, approver, allowed_roles=self.approval_roles,
            allow_self_approval=self.allow_self_approval, reason=reason,
        )

    def reject(self, approval_id: str, approver: AgentIdentity, *, reason: str | None = None) -> dict[str, Any]:
        record = self.trace.approvals.reject(
            approval_id, approver, allowed_roles=self.approval_roles, reason=reason,
        )
        run_id = str(record["run_id"])
        for step in self.trace._list_steps(run_id):
            if step["call_id"] == record["call_id"] and step["state"] == TraceState.WAITING_APPROVAL.value:
                self.trace.set_step_state(run_id, step["step_index"], TraceState.FAILED,
                                          error_code="APPROVAL_REJECTED")
                break
        run = self.trace._get_run(run_id)
        if run is not None and run["state"] == TraceState.WAITING_APPROVAL.value:
            self.trace.set_run_state(run_id, TraceState.FAILED, error_code="APPROVAL_REJECTED")
        return record

    def cancel(self, run_id: str, identity: AgentIdentity) -> bool:
        self.trace.get_run_for(run_id, identity)
        with self._guard:
            active = self._active_events.get(run_id)
        if active is not None:
            event, loop = active
            loop.call_soon_threadsafe(event.set)
            return True
        self.trace.cancel_for(run_id, identity)
        return True

    def _acquire_run_lock(self, run_id: str) -> threading.Lock | None:
        with self._guard:
            lock = self._run_locks.setdefault(run_id, threading.Lock())
            if not lock.acquire(blocking=False):
                return None
            return lock

    def _release_run_lock(self, run_id: str, lock: threading.Lock) -> None:
        lock.release()
        with self._guard:
            if not lock.locked():
                self._run_locks.pop(run_id, None)

    def _wait_for_approval(self, run_id: str, index: int) -> None:
        state = TraceState(self.trace._list_steps(run_id)[index]["state"])
        if state != TraceState.WAITING_APPROVAL:
            self.trace.set_step_state(run_id, index, TraceState.WAITING_APPROVAL)
        run = self.trace._get_run(run_id)
        if run and run["state"] != TraceState.WAITING_APPROVAL.value:
            self.trace.set_run_state(run_id, TraceState.WAITING_APPROVAL)

    def _fail_step(self, run_id: str, index: int, code: str, *, attempts: int | None = None) -> None:
        state = TraceState(self.trace._list_steps(run_id)[index]["state"])
        if state not in {TraceState.FAILED, TraceState.COMPLETED, TraceState.CANCELLED}:
            self.trace.set_step_state(run_id, index, TraceState.FAILED, error_code=code, attempts=attempts)
        self.trace.set_run_state(run_id, TraceState.FAILED, error_code=code)

    def _outcome(
        self,
        run_id: str,
        *,
        pending_call_id: str | None = None,
        pending_approval_id: str | None = None,
    ) -> RunOutcome:
        run = self.trace._get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        steps = self.trace._list_steps(run_id)
        results = [step["result"] for step in steps if step["state"] == TraceState.COMPLETED.value]
        return RunOutcome(
            run_id=run_id,
            state=run["state"],
            results=results,
            pending_approval_call_id=pending_call_id,
            pending_approval_id=pending_approval_id,
            error_code=run["error_code"],
            correlation_id=run["correlation_id"],
        )

    def _outcome_for_existing(self, run: dict[str, Any], identity: AgentIdentity) -> RunOutcome:
        pending_call_id: str | None = None
        pending_approval_id: str | None = None
        if run["state"] == TraceState.WAITING_APPROVAL.value:
            for step in self.trace._list_steps(str(run["run_id"])):
                if step["state"] == TraceState.WAITING_APPROVAL.value:
                    pending_call_id = str(step["call_id"])
                    approval = self.trace.approvals.get_pending_for_call(
                        str(run["run_id"]), pending_call_id, identity,
                        admin_roles=self.approval_roles,
                    )
                    pending_approval_id = str(approval["approval_id"]) if approval else None
                    break
        return self._outcome(str(run["run_id"]), pending_call_id=pending_call_id,
                             pending_approval_id=pending_approval_id)


class _Cancelled(Exception):
    pass


def _snapshot_plan(plan: AgentPlan | dict[str, Any]) -> AgentPlan:
    if isinstance(plan, AgentPlan):
        return plan.model_copy(deep=True)
    return AgentPlan.model_validate(copy.deepcopy(plan))


def _canonical_plan(plan: AgentPlan) -> str:
    return json.dumps(plan.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


async def _await_bounded(awaitable: Awaitable[Any], timeout_seconds: int,
                         cancel_event: asyncio.Event) -> Any:
    task = asyncio.ensure_future(awaitable)
    cancel_task: asyncio.Task[bool] | None = None
    try:
        if cancel_event.is_set():
            raise _Cancelled
        cancel_task = asyncio.create_task(cancel_event.wait())
        done, _ = await asyncio.wait(
            {task, cancel_task}, timeout=timeout_seconds, return_when=asyncio.FIRST_COMPLETED
        )
        if task in done:
            return task.result()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if cancel_task in done:
            raise _Cancelled
        raise TimeoutError
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if cancel_task is not None:
            cancel_task.cancel()
            await asyncio.gather(cancel_task, return_exceptions=True)

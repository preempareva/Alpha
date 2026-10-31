from __future__ import annotations

import asyncio
import sqlite3

import pytest
from pydantic import ValidationError

from alpha_core.agent import (
    ApprovalError,
    AgentIdentity,
    AgentPlan,
    BoundedExecutor,
    InvalidTransition,
    PolicyEngine,
    RetryableToolError,
    RunInProgress,
    ToolCall,
    ToolRegistry,
    ToolSpec,
    TraceState,
    TraceAccessDenied,
    TraceStore,
)


def make_spec(handler, **updates):
    values = {
        "name": "sample.read",
        "description": "Return a synthetic sample value.",
        "input_schema": {
            "type": "object", "required": ["value"],
            "properties": {"value": {"type": "string", "maxLength": 100}},
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object", "required": ["value"],
            "properties": {"value": {"type": "string"}}, "additionalProperties": False,
        },
        "module": handler.__module__,
        "allowed_roles": {"analyst"},
    }
    values.update(updates)
    return ToolSpec(**values)


def make_runtime(handler, spec=None, *, retries=1):
    registry = ToolRegistry()
    registry.register(spec or make_spec(handler), handler)
    trace = TraceStore()
    return BoundedExecutor(registry, PolicyEngine(), trace, retries=retries), trace


def make_identity(**updates):
    values = {"user_id": "user-1", "roles": {"analyst"}, "workspace_id": "workspace-1"}
    values.update(updates)
    return AgentIdentity(**values)


def make_plan(*calls):
    return AgentPlan(agent_name="Test planner", goal="Inspect a synthetic value", steps=list(calls))


def test_role_denial_happens_before_tool_dispatch():
    calls = []

    async def handler(identity, arguments):
        calls.append(arguments)
        return {"value": "ok"}

    executor, trace = make_runtime(handler)
    outcome = asyncio.run(executor.run(make_plan(ToolCall(tool_name="sample.read", arguments={"value": "x"})),
                                        make_identity(roles={"viewer"})))

    assert outcome.state == TraceState.FAILED
    assert outcome.error_code == "ROLE_DENIED"
    assert calls == []
    assert trace.list_steps_for(outcome.run_id, make_identity())[0]["state"] == TraceState.FAILED


def test_workspace_denial_happens_before_tool_dispatch():
    calls = []

    async def handler(identity, arguments):
        calls.append(arguments)
        return {"value": "ok"}

    spec = make_spec(handler, allowed_workspaces={"workspace-allowed"})
    executor, _ = make_runtime(handler, spec)
    outcome = asyncio.run(executor.run(make_plan(ToolCall(tool_name=spec.name, arguments={"value": "x"})),
                                        make_identity()))

    assert outcome.error_code == "WORKSPACE_DENIED"
    assert calls == []


def test_malformed_plan_is_rejected_and_step_count_is_bounded():
    with pytest.raises(ValidationError):
        AgentPlan(agent_name="planner", goal="invalid", steps=[])
    with pytest.raises(ValidationError):
        make_plan(*(ToolCall(tool_name="sample.read", arguments={"value": "x"}) for _ in range(6)))


def test_tool_not_in_allowlist_fails_closed():
    async def handler(identity, arguments):
        return {"value": arguments["value"]}

    executor, _ = make_runtime(handler)
    outcome = asyncio.run(executor.run(make_plan(ToolCall(tool_name="unknown.tool", arguments={"value": "x"})),
                                        make_identity()))

    assert outcome.state == TraceState.FAILED
    assert outcome.error_code == "TOOL_NOT_ALLOWLISTED"


def test_module_mismatch_fails_policy_check():
    calls = []

    async def handler(identity, arguments):
        calls.append(arguments)
        return {"value": "ok"}

    spec = make_spec(handler, module="untrusted.module")
    executor, _ = make_runtime(handler, spec)
    outcome = asyncio.run(executor.run(make_plan(ToolCall(tool_name=spec.name, arguments={"value": "x"})),
                                        make_identity()))

    assert outcome.error_code == "MODULE_DENIED"
    assert calls == []


def test_malformed_arguments_are_rejected_before_dispatch():
    calls = []

    async def handler(identity, arguments):
        calls.append(arguments)
        return {"value": "ok"}

    executor, _ = make_runtime(handler)
    outcome = asyncio.run(executor.run(make_plan(ToolCall(tool_name="sample.read", arguments={"unexpected": 1})),
                                        make_identity()))

    assert outcome.error_code == "INVALID_ARGUMENTS"
    assert calls == []


def test_timeout_cancels_async_tool():
    async def handler(identity, arguments):
        await asyncio.sleep(2)
        return {"value": "late"}

    spec = make_spec(handler, timeout_seconds=1)
    executor, trace = make_runtime(handler, spec)
    outcome = asyncio.run(executor.run(make_plan(ToolCall(tool_name=spec.name, arguments={"value": "x"})),
                                        make_identity()))

    assert outcome.error_code == "TIMEOUT"
    assert trace.list_steps_for(outcome.run_id, make_identity())[0]["state"] == TraceState.FAILED


def test_one_transient_failure_is_retried_and_traced():
    attempts = 0

    async def handler(identity, arguments):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RetryableToolError("temporary read failure")
        return {"value": arguments["value"]}

    executor, trace = make_runtime(handler)
    outcome = asyncio.run(executor.run(make_plan(ToolCall(tool_name="sample.read", arguments={"value": "ok"})),
                                        make_identity()))

    assert outcome.state == TraceState.COMPLETED
    assert attempts == 2
    assert trace.list_steps_for(outcome.run_id, make_identity())[0]["attempts"] == 2


def test_cancellation_stops_the_active_tool_and_marks_trace():
    async def handler(identity, arguments):
        await asyncio.sleep(10)
        return {"value": "late"}

    executor, trace = make_runtime(handler)

    async def run_and_cancel():
        cancel_event = asyncio.Event()
        task = asyncio.create_task(executor.run(
            make_plan(ToolCall(tool_name="sample.read", arguments={"value": "x"})),
            make_identity(), cancel_event=cancel_event,
        ))
        await asyncio.sleep(0.02)
        cancel_event.set()
        return await task

    outcome = asyncio.run(run_and_cancel())
    assert outcome.state == TraceState.CANCELLED
    assert trace.list_steps_for(outcome.run_id, make_identity())[0]["state"] == TraceState.CANCELLED


def test_persisted_approval_is_scoped_single_use_and_rechecked():
    calls = []

    async def handler(identity, arguments):
        calls.append(arguments)
        return {"value": "drafted"}

    spec = make_spec(handler, side_effect="draft", requires_approval=True)
    executor, trace = make_runtime(handler, spec)
    plan = make_plan(ToolCall(tool_name=spec.name, arguments={"value": "draft"}))
    waiting = asyncio.run(executor.run(plan, make_identity()))

    assert waiting.state == TraceState.WAITING_APPROVAL
    assert waiting.pending_approval_call_id == plan.steps[0].call_id
    assert calls == []
    assert trace.list_steps_for(waiting.run_id, make_identity())[0]["state"] == TraceState.WAITING_APPROVAL
    approval_id = waiting.pending_approval_id
    assert approval_id
    record = trace._db.execute(
        "SELECT approval_id,run_id,call_id,plan_hash,user_id,workspace_id,requested_by,status "
        "FROM agent_approvals WHERE approval_id=?", (approval_id,),
    ).fetchone()
    assert record["run_id"] == waiting.run_id
    assert record["call_id"] == plan.steps[0].call_id
    assert record["plan_hash"] == trace.get_run_for(waiting.run_id, make_identity())["plan_hash"]
    assert record["requested_by"] == "user-1"
    assert record["status"] == "pending"

    with pytest.raises(TypeError):
        executor.run(plan, make_identity(), run_id=waiting.run_id, approved_call_ids={plan.steps[0].call_id})
    with pytest.raises(ApprovalError):
        executor.approve(approval_id, make_identity(user_id="other-user", roles={"analyst"}))
    with pytest.raises(ApprovalError):
        executor.approve(approval_id, make_identity(user_id="other-admin", roles={"admin"},
                                                    workspace_id="other-workspace"))
    executor.approve(approval_id, make_identity(user_id="admin-1", roles={"admin"}))
    assert not trace.approvals.consume(
        approval_id, make_identity(), run_id=waiting.run_id,
        call_id=plan.steps[0].call_id, plan_hash="0" * 64,
    )
    assert trace._db.execute(
        "SELECT consumed_at FROM agent_approvals WHERE approval_id=?", (approval_id,)
    ).fetchone()[0] is None

    done = asyncio.run(executor.run(None, make_identity(), run_id=waiting.run_id))
    assert done.state == TraceState.COMPLETED
    assert calls == [{"value": "draft"}]
    approval = trace._db.execute(
        "SELECT status,approver_id,consumed_at FROM agent_approvals WHERE approval_id=?", (approval_id,)
    ).fetchone()
    assert approval["status"] == "approved"
    assert approval["approver_id"] == "admin-1"
    assert approval["consumed_at"]
    assert not trace.approvals.consume(approval_id, make_identity(), run_id=waiting.run_id,
                                       call_id=plan.steps[0].call_id,
                                       plan_hash=trace.get_run_for(waiting.run_id, make_identity())["plan_hash"])
    with pytest.raises(ValueError, match="only a run waiting"):
        asyncio.run(executor.run(None, make_identity(), run_id=waiting.run_id))


def test_self_approval_is_blocked_and_rejection_is_terminal():
    calls = []

    async def handler(identity, arguments):
        calls.append(arguments)
        return {"value": "drafted"}

    spec = make_spec(handler, side_effect="draft", requires_approval=True, allowed_roles={"admin"})
    executor, trace = make_runtime(handler, spec)
    owner = make_identity(roles={"admin"})
    outcome = asyncio.run(executor.run(make_plan(ToolCall(tool_name=spec.name, arguments={"value": "draft"})),
                                        owner))
    assert outcome.state == TraceState.WAITING_APPROVAL
    assert outcome.pending_approval_id
    with pytest.raises(ApprovalError, match="self-approval"):
        executor.approve(outcome.pending_approval_id, owner)
    record = executor.reject(outcome.pending_approval_id,
                             make_identity(user_id="reviewer", roles={"admin"}), reason="not approved")
    assert record["status"] == "rejected"
    assert record["reason"] == "not approved"
    with pytest.raises(ApprovalError):
        executor.approve(outcome.pending_approval_id,
                         make_identity(user_id="reviewer", roles={"admin"}))
    assert calls == []
    assert trace.get_run_for(outcome.run_id, owner)["state"] == TraceState.FAILED.value


def test_llm_off_keeps_the_deterministic_tool_path(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "none")

    async def handler(identity, arguments):
        return {"value": arguments["value"].upper()}

    executor, _ = make_runtime(handler)
    outcome = asyncio.run(executor.run(make_plan(ToolCall(tool_name="sample.read", arguments={"value": "alpha"})),
                                        make_identity()))

    assert outcome.state == TraceState.COMPLETED
    assert outcome.results == [{"value": "ALPHA"}]


def test_output_row_and_byte_caps_are_enforced():
    async def handler(identity, arguments):
        return {"rows": [{"id": 1}, {"id": 2}], "value": "x"}

    spec = make_spec(handler, output_schema={"type": "object"}, max_rows=1)
    executor, _ = make_runtime(handler, spec)
    outcome = asyncio.run(executor.run(make_plan(ToolCall(tool_name=spec.name, arguments={"value": "x"})),
                                        make_identity()))
    assert outcome.error_code == "ROW_LIMIT_EXCEEDED"

    spec = make_spec(handler, output_schema={"type": "object"}, max_bytes=30)
    executor, _ = make_runtime(handler, spec)
    outcome = asyncio.run(executor.run(make_plan(ToolCall(tool_name=spec.name, arguments={"value": "x"})),
                                        make_identity()))
    assert outcome.error_code == "OUTPUT_TOO_LARGE"


def test_plan_is_snapshotted_before_dispatch_and_resume_uses_saved_plan_only():
    started = None
    release = None
    received = []

    async def handler(identity, arguments):
        received.append(arguments["value"])
        started.set()
        await release.wait()
        return {"value": arguments["value"]}

    executor, _ = make_runtime(handler)
    call = ToolCall(tool_name="sample.read", arguments={"value": "original"})
    plan = make_plan(call)

    async def scenario():
        nonlocal started, release
        started, release = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(executor.run(plan, make_identity()))
        await started.wait()
        call.arguments["value"] = "mutated"
        release.set()
        return await task

    outcome = asyncio.run(scenario())
    assert received == ["original"]
    assert outcome.results == [{"value": "original"}]

    draft_spec = make_spec(handler, side_effect="draft", requires_approval=True)
    executor, _ = make_runtime(handler, draft_spec)
    waiting = asyncio.run(executor.run(make_plan(ToolCall(tool_name=draft_spec.name,
                                                          arguments={"value": "pending"})), make_identity()))
    alternate = make_plan(ToolCall(tool_name=draft_spec.name, arguments={"value": "attacker"}))
    with pytest.raises(ValueError, match="saved plan is authoritative"):
        asyncio.run(executor.run(alternate, make_identity(), run_id=waiting.run_id))


def test_tool_spec_is_deep_copied_at_registration():
    async def handler(identity, arguments):
        return {"value": arguments["value"]}

    spec = make_spec(handler)
    registry = ToolRegistry()
    registry.register(spec, handler)
    spec.input_schema["properties"]["value"]["maxLength"] = 1
    executor = BoundedExecutor(registry, PolicyEngine(), TraceStore())
    outcome = asyncio.run(executor.run(make_plan(ToolCall(tool_name=spec.name,
                                                          arguments={"value": "long enough"})),
                                        make_identity()))
    assert outcome.state == TraceState.COMPLETED


def test_duplicate_idempotency_key_executes_exactly_once_and_exposes_step_key():
    started = None
    release = None
    calls = []

    async def handler(identity, arguments, *, context):
        calls.append(context.idempotency_key)
        started.set()
        await release.wait()
        return {"value": arguments["value"]}

    executor, trace = make_runtime(handler)

    async def scenario():
        nonlocal started, release
        started, release = asyncio.Event(), asyncio.Event()
        plan = make_plan(ToolCall(tool_name="sample.read", arguments={"value": "once"}))
        first = asyncio.create_task(executor.run(plan, make_identity(), idempotency_key="request-1"))
        await started.wait()
        with pytest.raises(RunInProgress):
            await executor.run(plan, make_identity(), idempotency_key="request-1")
        release.set()
        return plan, await first

    plan, outcome = asyncio.run(scenario())
    assert outcome.state == TraceState.COMPLETED
    assert len(calls) == 1
    persisted_key = trace._db.execute(
        "SELECT idempotency_key FROM agent_steps WHERE run_id=?", (outcome.run_id,)
    ).fetchone()[0]
    assert calls[0] == persisted_key
    replay = asyncio.run(executor.run(plan, make_identity(), idempotency_key="request-1"))
    assert replay.run_id == outcome.run_id
    assert len(calls) == 1


def test_non_read_side_effects_are_never_automatically_retried():
    calls = 0

    async def handler(identity, arguments):
        nonlocal calls
        calls += 1
        raise RetryableToolError("transient")

    spec = make_spec(handler, side_effect="draft", requires_approval=True)
    executor, _ = make_runtime(handler, spec)
    owner = make_identity()
    waiting = asyncio.run(executor.run(make_plan(ToolCall(tool_name=spec.name,
                                                          arguments={"value": "draft"})), owner))
    executor.approve(waiting.pending_approval_id,
                     make_identity(user_id="admin", roles={"admin"}))
    outcome = asyncio.run(executor.run(None, owner, run_id=waiting.run_id))
    assert outcome.error_code == "RETRY_DENIED"
    assert calls == 1


def test_expired_approval_and_all_trace_reads_are_fail_closed():
    async def handler(identity, arguments):
        return {"value": "drafted"}

    spec = make_spec(handler, side_effect="draft", requires_approval=True)
    executor, trace = make_runtime(handler, spec)
    identity = make_identity()
    waiting = asyncio.run(executor.run(make_plan(ToolCall(tool_name=spec.name,
                                                          arguments={"value": "draft"})), identity))
    approval_id = waiting.pending_approval_id
    trace._db.execute("UPDATE agent_approvals SET expires_at='2000-01-01T00:00:00+00:00' WHERE approval_id=?",
                      (approval_id,))
    trace._db.commit()
    assert trace.approvals.expire_stale() == 1
    with pytest.raises(ApprovalError, match="no longer pending"):
        executor.approve(approval_id, make_identity(user_id="admin", roles={"admin"}))
    assert not trace.approvals.consume(approval_id, identity, run_id=waiting.run_id,
                                       call_id=spec.name, plan_hash=trace.get_run_for(waiting.run_id, make_identity())["plan_hash"])
    expired = asyncio.run(executor.run(None, identity, run_id=waiting.run_id))
    assert expired.state == TraceState.FAILED
    assert expired.error_code == "APPROVAL_EXPIRED"

    outsider = make_identity(user_id="outsider")
    with pytest.raises(TraceAccessDenied):
        trace.get_run_for(waiting.run_id, outsider)
    with pytest.raises(TraceAccessDenied):
        trace.list_steps_for(waiting.run_id, outsider)
    with pytest.raises(TraceAccessDenied):
        executor.cancel(waiting.run_id, outsider)
    admin = make_identity(user_id="admin", roles={"admin"})
    assert trace.get_run_for(waiting.run_id, admin)["run_id"] == waiting.run_id
    assert trace.list_runs_for(outsider) == []


def test_trace_redacts_sensitive_keys_caps_fields_and_purges_old_runs():
    async def handler(identity, arguments):
        return {"password": "result-secret", "email": "person@example.invalid", "note": "z" * 600}

    spec = make_spec(
        handler,
        input_schema={"type": "object", "properties": {"value": {"type": "string"}},
                      "required": ["value"], "additionalProperties": False},
        output_schema={"type": "object"},
    )
    trace = TraceStore(redact_email=True, max_field_bytes=256, max_run_bytes=2048, retention_days=1)
    registry = ToolRegistry()
    registry.register(spec, handler)
    executor = BoundedExecutor(registry, PolicyEngine(), trace)
    outcome = asyncio.run(executor.run(make_plan(ToolCall(tool_name=spec.name,
                                                          arguments={"value": "input"})), make_identity()))
    step = trace.list_steps_for(outcome.run_id, make_identity())[0]
    assert step["result"]["password"] == "[REDACTED]"
    assert step["result"]["email"] == "[REDACTED]"
    assert "truncated" in step["result"]["note"]
    trace._db.execute("UPDATE agent_runs SET created_at='2000-01-01T00:00:00+00:00' WHERE run_id=?",
                      (outcome.run_id,))
    trace._db.commit()
    assert trace.purge_expired() == 1
    assert trace.get_run_for(outcome.run_id, make_identity()) is None


def test_trace_caps_total_run_bytes_and_correlates_run_and_steps():
    async def handler(identity, arguments):
        return {"value": "z" * 300}

    trace = TraceStore(max_field_bytes=128, max_run_bytes=300)
    registry = ToolRegistry()
    registry.register(make_spec(handler), handler)
    executor = BoundedExecutor(registry, PolicyEngine(), trace)
    plan = make_plan(ToolCall(tool_name="sample.read", arguments={"value": "x"}))
    outcome = asyncio.run(executor.run(plan, make_identity()))
    public_run = trace.get_run_for(outcome.run_id, make_identity())
    steps = trace.list_steps_for(outcome.run_id, make_identity())
    assert public_run["trace_bytes"] <= 300
    assert public_run["correlation_id"] == outcome.correlation_id
    assert {step["correlation_id"] for step in steps} == {outcome.correlation_id}
    actual_size = trace._db.execute(
        "SELECT SUM(length(CAST(arguments_json AS BLOB))) + "
        "SUM(length(CAST(COALESCE(result_json,'') AS BLOB))) FROM agent_steps WHERE run_id=?",
        (outcome.run_id,),
    ).fetchone()[0]
    assert actual_size <= 300
    assert public_run.get("plan_json") is None


def test_sensitive_plan_fields_are_rejected_before_persistence():
    async def handler(identity, arguments):
        return {"value": "ok"}

    executor, trace = make_runtime(handler)
    plan = make_plan(ToolCall(tool_name="sample.read", arguments={"value": "x", "password": "hidden"}))
    with pytest.raises(ValueError, match="excluded from persisted traces"):
        asyncio.run(executor.run(plan, make_identity()))
    assert trace.list_runs_for(make_identity()) == []


def test_invalid_state_transitions_and_non_json_outputs_fail_closed():
    async def bad_handler(identity, arguments):
        return {"value": object()}

    executor, trace = make_runtime(bad_handler, make_spec(bad_handler, output_schema={"type": "object"}))
    outcome = asyncio.run(executor.run(make_plan(ToolCall(tool_name="sample.read",
                                                          arguments={"value": "x"})), make_identity()))
    assert outcome.error_code == "OUTPUT_NOT_JSON"
    with pytest.raises(InvalidTransition):
        trace.set_run_state(outcome.run_id, TraceState.REQUESTED)
    with pytest.raises(InvalidTransition):
        trace.set_step_state(outcome.run_id, 0, TraceState.RUNNING)


def test_trace_store_migrates_the_first_runtime_schema(tmp_path):
    path = tmp_path / "runtime-legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE agent_runs (
          run_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,workspace_id TEXT NOT NULL,
          plan_hash TEXT NOT NULL,goal TEXT NOT NULL,state TEXT NOT NULL,error_code TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE agent_steps (
          run_id TEXT NOT NULL,step_index INTEGER NOT NULL,call_id TEXT NOT NULL,tool_name TEXT NOT NULL,
          arguments_json TEXT NOT NULL,result_json TEXT,state TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
          error_code TEXT,started_at TEXT,finished_at TEXT,PRIMARY KEY(run_id,step_index),UNIQUE(run_id,call_id)
        );
    """)
    connection.close()

    trace = TraceStore(path)
    run_columns = {row["name"] for row in trace._db.execute("PRAGMA table_info(agent_runs)")}
    step_columns = {row["name"] for row in trace._db.execute("PRAGMA table_info(agent_steps)")}
    tables = {row[0] for row in trace._db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"request_key", "plan_json", "correlation_id", "trace_bytes"} <= run_columns
    assert {"correlation_id", "idempotency_key"} <= step_columns
    assert "agent_approvals" in tables

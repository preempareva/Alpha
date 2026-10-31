"""Typed contracts for the bounded Alpha tool runtime."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

SideEffect = Literal["read", "draft", "write", "external"]
_SCHEMA_KEYS = {
    "type", "properties", "required", "additionalProperties", "items", "enum", "const",
    "minLength", "maxLength", "minItems", "maxItems", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "pattern", "uniqueItems", "minProperties",
    "maxProperties", "title", "description", "anyOf", "oneOf", "allOf",
}


def _check_schema_definition(schema: dict[str, Any], label: str) -> None:
    unsupported = set(schema) - _SCHEMA_KEYS
    if unsupported:
        raise ValueError(f"{label} uses unsupported schema keywords: {', '.join(sorted(unsupported))}")
    schema_type = schema.get("type")
    if schema_type is not None and (not isinstance(schema_type, str) or schema_type not in {
        "object", "array", "string", "integer", "number", "boolean", "null"
    }):
        raise ValueError(f"{label}.type is unsupported")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict) or not all(isinstance(name, str) for name in properties):
        raise ValueError(f"{label}.properties must be an object")
    for name, child in properties.items():
        if not isinstance(child, dict):
            raise ValueError(f"{label}.properties.{name} must be a schema object")
        _check_schema_definition(child, f"{label}.properties.{name}")
    items = schema.get("items")
    if items is not None:
        if not isinstance(items, dict):
            raise ValueError(f"{label}.items must be a schema object")
        _check_schema_definition(items, f"{label}.items")
    additional = schema.get("additionalProperties", True)
    if isinstance(additional, dict):
        _check_schema_definition(additional, f"{label}.additionalProperties")
    elif not isinstance(additional, bool):
        raise ValueError(f"{label}.additionalProperties must be a boolean or schema object")
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(name, str) for name in required):
        raise ValueError(f"{label}.required must be a list of property names")
    for combinator in ("anyOf", "oneOf", "allOf"):
        choices = schema.get(combinator, [])
        if not isinstance(choices, list) or not all(isinstance(choice, dict) for choice in choices):
            raise ValueError(f"{label}.{combinator} must be a list of schema objects")
        for index, choice in enumerate(choices):
            _check_schema_definition(choice, f"{label}.{combinator}[{index}]")
    pattern = schema.get("pattern")
    if pattern is not None:
        try:
            re.compile(pattern)
        except (TypeError, re.error) as exc:
            raise ValueError(f"{label}.pattern must be a valid regular expression") from exc


class TraceState(StrEnum):
    REQUESTED = "requested"
    PLANNED = "planned"
    VALIDATED = "validated"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentIdentity(BaseModel):
    """Identity populated by the server's authenticated session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(min_length=1, max_length=200)
    roles: frozenset[str] = Field(min_length=1)
    workspace_id: str = Field(min_length=1, max_length=200)
    groups: frozenset[str] = Field(default_factory=frozenset)
    active: bool = True


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,79}$")
    description: str = Field(min_length=1, max_length=500)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    module: str = Field(min_length=1, max_length=300)
    allowed_roles: frozenset[str] = Field(min_length=1)
    allowed_workspaces: frozenset[str] | None = None
    side_effect: SideEffect = "read"
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    max_rows: int = Field(default=1000, ge=1, le=10000)
    max_bytes: int = Field(default=100_000, ge=1, le=5_000_000)
    requires_approval: bool = False

    @model_validator(mode="after")
    def require_approval_for_effects(self) -> ToolSpec:
        if self.side_effect in {"write", "external"} and not self.requires_approval:
            raise ValueError("write and external tools must require human approval")
        if self.input_schema.get("type") != "object":
            raise ValueError("tool input_schema must describe an object")
        _check_schema_definition(self.input_schema, "input_schema")
        _check_schema_definition(self.output_schema, "output_schema")
        return self


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=80)
    tool_name: str = Field(min_length=2, max_length=80)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class AgentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=80)
    agent_name: str = Field(min_length=1, max_length=100)
    goal: str = Field(min_length=1, max_length=1000)
    steps: tuple[ToolCall, ...] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def bound_plan_payload(self) -> AgentPlan:
        call_ids = [step.call_id for step in self.steps]
        if len(set(call_ids)) != len(call_ids):
            raise ValueError("tool call IDs must be unique within a plan")
        if len(self.model_dump_json().encode("utf-8")) > 64_000:
            raise ValueError("plan exceeds the 64 KB input limit")
        return self


class RunOutcome(BaseModel):
    run_id: str
    state: str
    results: list[JsonValue] = Field(default_factory=list)
    pending_approval_call_id: str | None = None
    pending_approval_id: str | None = None
    error_code: str | None = None
    correlation_id: str | None = None


class ToolCallContext(BaseModel):
    """Stable execution metadata that lets side-effecting handlers deduplicate work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, max_length=80)
    step_index: int = Field(ge=0, le=4)
    call_id: str = Field(min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=64, max_length=64)
    correlation_id: str = Field(min_length=1, max_length=80)

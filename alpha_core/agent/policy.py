"""Fail-closed checks immediately before each allowlisted tool dispatch."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from .models import AgentIdentity, ToolCall
from .registry import RegisteredTool


class PolicyDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: bool
    reason: str


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _schema_error(value: Any, schema: dict[str, Any], path: str = "$") -> str | None:
    """Validate the bounded JSON Schema subset used by registered Alpha tools."""
    for combinator in ("anyOf", "oneOf", "allOf"):
        choices = schema.get(combinator)
        if choices is None:
            continue
        matches = [choice for choice in choices if _schema_error(value, choice, path) is None]
        if combinator == "anyOf" and not matches:
            return f"{path} does not match any permitted shape"
        if combinator == "oneOf" and len(matches) != 1:
            return f"{path} does not match exactly one permitted shape"
        if combinator == "allOf" and len(matches) != len(choices):
            return f"{path} does not match every required shape"
    expected = schema.get("type")
    if expected is not None and not _matches_type(value, expected):
        return f"{path} must be {expected}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path} is not an allowed value"
    if "const" in schema and value != schema["const"]:
        return f"{path} is not the required constant"

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                return f"{path}.{key} is required"
        properties = schema.get("properties", {})
        if len(value) < schema.get("minProperties", 0) or len(value) > schema.get("maxProperties", 1_000_000):
            return f"{path} has an invalid property count"
        additional = schema.get("additionalProperties", True)
        if additional is False:
            unknown = set(value) - set(properties)
            if unknown:
                return f"{path} contains an unknown property"
        for key, item in value.items():
            item_schema = properties.get(key)
            if item_schema is not None:
                error = _schema_error(item, item_schema, f"{path}.{key}")
                if error:
                    return error
            elif isinstance(additional, dict):
                error = _schema_error(item, additional, f"{path}.{key}")
                if error:
                    return error

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 1_000_000):
            return f"{path} has an invalid item count"
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                error = _schema_error(item, item_schema, f"{path}[{index}]")
                if error:
                    return error
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            return f"{path} contains duplicate items"

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1_000_000):
            return f"{path} has an invalid string length"
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            return f"{path} does not match its required pattern"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            return f"{path} is outside its numeric bounds"
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            return f"{path} is not above its exclusive minimum"
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            return f"{path} is not below its exclusive maximum"
    return None


class PolicyEngine:
    def authorize(
        self,
        tool: RegisteredTool,
        call: ToolCall,
        identity: AgentIdentity,
        *,
        approved: bool = False,
    ) -> PolicyDecision:
        spec = tool.spec
        if not identity.active or not identity.user_id.strip():
            return PolicyDecision(allowed=False, reason="identity_inactive")
        if not identity.roles.intersection(spec.allowed_roles):
            return PolicyDecision(allowed=False, reason="role_denied")
        if spec.allowed_workspaces is not None and identity.workspace_id not in spec.allowed_workspaces:
            return PolicyDecision(allowed=False, reason="workspace_denied")
        if call.tool_name != spec.name:
            return PolicyDecision(allowed=False, reason="tool_not_allowlisted")
        if tool.module != spec.module or tool.handler.__module__ != spec.module:
            return PolicyDecision(allowed=False, reason="module_denied")
        try:
            argument_size = len(json.dumps(call.arguments, separators=(",", ":"), allow_nan=False).encode("utf-8"))
        except (TypeError, ValueError):
            return PolicyDecision(allowed=False, reason="arguments_not_json")
        if argument_size > min(spec.max_bytes, 64_000):
            return PolicyDecision(allowed=False, reason="arguments_too_large")
        error = _schema_error(call.arguments, spec.input_schema)
        if error:
            return PolicyDecision(allowed=False, reason="invalid_arguments")
        approval_required = spec.requires_approval or spec.side_effect in {"write", "external"}
        if approval_required and not approved:
            return PolicyDecision(allowed=False, reason="approval_required")
        return PolicyDecision(allowed=True, reason="allowed")

    def validate_output(self, tool: RegisteredTool, value: Any) -> str | None:
        spec = tool.spec
        error = _schema_error(value, spec.output_schema)
        if error:
            return "invalid_output"
        try:
            encoded = json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError):
            return "output_not_json"
        if len(encoded) > spec.max_bytes:
            return "output_too_large"
        rows = value if isinstance(value, list) else value.get("rows") if isinstance(value, dict) else None
        if rows is not None and (not isinstance(rows, list) or len(rows) > spec.max_rows):
            return "row_limit_exceeded"
        return None

"""Explicit tool allowlist. Tools are registered as callables, never imported from plans."""

from __future__ import annotations

import inspect
import copy
import threading
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import Any

from .models import AgentIdentity, ToolCallContext, ToolSpec

ToolHandler = Callable[..., Awaitable[Any]]


class RegistryError(ValueError):
    """Raised when trusted startup configuration is inconsistent."""


class ToolNotFound(LookupError):
    """Raised when a plan requests a tool outside the allowlist."""


@dataclass(frozen=True)
class RegisteredTool:
    spec: ToolSpec
    handler: ToolHandler
    module: str
    accepts_context: bool = False

    async def invoke(self, identity: AgentIdentity, arguments: dict[str, Any],
                     context: ToolCallContext) -> Any:
        if self.accepts_context:
            return await self.handler(identity, copy.deepcopy(arguments), context=context)
        return await self.handler(identity, copy.deepcopy(arguments))


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self._lock = threading.RLock()

    def register(self, spec: ToolSpec, handler: ToolHandler, *, module: str | None = None) -> None:
        if not inspect.iscoroutinefunction(handler):
            raise RegistryError("tool handlers must be async so timeouts can cancel their work")
        signature = inspect.signature(handler)
        accepts_context = "context" in signature.parameters or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
        )
        snapshot = spec.model_copy(deep=True)
        with self._lock:
            if snapshot.name in self._tools:
                raise RegistryError(f"tool {snapshot.name!r} is already registered")
            self._tools[snapshot.name] = RegisteredTool(
                spec=snapshot,
                handler=handler,
                module=module or handler.__module__,
                accepts_context=accepts_context,
            )

    def get(self, name: str) -> RegisteredTool:
        try:
            registered = self._tools[name]
        except KeyError as exc:
            raise ToolNotFound(name) from exc
        return _snapshot(registered)

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return name in self._tools

    def __iter__(self) -> Iterator[RegisteredTool]:
        with self._lock:
            snapshot = tuple(_snapshot(item) for item in self._tools.values())
        return iter(snapshot)


def _snapshot(tool: RegisteredTool) -> RegisteredTool:
    return RegisteredTool(
        spec=tool.spec.model_copy(deep=True),
        handler=tool.handler,
        module=tool.module,
        accepts_context=tool.accepts_context,
    )


class RetryableToolError(RuntimeError):
    """A tool may raise this only for a transient, safe-to-retry failure."""

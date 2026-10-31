"""Optional local Ollama adapter. Normal project flows must work without it."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMDisabled(RuntimeError):
    """Raised when a caller requests a completion while LLM use is disabled."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    parsed: BaseModel | None = None
    model: str | None = None


class LLMProvider(Protocol):
    def complete(
        self,
        system: str,
        user: str,
        *,
        schema: type[T] | None = None,
        timeout_s: float = 30,
        max_tokens: int = 800,
    ) -> LLMResult: ...


class NoneProvider:
    def complete(self, system: str, user: str, **kwargs: Any) -> LLMResult:
        raise LLMDisabled("LLM_PROVIDER is none; use the deterministic project path.")


class OllamaProvider:
    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")

    def complete(
        self,
        system: str,
        user: str,
        *,
        schema: type[T] | None = None,
        timeout_s: float = 30,
        max_tokens: int = 800,
    ) -> LLMResult:
        options: dict[str, int] = {"num_predict": max_tokens}
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "options": options,
        }
        if schema is not None:
            body["format"] = schema.model_json_schema()
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(f"{self.base_url}/api/chat", json=body)
            response.raise_for_status()
            payload = response.json()
        text = str(payload.get("message", {}).get("content", ""))
        parsed = None
        if schema is not None:
            parsed = schema.model_validate_json(text)
        return LLMResult(text=text, parsed=parsed, model=self.model)


class FakeProvider:
    """Deterministic provider for unit tests; outputs are supplied by the test."""

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)

    def complete(
        self,
        system: str,
        user: str,
        *,
        schema: type[T] | None = None,
        timeout_s: float = 30,
        max_tokens: int = 800,
    ) -> LLMResult:
        del system, user, timeout_s, max_tokens
        if not self.outputs:
            raise RuntimeError("FakeProvider has no remaining canned output.")
        text = self.outputs.pop(0)
        try:
            parsed = schema.model_validate_json(text) if schema else None
        except (ValidationError, json.JSONDecodeError):
            raise
        return LLMResult(text=text, parsed=parsed, model="fake")


def get_provider() -> LLMProvider:
    """Read the provider choice each call so environment overrides remain explicit."""
    choice = os.getenv("LLM_PROVIDER", "none").strip().casefold()
    if choice == "none":
        return NoneProvider()
    if choice == "ollama":
        return OllamaProvider()
    raise ValueError("LLM_PROVIDER must be 'none' or 'ollama'.")

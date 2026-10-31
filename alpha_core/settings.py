"""Small, explicit runtime settings shared by the Alpha shell."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "none"
    ollama_model: str = "llama3.1:8b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        provider = os.getenv("LLM_PROVIDER", "none").strip().casefold()
        if provider not in {"none", "ollama"}:
            raise ValueError("LLM_PROVIDER must be 'none' or 'ollama'.")
        return cls(
            llm_provider=provider,
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )

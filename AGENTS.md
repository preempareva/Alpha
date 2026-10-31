# AGENTS.md: Project Alpha (13 AI/analytics projects)

Drop this file in `project-alpha/` (repo root). Codex reads it every session.

## Hard constraints (never break)

1. **No paid LLM APIs.** No Anthropic/Claude, OpenAI, Gemini or any key-based service. LLM use is optional and goes only through the local adapter below (Ollama; Llama 3.1 8B or Qwen2.5 7B). Do not add `anthropic` or `openai` to any requirements file.
2. **Everything must work with the LLM turned off.** Every project has a deterministic path. LLM is an enhancement behind `LLM_PROVIDER=none|ollama` (default `none`).
3. **No employer data** (Media.net, RP Tech, anyone's), no secrets, no real personal data. Public data only under its licence, or fixtures labelled SYNTHETIC in UI, API, README and model card.
4. **Honest labels.** Do not call something an "agent" unless it picks tools at runtime with bounded steps and approval gates. Rule-based = say rule-based. No invented metrics, savings, or "production-ready" claims.
5. **Never trust the client for identity.** Auth/roles come from the server.
6. Don't rewrite everything at once. One phase, one project at a time, tests green before moving on.

## LLM adapter (the only way models are called)

Create `alpha_core/llm.py`:

```python
class LLMProvider(Protocol):
    def complete(self, system: str, user: str, *, schema: type[BaseModel] | None = None,
                 timeout_s: float = 30, max_tokens: int = 800) -> LLMResult: ...
```

- `NoneProvider`: raises `LLMDisabled`; callers must fall back to the deterministic path.
- `OllamaProvider`: HTTP to `http://127.0.0.1:11434` (`/api/chat`, `format` = JSON schema for structured output). Model from env `OLLAMA_MODEL` (default `llama3.1:8b`). Embeddings via `nomic-embed-text` or `bge-small` (sentence-transformers, CPU).
- Every LLM output is parsed with Pydantic and policy-checked before it touches business logic. On parse failure: retry once, then fall back to deterministic.
- LLM never gets raw SQL access, shell, credentials, or write tools. Tools are an allowlist with input schema, timeout, and side-effect class.
- Tests use a `FakeProvider` with canned outputs. CI never needs Ollama.

## Engineering rules

- Python 3.12. `pyproject.toml` + pinned lockfile. One test command from repo root: `pytest`. Ruff + mypy (or pyright) in CI.
- Unique importable packages. No `sys.path` mutation, no deleting from `sys.modules`. Parent FastAPI app mounts `APIRouter`s.
- FastAPI `lifespan`, not `@app.on_event`.
- Money = `Decimal`. Time-series/temporal data = time-based splits, no future leakage.
- Never commit: `__pycache__`, `.pyc`, `.pytest_cache`, `*.db`, generated data, model binaries (build from scripts; `make seed` / `scripts/seed_all.py`).
- Windows (PowerShell) and Linux must both work. Keep `run.ps1`, add `run.sh`.
- Each project ships: README, data card (`data_register.md` entry), model/agent card, threat model, runbook, 3-min demo script.
- Add tests BEFORE refactoring working behaviour. Report test commands and results at the end of every task.

## Definition of done (per project)

Fresh clone runs from documented commands; sources/licences recorded; baseline + valid split + metrics; negative/adversarial tests; side effects approval-gated; UI shows live vs synthetic; claims match reality.

## Output format at end of each task

Changed files, commands run + results, what's real vs simulated, remaining risks. Then stop and wait.

"""Typed planners that only propose plans; runtime policy remains authoritative."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Protocol

from pydantic import ValidationError

from alpha_core.llm import LLMDisabled, LLMProvider, get_provider

from .models import AgentPlan, ToolCall

PlannerMode = Literal["deterministic", "llm_planned"]


class Planner(Protocol):
    def plan(self, question: str) -> AgentPlan: ...


@dataclass(frozen=True)
class PlanningResult:
    plan: AgentPlan
    mode: PlannerMode


class DeterministicPlanner:
    """Wrap a deterministic intent router that returns a typed call and arguments."""

    def __init__(self, route: Callable[[str], ToolCall], *, agent_name: str = "analyst") -> None:
        self._route = route
        self._agent_name = agent_name

    def plan(self, question: str) -> AgentPlan:
        return self.plan_with_mode(question).plan

    def plan_with_mode(self, question: str) -> PlanningResult:
        call = self._route(question)
        return PlanningResult(
            plan=AgentPlan(agent_name=self._agent_name, goal=question.strip(), steps=(call,)),
            mode="deterministic",
        )


class LLMPlanner:
    """Use the configured local provider to propose a schema-checked plan, then fall back."""

    def __init__(
        self,
        fallback: DeterministicPlanner,
        *,
        provider: LLMProvider | None = None,
        tool_names: tuple[str, ...],
    ) -> None:
        self._fallback = fallback
        self._provider = provider
        self._tool_names = tuple(tool_names)

    def plan(self, question: str) -> AgentPlan:
        return self.plan_with_mode(question).plan

    def plan_with_mode(self, question: str) -> PlanningResult:
        try:
            provider = self._provider or get_provider()
        except Exception:
            return self._fallback.plan_with_mode(question)
        system = (
            "Return a JSON AgentPlan proposing at most four read-only BI tool calls. "
            "Choose only from this catalogue: " + ", ".join(self._tool_names) + ". "
            "Never calculate values, write SQL, request private data, or propose write tools. "
            "The server will validate each tool, argument, identity, and permission."
        )
        correction = ""
        for attempt in range(2):
            try:
                result = provider.complete(
                    system + correction,
                    question[:500],
                    schema=AgentPlan,
                    timeout_s=8,
                    max_tokens=700,
                )
                candidate = result.parsed
                plan = candidate if isinstance(candidate, AgentPlan) else AgentPlan.model_validate_json(result.text)
                return PlanningResult(plan=plan, mode="llm_planned")
            except LLMDisabled:
                break
            except (ValidationError, ValueError, TypeError):
                if attempt == 0:
                    correction = " The previous JSON did not match AgentPlan; return corrected JSON only."
                    continue
                break
            except Exception:
                break
        return self._fallback.plan_with_mode(question)

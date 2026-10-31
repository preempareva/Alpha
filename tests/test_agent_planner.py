from __future__ import annotations

from alpha_core.agent import AgentPlan, DeterministicPlanner, LLMPlanner
from alpha_core.llm import FakeProvider, NoneProvider
from alpha_core.agent.models import ToolCall


def route(question: str) -> ToolCall:
    return ToolCall(tool_name="sample.read", arguments={"question": question})


def test_deterministic_planner_returns_typed_plan():
    result = DeterministicPlanner(route).plan_with_mode("show sample")

    assert result.mode == "deterministic"
    assert result.plan.steps[0].tool_name == "sample.read"
    assert result.plan.steps[0].arguments == {"question": "show sample"}


def test_llm_planner_retries_schema_failure_once_then_uses_valid_plan():
    valid = AgentPlan(
        agent_name="local planner",
        goal="show sample",
        steps=[ToolCall(tool_name="sample.read", arguments={"question": "show sample"})],
    ).model_dump_json()
    provider = FakeProvider(["{invalid", valid])
    planner = LLMPlanner(DeterministicPlanner(route), provider=provider, tool_names=("sample.read",))

    result = planner.plan_with_mode("show sample")

    assert result.mode == "llm_planned"
    assert result.plan.steps[0].tool_name == "sample.read"
    assert provider.outputs == []


def test_llm_disabled_provider_falls_back_to_deterministic():
    planner = LLMPlanner(DeterministicPlanner(route), provider=NoneProvider(), tool_names=("sample.read",))

    result = planner.plan_with_mode("show sample")

    assert result.mode == "deterministic"
    assert result.plan.steps[0].arguments == {"question": "show sample"}

"""Compare saved synthetic evaluation aggregates with reviewed tolerances."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "docs" / "eval"


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing evaluation report: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def require_at_least(failures: list[str], label: str, actual: float, expected: float) -> None:
    if actual < expected:
        failures.append(f"{label}: {actual} is below {expected}")


def require_at_most(failures: list[str], label: str, actual: float, expected: float) -> None:
    if actual > expected:
        failures.append(f"{label}: {actual} is above {expected}")


def check_thresholds() -> list[str]:
    thresholds = read_json(EVAL / "thresholds.json")
    failures: list[str] = []

    knowledge = read_json(
        ROOT / "tools" / "enterprise-knowledge-assistant" / "data" / "evaluation" / "ci_report.json"
    )
    require_at_least(
        failures, "Knowledge case count", knowledge["cases"], thresholds["knowledge"]["min_case_count"]
    )
    for metric, threshold in (
        ("recall_at_5", thresholds["knowledge"]["min_recall_at_5"]),
        ("abstention_accuracy", thresholds["knowledge"]["min_abstention_accuracy"]),
    ):
        require_at_least(failures, f"Knowledge {metric}", knowledge[metric], threshold)
    require_at_most(
        failures, "Knowledge acl_leakage_rate", knowledge["acl_leakage_rate"],
        thresholds["knowledge"]["max_acl_leakage_rate"],
    )
    require_at_most(
        failures, "Knowledge expired_version_leaks", knowledge["expired_version_leaks"],
        thresholds["knowledge"]["max_expired_version_leaks"],
    )

    bi_report = read_json(EVAL / "bi_agent.json")
    bi = bi_report["metrics"]
    if bi_report.get("planner_mode") != "LLM_PROVIDER=none":
        failures.append("BI evaluation was not run with the deterministic provider disabled")
    require_at_least(
        failures, "BI gold case count", bi["gold_case_count"], thresholds["bi"]["min_gold_case_count"]
    )
    for metric, threshold_name in (
        ("tool_selection_accuracy", "min_tool_selection_accuracy"),
        ("argument_accuracy", "min_argument_accuracy"),
        ("numeric_correctness", "min_numeric_correctness"),
        ("refusal_correctness", "min_refusal_correctness"),
        ("verifier_catch_rate", "min_verifier_catch_rate"),
    ):
        require_at_least(failures, f"BI {metric}", bi[metric], thresholds["bi"][threshold_name])
    require_at_least(
        failures, "BI verifier_tamper_trials", bi["verifier_tamper_trials"],
        thresholds["bi"]["min_verifier_tamper_trials"],
    )

    hub_report = read_json(EVAL / "agent_hub.json")
    hub = hub_report["summary"]
    if hub_report.get("llm_provider") != "none":
        failures.append("Hub evaluation was not run with the deterministic provider disabled")
    require_at_least(
        failures, "Hub task count", hub["task_count"], thresholds["hub"]["min_task_count"]
    )
    for metric, threshold_name in (
        ("end_to_end_success", "min_end_to_end_success"),
        ("tool_selection_accuracy", "min_tool_selection_accuracy"),
        ("argument_accuracy", "min_argument_accuracy"),
        ("cross_tool_end_to_end_success", "min_cross_tool_end_to_end_success"),
        ("cross_tool_tool_selection_accuracy", "min_cross_tool_tool_selection_accuracy"),
        ("cross_tool_argument_accuracy", "min_cross_tool_argument_accuracy"),
        ("cross_tool_trace_completeness", "min_cross_tool_trace_completeness"),
        ("correct_refusal_rate", "min_correct_refusal_rate"),
        ("policy_denial_correctness", "min_policy_denial_correctness"),
        ("trace_completeness", "min_trace_completeness"),
    ):
        require_at_least(failures, f"Hub {metric}", hub[metric], thresholds["hub"][threshold_name])
    for metric, threshold_name in (
        ("cross_tool_task_count", "min_cross_tool_task_count"),
        ("cross_tool_minimum_source_tools", "min_cross_tool_source_tools"),
    ):
        require_at_least(failures, f"Hub {metric}", hub[metric], thresholds["hub"][threshold_name])
    tamper = hub["bi_tamper_trials"]
    require_at_least(
        failures, "Hub BI tamper trial count", tamper["trial_count"],
        thresholds["hub"]["min_bi_tamper_trials"],
    )
    if tamper["trial_count"]:
        require_at_least(
            failures, "Hub BI tamper catch rate", tamper["caught_count"] / tamper["trial_count"],
            thresholds["hub"]["min_bi_tamper_catch_rate"],
        )
    else:
        failures.append("Hub BI tamper trials: no trials were recorded")

    copilot = read_json(EVAL / "copilot.json")
    if copilot.get("llm_provider") != "none":
        failures.append("Copilot evaluation was not run with the deterministic provider disabled")
    require_at_least(
        failures, "Copilot question count", copilot["question_count"],
        thresholds["copilot"]["min_question_count"],
    )
    require_at_least(
        failures, "Copilot numeric_correctness", copilot["numeric_correctness"],
        thresholds["copilot"]["min_numeric_correctness"],
    )
    require_at_least(
        failures, "Copilot refusal_correctness", copilot["refusal_correctness"],
        thresholds["copilot"]["min_refusal_correctness"],
    )
    require_at_least(
        failures, "Copilot verifier tamper catch rate", copilot["verifier_tamper_catch_rate"],
        thresholds["copilot"]["min_verifier_tamper_catch_rate"],
    )
    require_at_least(
        failures, "Copilot verifier tamper trials", copilot["verifier_tamper_trials"],
        thresholds["copilot"]["min_verifier_tamper_trials"],
    )

    inventory = read_json(EVAL / "inventory_forecast.json")
    config = thresholds["inventory"]
    if not inventory["data_quality"]["valid"]:
        failures.append("Inventory generated-table validation failed")
    require_at_least(
        failures, "Inventory validated table count", inventory["data_quality"]["tables_checked"],
        config["min_validated_tables"],
    )
    for segment, model in config["required_selected_models"].items():
        actual = inventory["selected_models"].get(segment)
        if actual != model:
            failures.append(f"Inventory selected model {segment}: {actual!r} differs from {model!r}")
    metrics = inventory["backtest_metrics"]
    require_at_least(failures, "Inventory metric group count", len(metrics), config["min_metric_groups"])
    tolerance = config["metric_tolerance"]
    selected = {
        f"{item['segment']}:{item['horizon_weeks']}": item
        for item in metrics if item["model"] == config["required_selected_models"].get(item["segment"])
    }
    for key, baseline in tolerance["selected_model_baselines"].items():
        if key not in selected:
            failures.append(f"Inventory selected metric group missing: {key}")
            continue
        actual = selected[key]
        require_at_most(failures, f"Inventory {key} WAPE", actual["wape"], baseline["wape"] + tolerance["max_wape_increase"])
        require_at_most(failures, f"Inventory {key} MASE", actual["mase"], baseline["mase"] + tolerance["max_mase_increase"])
        require_at_least(
            failures, f"Inventory {key} interval coverage", actual["interval_coverage_10_90"],
            baseline["coverage"] - tolerance["min_coverage_decrease"],
        )

    scenarios = inventory["scenario_tradeoffs"]
    require_at_least(failures, "Inventory scenario count", len(scenarios), config["min_scenario_count"])
    scenario_config = config["scenario_tolerance"]
    indexed = {f"{item['condition']}:{item['policy']}": item for item in scenarios}
    for key, baseline in scenario_config["baselines"].items():
        if key not in indexed:
            failures.append(f"Inventory scenario missing: {key}")
            continue
        actual = indexed[key]
        require_at_least(
            failures, f"Inventory {key} fill rate", actual["fill_rate"],
            baseline["fill_rate"] - scenario_config["min_fill_rate_decrease"],
        )
        require_at_most(
            failures, f"Inventory {key} stockout days", actual["stockout_days"],
            baseline["stockout_days"] + scenario_config["max_stockout_days_increase"],
        )

    return failures


if __name__ == "__main__":
    errors = check_thresholds()
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(1)
    print("All saved evaluation aggregates meet docs/eval/thresholds.json.")

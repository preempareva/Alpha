"""Run the deterministic, fixed-seed Inventory Control Tower evaluation."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any

_data = import_module("tools.inventory-optimization-agent.app.tower_data")
_forecast = import_module("tools.inventory-optimization-agent.app.tower_forecast")
_logic = import_module("tools.inventory-optimization-agent.app.tower_logic")
_generator = import_module("tools.inventory-optimization-agent.scripts.generate_tower_data")
SEED = _generator.SEED

ROOT = Path(__file__).resolve().parents[3]
JSON_OUT = ROOT / "docs" / "eval" / "inventory_forecast.json"
MD_OUT = ROOT / "docs" / "eval" / "inventory_forecast.md"


def _rounded_metrics(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = {"wape", "mase", "bias_units", "interval_coverage_10_90"}
    result = []
    for metric in metrics:
        result.append({key: round(value, 5) if key in fields and isinstance(value, (int, float)) else value
                       for key, value in metric.items()})
    return result


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Inventory Control Tower forecast evaluation",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "SYNTHETIC; fixed-seed generator; no live inventory or supplier data; local deterministic evaluation.",
        "",
        "## Data quality",
        "",
        f"- Validator: **{'passed' if report['data_quality']['valid'] else 'failed'}** across {report['data_quality']['tables_checked']} tables.",
        f"- Synthetic rows: {sum(report['data_quality']['rows_by_table'].values()):,} across six tables.",
        "",
        "## Model selection",
        "",
        f"Selection rule: {report['selection_rule']}.",
        "",
        "| Demand segment | Selected model |",
        "|---|---|",
    ]
    for segment, model in sorted(report["selected_models"].items()):
        lines.append(f"| {segment} | {model} |")
    lines.extend([
        "",
        "The comparison includes naive, seasonal naive, eight-week moving average, statsmodels ETS, and Croston SBA for intermittent demand. The optional LightGBM global challenger is guarded and runs only when the package is installed. The selected model per segment is computed from aggregate WAPE; models within 2% of the best score are tie-broken toward the simplest baseline.",
        "",
        "## Rolling-origin metrics",
        "",
        "Cutoffs are 26, 13, and 6 weeks before the end of the series. Metrics are grouped by segment and horizon; residual bands are recalibrated using training-only rolling moving-average residuals at each cutoff.",
        "",
        "| Segment | Horizon | Model | n | WAPE | MASE | Bias units | 10–90 coverage |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ])
    for metric in report["backtest_metrics"]:
        wape = "n/a" if metric["wape"] is None else f"{metric['wape']:.3f}"
        lines.append(
            f"| {metric['segment']} | {metric['horizon_weeks']} | {metric['model']} | {metric['n']} | "
            f"{wape} | {metric['mase']:.3f} | {metric['bias_units']:.2f} | "
            f"{metric['interval_coverage_10_90']:.3f} |"
        )
    lines.extend([
        "",
        "## Scenario comparison",
        "",
        "The fixed-seed Monte Carlo run compares lean, balanced, and resilient buffers under supplier delay and a demand spike. Values describe one fictional SKU/location scenario only.",
        "",
        "| Condition | Policy | Fill rate | Stockout days | Avg stock | Holding cost | Excess | Expedite cost | Orders |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for item in report["scenario_tradeoffs"]:
        lines.append(
            f"| {item['condition']} | {item['policy']} | {item['fill_rate']:.3f} | "
            f"{item['stockout_days']:.2f} | {item['average_inventory_units']:.2f} | "
            f"${item['holding_cost_estimate']} | {item['excess_units']:.2f} | "
            f"${item['expedite_cost_estimate']} | {item['order_frequency']:.2f} |"
        )
    lines.extend([
        "",
        "## Limits",
        "",
        "This is a hand-authored synthetic panel with a fixed seed. Backtest metrics and interval coverage apply only to its segments, generated assumptions, cutoffs, and horizons. The scenario cost rates are illustrative. They do not establish service-level performance, savings, supplier outcomes, or suitability for live purchasing.",
        "",
        "No observation-level demand, inventory, supplier, or simulation rows are stored in this report.",
        "",
    ])
    return "\n".join(lines)


def evaluate() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="alpha-inventory-eval-") as temporary:
        _generator.generate(Path(temporary), seed=SEED)
        tables = _data.load_tables(Path(temporary))
        quality = _data.validate_tables(tables)
        if not quality["valid"]:
            raise RuntimeError("Generated inventory evaluation data did not pass validation.")
        backtest = _forecast.rolling_origin_backtest(tables.sales_history)
        scenarios = _logic.simulate_scenarios(tables, sku="SKU-001", location="LOC-001",
                                              replications=200, seed=SEED)
    return {
        "evaluation": "inventory-control-tower-forecast-v1",
        "generated_at": datetime.now(UTC).date().isoformat(),
        "mode": "SYNTHETIC",
        "seed": SEED,
        "data_quality": quality,
        "selected_models": backtest["selected_models"],
        "selection_rule": backtest["selection_rule"],
        "cutoff_backsteps_weeks": backtest["cutoff_backsteps_weeks"],
        "horizons_weeks": backtest["horizons_weeks"],
        "optional_lightgbm": backtest["optional_lightgbm"],
        "unavailable_fit_counts": backtest["unavailable_fit_counts"],
        "backtest_metrics": _rounded_metrics(backtest["metrics"]),
        "scenario_tradeoffs": _logic.json_safe(scenarios["tradeoffs"]),
        "limits": [
            "Hand-authored fixed-seed synthetic observations only.",
            "Coverage and error metrics describe only the included panel and holdout schedule.",
            "Scenario costs are illustrative; no operational or savings claims are supported.",
            "No live purchase orders, supplier communications, or external execution occur.",
        ],
    }


def main() -> None:
    report = evaluate()
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                        encoding="utf-8")
    MD_OUT.write_text(_markdown(report), encoding="utf-8")
    print("Wrote SYNTHETIC Inventory Control Tower metrics (no individual rows).")
    print(f"Selected models by segment: {report['selected_models']}")
    print(f"Rolling metric groups: {len(report['backtest_metrics'])}; scenario rows: {len(report['scenario_tradeoffs'])}")


if __name__ == "__main__":
    main()

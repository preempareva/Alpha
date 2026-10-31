from __future__ import annotations

import asyncio
import hashlib
import math
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest
from fastapi.testclient import TestClient

from alpha_core.agent import AgentIdentity, AgentPlan, BoundedExecutor, PolicyEngine
from alpha_core.agent import ToolCall, ToolRegistry, TraceStore

data_module = import_module("tools.inventory-optimization-agent.app.tower_data")
forecast_module = import_module("tools.inventory-optimization-agent.app.tower_forecast")
logic_module = import_module("tools.inventory-optimization-agent.app.tower_logic")
generator_module = import_module("tools.inventory-optimization-agent.scripts.generate_tower_data")
inventory_app_module = import_module("tools.inventory-optimization-agent.app.main")


@pytest.fixture(scope="module", autouse=True)
def load_alpha_shell_after_test_collection() -> None:
    # Import at test runtime so project test modules can configure their isolated
    # database paths before the shell imports and mounts their applications.
    import_module("alpha_app.main")


@pytest.fixture(scope="module")
def tower_data(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, object]:
    root = tmp_path_factory.mktemp("inventory-tower")
    generator_module.generate(root)
    return root, data_module.load_tables(root)


def test_generator_is_fixed_seed_and_validator_accepts_clean_tables(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    generator_module.generate(first, seed=734)
    generator_module.generate(second, seed=734)
    def digests(folder: Path) -> dict[str, str]:
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(folder.glob("*.csv"))}
    assert digests(first) == digests(second)
    assert data_module.validate_tables(data_module.load_tables(first))["valid"] is True


def test_validator_reports_duplicate_key_and_invalid_reference(tower_data) -> None:
    _root, tables = tower_data
    broken = tables.as_mapping()
    broken["sales_history"] = pd.concat(
        [tables.sales_history, tables.sales_history.iloc[[0]]], ignore_index=True
    )
    report = data_module.validate_tables(broken)
    assert report["valid"] is False
    assert "sales_history:duplicate_key" in report["issue_codes"]


def test_atp_and_inventory_position_hand_calculation() -> None:
    assert logic_module.available_to_promise(100, 10, 15) == 75
    position = logic_module.inventory_position(100, 10, 15, 20, 10, 5)
    assert position == {
        "available_to_promise": 75,
        "confirmed_incoming": 30,
        "backorders": 5,
        "inventory_position": 100,
    }


def test_replenishment_formula_decimal_moq_pack_budget_and_max_stock() -> None:
    result = logic_module.replenishment_formula(
        weekly_demand_mean="70", weekly_demand_std="0", service_level="0.95",
        lead_time_days="2", lead_time_std_days="0", review_period_days="1",
        inventory_position_units="20", min_order_qty="5", pack_size="4",
        unit_cost="0.25", max_stock_days="10", budget="2.00",
    )
    assert result["demand_over_lead_plus_review"] == 30
    assert result["safety_stock_units"] == 0
    assert result["reorder_point_units"] == 30
    assert result["suggested_units"] == 8
    assert result["estimated_cost"] == 2
    assert result["reason"] == "draft_quantity_limited_by_budget"

    below_moq_budget = logic_module.replenishment_formula(
        weekly_demand_mean=70, weekly_demand_std=0, service_level=0.95,
        lead_time_days=2, lead_time_std_days=0, review_period_days=1,
        inventory_position_units=20, min_order_qty=6, pack_size=4,
        unit_cost=1, max_stock_days=10, budget=7,
    )
    assert below_moq_budget["suggested_units"] == 0
    assert below_moq_budget["reason"] == "budget_below_supplier_minimum"

    stock_cap = logic_module.replenishment_formula(
        weekly_demand_mean=70, weekly_demand_std=0, service_level=0.95,
        lead_time_days=2, lead_time_std_days=0, review_period_days=1,
        inventory_position_units=20, min_order_qty=5, pack_size=4,
        unit_cost=1, max_stock_days=2,
    )
    assert stock_cap["suggested_units"] == 0
    assert stock_cap["reason"] == "max_stock_cap_below_supplier_minimum"


def test_safety_stock_combines_demand_and_lead_time_variance() -> None:
    weekly_std = 7 * math.sqrt(7)
    result = logic_module.replenishment_formula(
        weekly_demand_mean=70, weekly_demand_std=weekly_std, service_level=0.95,
        lead_time_days=2, lead_time_std_days=2, review_period_days=1,
        inventory_position_units=0, min_order_qty=1, pack_size=1,
        unit_cost="1.20", max_stock_days=100,
    )
    expected = 1.6448536270 * math.sqrt(3 * 7**2 + 10**2 * 2**2)
    assert float(result["safety_stock_units"]) == pytest.approx(expected, abs=0.01)


@pytest.mark.parametrize(
    ("available", "weekly", "expected", "status"),
    [(-3, 14, 0, "stockout_or_negative_stock"), (10, 0, None, "no_positive_demand")],
)
def test_cover_zero_demand_and_negative_stock(available, weekly, expected, status) -> None:
    cover = logic_module.days_of_cover(available, weekly)
    assert cover["days"] == expected
    assert cover["status"] == status


def test_negative_inventory_remains_visible_and_reorders(tower_data) -> None:
    _root, tables = tower_data
    snapshot = tables.inventory_snapshot.copy()
    snapshot.loc[0, ["on_hand", "reserved", "blocked", "in_transit", "backorders"]] = [1, 2, 1, 0, 2]
    row = snapshot.iloc[0]
    orders = tables.purchase_orders.copy()
    orders.loc[(orders.sku == row.sku) & (orders.location == row.location), "status"] = "cancelled"
    modified = replace(tables, inventory_snapshot=snapshot, purchase_orders=orders)
    report = logic_module.inventory_position_report(modified, str(row.sku), str(row.location))
    assert report["available_to_promise"] == -2
    assert report["inventory_position"] <= -2
    assert report["days_of_cover"] == 0


def test_seasonal_naive_and_croston_sba_boundaries() -> None:
    values = np.arange(1, 53, dtype=float)
    assert forecast_module.forecast_points("seasonal_naive", values, 3).tolist() == [1, 2, 3]
    assert forecast_module.croston_sba(np.zeros(20), 4).tolist() == [0, 0, 0, 0]
    intermittent = forecast_module.croston_sba(np.array([0, 0, 8, 0, 0, 0, 6], dtype=float), 2)
    assert intermittent.shape == (2,)
    assert all(value >= 0 for value in intermittent)


def test_forecast_interval_is_ordered_and_uses_only_training_values(tower_data) -> None:
    _root, tables = tower_data
    series = tables.sales_history.loc[
        (tables.sales_history.sku == "SKU-001")
        & (tables.sales_history.location == "LOC-001")
    ].sort_values("date")
    cutoff = pd.to_datetime(series.date, utc=True).iloc[79]
    train = series.loc[pd.to_datetime(series.date, utc=True) <= cutoff]
    forecast = forecast_module.forecast_series(train, "SKU-001", "LOC-001", 6, "moving_average")
    assert len(forecast["forecast"]) == 6
    assert all(row["p10"] <= row["p50"] <= row["p90"] for row in forecast["forecast"])


def test_global_challenger_features_exclude_rows_after_cutoff(tower_data) -> None:
    _root, tables = tower_data
    panel = tables.sales_history.copy()
    cutoff = pd.to_datetime(panel.date, utc=True).sort_values().unique()[70]
    before = forecast_module._lightgbm_frame(panel, pd.Timestamp(cutoff))
    future = pd.to_datetime(panel.date, utc=True) > cutoff
    panel.loc[future, "units"] = 999_999
    after = forecast_module._lightgbm_frame(panel, pd.Timestamp(cutoff))
    pdt.assert_frame_equal(before, after)


def test_rolling_origin_metrics_include_intervals_by_segment_and_horizon(tower_data) -> None:
    _root, tables = tower_data
    selected = tables.sales_history.loc[
        ((tables.sales_history.sku == "SKU-001") & (tables.sales_history.location == "LOC-001"))
        | ((tables.sales_history.sku == "SKU-006") & (tables.sales_history.location == "LOC-001"))
    ]
    result = forecast_module.rolling_origin_backtest(selected)
    assert result["cutoff_backsteps_weeks"] == [26, 13, 6]
    assert result["selected_models"].keys() >= {"seasonal", "intermittent"}
    assert {item["horizon_weeks"] for item in result["metrics"]} >= {1, 2, 4, 6}
    assert all({"wape", "mase", "bias_units", "interval_coverage_10_90"} <= item.keys()
               for item in result["metrics"])
    assert all(0 <= item["interval_coverage_10_90"] <= 1 for item in result["metrics"])


def test_risk_transfer_and_scenario_outputs_are_bounded_and_reproducible(tower_data) -> None:
    _root, tables = tower_data
    risks = logic_module.risk_ranking(tables, horizon_weeks=6, limit=10)
    assert risks["count"] == 72
    assert len(risks["rows"]) == 10
    assert risks["rows"] == sorted(risks["rows"], key=lambda row: (
        -row["risk_score"], float(row["days_of_cover"]) if row["days_of_cover"] is not None else float("inf"),
        row["sku"], row["location"],
    ))

    transfers = logic_module.propose_transfers(tables, limit=30)
    assert all(row["eligible"] and row["quantity"] <= row["source_surplus"]
               and row["quantity"] <= row["destination_need"] for row in transfers["rows"])
    assert all(row["route_days"] > 0 for row in transfers["rows"])

    first = logic_module.simulate_scenarios(tables, replications=30, seed=84)
    second = logic_module.simulate_scenarios(tables, replications=30, seed=84)
    assert first == second
    assert len(first["tradeoffs"]) == 6
    assert {row["condition"] for row in first["tradeoffs"]} == {"supplier_delay", "demand_spike"}
    assert all({"fill_rate", "stockout_days", "average_inventory_units", "holding_cost_estimate",
                "excess_units", "expedite_cost_estimate", "order_frequency"} <= row.keys()
               for row in first["tradeoffs"])


def test_position_reports_weeks_of_cover_po_details_and_policy_excess(tower_data) -> None:
    _root, tables = tower_data
    snapshot = tables.inventory_snapshot.copy()
    snapshot.loc[0, ["on_hand", "reserved", "blocked", "in_transit", "backorders"]] = [10000, 0, 0, 0, 0]
    modified = replace(tables, inventory_snapshot=snapshot)
    row = snapshot.iloc[0]
    report = logic_module.inventory_position_report(modified, str(row.sku), str(row.location))
    assert report["weeks_of_cover"] == report["days_of_cover"] / 7
    assert isinstance(report["purchase_orders"], list)
    assert report["purchase_orders"]
    risks = logic_module.risk_ranking(modified, horizon_weeks=6, limit=72)
    assert risks["excess_count"] > 0
    match = next(item for item in risks["excess_rows"]
                 if item["sku"] == row.sku and item["location"] == row.location)
    assert match["risk_level"] == "EXCESS"
    assert match["excess_units"] > 0


def test_proposal_store_is_owner_scoped_and_simulation_idempotent(tmp_path: Path) -> None:
    store = logic_module.ProposalStore(tmp_path / "proposal-store.sqlite3")
    owner = SimpleNamespace(user_id="user-a", workspace_id="workspace-a")
    other = SimpleNamespace(user_id="user-b", workspace_id="workspace-a")
    saved = store.create(owner, "same-action-key", {"sku": "SKU-001", "suggested_units": 12})
    replay = store.create(owner, "same-action-key", {"sku": "SKU-001", "suggested_units": 99})
    assert replay["proposal_id"] == saved["proposal_id"]
    assert len(store.list_for(owner)) == 1
    assert store.list_for(other) == []
    with pytest.raises(KeyError):
        store.simulate(other, saved["proposal_id"], "foreign-action")
    first = store.simulate(owner, saved["proposal_id"], "simulate-key-a")
    replayed = store.simulate(owner, saved["proposal_id"], "simulate-key-b")
    assert first == replayed
    assert first["status"] == "SIMULATED_ONLY"
    assert first["real_purchase_order_created"] is False


def test_hub_draft_and_simulation_tools_require_persisted_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tower_data,
) -> None:
    root, _tables = tower_data
    monkeypatch.setenv("INVENTORY_TOWER_DATA_ROOT", str(root))
    monkeypatch.setenv("INVENTORY_TOWER_STATE_PATH", str(tmp_path / "tower-state.sqlite3"))
    hub = import_module("alpha_app.agent_hub")
    requester = AgentIdentity(user_id="analyst-1", roles=frozenset({"employee"}),
                              workspace_id="workspace-test")
    approver = AgentIdentity(user_id="admin-1", roles=frozenset({"admin"}),
                             workspace_id="workspace-test")
    registry = ToolRegistry()
    for name in ("inventory.propose_replenishment", "inventory.simulate_execution", "hub.verify_results"):
        registered = hub.REGISTRY.get(name)
        registry.register(registered.spec, registered.handler, module=registered.module)

    trace = TraceStore(tmp_path / "trace.sqlite3")
    executor = BoundedExecutor(registry, PolicyEngine(), trace)
    proposal_call = ToolCall(tool_name="inventory.propose_replenishment",
                              arguments={"sku": "SKU-001", "location": "LOC-001"})
    verify_proposal = ToolCall(tool_name="hub.verify_results",
                               arguments={"source_call_ids": [proposal_call.call_id]})
    proposal_plan = AgentPlan(agent_name="inventory test", goal="persist an approved draft",
                              steps=(proposal_call, verify_proposal))
    pending = asyncio.run(executor.run(proposal_plan, requester, idempotency_key="proposal-test"))
    assert pending.state == "waiting_approval"
    assert not logic_module.ProposalStore().list_for(requester)
    executor.approve(pending.pending_approval_id, approver, reason="test approval")
    completed = asyncio.run(executor.run(None, requester, run_id=pending.run_id))
    assert completed.state == "completed"
    assert completed.results[-1]["data"]["verified"] is True
    proposal = logic_module.ProposalStore().list_for(requester)[0]
    assert proposal["status"] == "draft"
    assert proposal["approval_status"] == "APPROVED_FOR_DRAFT_ONLY"

    simulation_call = ToolCall(tool_name="inventory.simulate_execution",
                               arguments={"proposal_id": proposal["proposal_id"]})
    verify_simulation = ToolCall(tool_name="hub.verify_results",
                                 arguments={"source_call_ids": [simulation_call.call_id]})
    simulation_plan = AgentPlan(agent_name="inventory test", goal="simulate an approved draft",
                                steps=(simulation_call, verify_simulation))
    simulation_pending = asyncio.run(executor.run(
        simulation_plan, requester, idempotency_key="simulation-test"
    ))
    assert simulation_pending.state == "waiting_approval"
    assert logic_module.ProposalStore().get(requester, proposal["proposal_id"])["simulation"] is None
    executor.approve(simulation_pending.pending_approval_id, approver, reason="test simulation approval")
    simulation_done = asyncio.run(executor.run(None, requester, run_id=simulation_pending.run_id))
    assert simulation_done.state == "completed"
    saved = logic_module.ProposalStore().get(requester, proposal["proposal_id"])
    assert saved["status"] == "simulated"
    assert saved["simulation"]["real_purchase_order_created"] is False


def test_hub_inventory_demo_uses_three_independent_tools_and_drafts_stay_gated() -> None:
    hub = import_module("alpha_app.agent_hub")
    plan = hub.plan_hub("Which SKUs are at risk over the next 6 weeks, why, and what should I review first?").plan
    names = [call.tool_name for call in plan.steps]
    assert names.count("inventory.risk_ranking") == 1
    assert names.count("inventory.position") == 1
    assert names.count("inventory.forecast") == 1
    assert names[-1] == "hub.verify_results"
    assert {hub.REGISTRY.get(name).spec.side_effect for name in names[:-1]} == {"read"}

    draft_plan = hub.plan_hub("Draft a replenishment proposal for SKU-001 at LOC-001").plan
    assert [call.tool_name for call in draft_plan.steps] == [
        "inventory.propose_replenishment", "hub.verify_results",
    ]
    assert hub.REGISTRY.get("inventory.propose_replenishment").spec.requires_approval is True
    simulation_plan = hub.plan_hub(
        "Simulate execution of replenishment proposal 9c388a5e-b551-4abc-915d-94162ef2bf66"
    ).plan
    assert simulation_plan.steps[0].tool_name == "inventory.simulate_execution"
    assert hub.REGISTRY.get("inventory.simulate_execution").spec.requires_approval is True


def test_existing_inventory_routes_and_new_workflow_screen_remain_available(
    tower_data, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, tables = tower_data
    monkeypatch.setenv("INVENTORY_TOWER_DATA_ROOT", str(root))
    history = tables.sales_history.loc[
        (tables.sales_history.sku == "SKU-001")
        & (tables.sales_history.location == "LOC-001"), ["date", "sku", "units"]
    ].rename(columns={"date": "week"})
    monkeypatch.setattr(inventory_app_module, "history", lambda: history)
    client = TestClient(inventory_app_module.app)
    page = client.get("/")
    assert page.status_code == 200
    assert "Inventory Control Tower" in page.text
    assert 'id="stock-breakdown"' in page.text and 'id="purchase-orders"' in page.text
    assert 'id="budget"' in page.text and 'id="excess-table"' in page.text
    assert client.get("/api/backtest?sku=SKU-001").status_code == 200
    legacy = client.post("/api/recommend", json={
        "sku": "SKU-001", "lead_time_weeks": 4, "on_hand": 30, "incoming": 0,
        "policy": "balanced",
    })
    assert legacy.status_code == 200
    assert legacy.json()["status"] == "NEEDS_APPROVAL"
    assert client.get("/api/tower/quality").json()["valid"] is True


def test_alpha_shell_mounts_tower_screen_and_keeps_both_inventory_slugs() -> None:
    shell_module = import_module("alpha_app.main")
    projects = {item[0]: item for item in shell_module.PROJECTS}
    assert projects["demand"][1] == "intelligent-inventory-forecasting"
    assert projects["replenishment"][1] == "inventory-optimization-agent"
    assert projects["replenishment"][2] == "Inventory Control Tower"
    client = TestClient(shell_module.app)
    page = client.get("/tools/replenishment/")
    assert page.status_code == 200
    assert 'src="/static/inventory.js"' in page.text
    assert 'data-api-base="/tools/replenishment"' in page.text
    assert client.get("/static/inventory.js").status_code == 200
    assert client.get("/static/inventory.css").status_code == 200

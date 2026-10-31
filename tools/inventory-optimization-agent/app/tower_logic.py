"""Deterministic inventory math, bounded scenarios, and approval-created drafts."""

from __future__ import annotations

from contextlib import contextmanager
import json
import math
import os
import sqlite3
import threading
from datetime import UTC, datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path
from collections.abc import Iterator
from statistics import NormalDist
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from .tower_data import InventoryTables
from .tower_forecast import demand_segment, forecast_points, preferred_model

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_PATH = ROOT / "data" / "runtime" / "inventory-control-tower.sqlite3"
_STORE_LOCK = threading.RLock()
MONEY_QUANTUM = Decimal("0.01")
Z_BY_SERVICE_LEVEL = {"0.90": Decimal("1.2815515655"), "0.95": Decimal("1.6448536270"),
                      "0.98": Decimal("2.0537489106")}


def dec(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError("A numeric inventory input is invalid.") from exc
    if not result.is_finite():
        raise ValueError("A numeric inventory input is not finite.")
    return result


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def available_to_promise(on_hand: Any, reserved: Any, blocked: Any) -> Decimal:
    """ATP = on-hand minus reserved and blocked units; blocked stock is never sellable."""
    return dec(on_hand) - dec(reserved) - dec(blocked)


def inventory_position(
    on_hand: Any, reserved: Any, blocked: Any, in_transit: Any, confirmed_incoming: Any,
    backorders: Any,
) -> dict[str, Decimal]:
    atp = available_to_promise(on_hand, reserved, blocked)
    incoming = dec(in_transit) + dec(confirmed_incoming)
    backorder_units = dec(backorders)
    return {"available_to_promise": atp, "confirmed_incoming": incoming,
            "backorders": backorder_units, "inventory_position": atp + incoming - backorder_units}


def demand_statistics(weekly_units: np.ndarray) -> tuple[Decimal, Decimal]:
    values = np.maximum(np.asarray(weekly_units, dtype=float), 0.0)
    if values.size == 0:
        raise ValueError("Demand history is empty.")
    mean_daily = Decimal(str(float(values.mean()) / 7.0))
    weekly_std = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
    std_daily = Decimal(str(weekly_std / math.sqrt(7.0)))
    return mean_daily, std_daily


def days_of_cover(available: Any, mean_weekly_demand: Any) -> dict[str, Any]:
    stock = dec(available)
    demand = dec(mean_weekly_demand) / Decimal(7)
    if stock <= 0:
        return {"days": Decimal("0"), "status": "stockout_or_negative_stock"}
    if demand <= 0:
        return {"days": None, "status": "no_positive_demand"}
    return {"days": stock / demand, "status": "covered"}


def _round_up_pack(quantity: Decimal, pack_size: int) -> int:
    if pack_size < 1:
        raise ValueError("Supplier pack size must be a positive integer.")
    return int((quantity / Decimal(pack_size)).to_integral_value(rounding=ROUND_CEILING)) * pack_size


def _round_down_pack(quantity: Decimal, pack_size: int) -> int:
    if pack_size < 1:
        raise ValueError("Supplier pack size must be a positive integer.")
    return int((quantity / Decimal(pack_size)).to_integral_value(rounding=ROUND_FLOOR)) * pack_size


def replenishment_formula(
    *, weekly_demand_mean: Any, weekly_demand_std: Any, service_level: Any,
    lead_time_days: Any, lead_time_std_days: Any, review_period_days: Any,
    inventory_position_units: Any, min_order_qty: Any, pack_size: Any, unit_cost: Any,
    max_stock_days: Any, budget: Any | None = None,
) -> dict[str, Any]:
    """Return an explainable, constrained draft quantity using Decimal for quantities/money."""
    mean_daily = dec(weekly_demand_mean) / Decimal(7)
    demand_std_daily = dec(weekly_demand_std) / Decimal(str(math.sqrt(7.0)))
    service = dec(service_level).quantize(Decimal("0.01"))
    z = Z_BY_SERVICE_LEVEL.get(str(service))
    if z is None:
        z = Decimal(str(NormalDist().inv_cdf(float(service))))
    lead = dec(lead_time_days)
    lead_std = dec(lead_time_std_days)
    review = dec(review_period_days)
    horizon = lead + review
    if min(lead, lead_std, review, mean_daily, demand_std_daily) < 0:
        raise ValueError("Lead time, review period, and demand inputs must be non-negative.")
    if not Decimal("0.5") <= service < Decimal("1"):
        raise ValueError("Service level must be at least 0.5 and below 1.")
    if horizon <= 0:
        raise ValueError("The lead-time plus review horizon must be positive.")
    variance = horizon * demand_std_daily**2 + mean_daily**2 * lead_std**2
    safety_stock = z * Decimal(str(math.sqrt(max(0.0, float(variance)))))
    lead_review_demand = mean_daily * horizon
    reorder_point = lead_review_demand + safety_stock
    position = dec(inventory_position_units)
    raw_need = max(Decimal(0), reorder_point - position)
    max_stock_units = mean_daily * dec(max_stock_days)
    capacity = max(Decimal(0), max_stock_units - position)
    moq = int(dec(min_order_qty))
    pack = int(dec(pack_size))
    price = money(dec(unit_cost))
    if moq < 0 or pack < 1 or price < 0:
        raise ValueError("MOQ, pack size, and unit cost are invalid.")

    reason = "reorder_point_not_reached"
    quantity = 0
    if raw_need > 0:
        max_by_stock = _round_down_pack(capacity, pack)
        requested = max(moq, _round_up_pack(raw_need, pack))
        quantity = min(requested, max_by_stock)
        reason = "draft_quantity_limited_by_max_stock" if quantity < requested else "draft_quantity_ready"
        if quantity < moq:
            quantity = 0
            reason = "max_stock_cap_below_supplier_minimum"
        if budget is not None and quantity > 0:
            budget_amount = money(dec(budget))
            if budget_amount < 0:
                raise ValueError("Budget cannot be negative.")
            max_by_budget = _round_down_pack(budget_amount / price, pack) if price > 0 else quantity
            budget_quantity = min(quantity, max_by_budget)
            if budget_quantity < moq:
                quantity = 0
                reason = "budget_below_supplier_minimum"
            else:
                quantity = budget_quantity
                if quantity < requested:
                    reason = "draft_quantity_limited_by_budget"
    total_cost = money(price * quantity)
    return {
        "mean_demand_per_day": mean_daily,
        "demand_std_per_day": demand_std_daily,
        "z_service_level": z,
        "demand_over_lead_plus_review": lead_review_demand,
        "safety_stock_units": safety_stock,
        "reorder_point_units": reorder_point,
        "inventory_position_units": position,
        "raw_need_units": raw_need,
        "suggested_units": quantity,
        "unit_cost": price,
        "estimated_cost": total_cost,
        "reason": reason,
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


def json_safe(value: Any) -> Any:
    """Convert Decimal and pandas/numpy values to bounded standard JSON values."""
    return json.loads(json.dumps(value, default=_json_default, allow_nan=False))


class ProposalStore:
    """Small identity-scoped local store for drafts and simulated execution records."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(os.getenv("INVENTORY_TOWER_STATE_PATH", str(DEFAULT_STATE_PATH)))

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("""CREATE TABLE IF NOT EXISTS inventory_proposals (
            proposal_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('draft','simulated')),
            payload_json TEXT NOT NULL,
            simulation_json TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(workspace_id,user_id,idempotency_key)
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_inventory_proposals_owner "
                   "ON inventory_proposals(workspace_id,user_id,created_at DESC)")
        return db

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            yield db
        except Exception:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def create(self, identity: Any, idempotency_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        proposal_id = str(uuid4())
        created_at = datetime.now(UTC).isoformat()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
        with _STORE_LOCK, self._connection() as db:
            db.execute("INSERT OR IGNORE INTO inventory_proposals "
                       "(proposal_id,user_id,workspace_id,idempotency_key,status,payload_json,created_at) "
                       "VALUES (?,?,?,?,?,?,?)", (proposal_id, identity.user_id, identity.workspace_id,
                       idempotency_key, "draft", encoded, created_at))
            row = db.execute("SELECT * FROM inventory_proposals WHERE workspace_id=? AND user_id=? "
                             "AND idempotency_key=?", (identity.workspace_id, identity.user_id,
                             idempotency_key)).fetchone()
        if row is None:
            raise RuntimeError("The replenishment draft could not be saved.")
        return self._row(row)

    def list_for(self, identity: Any, limit: int = 50) -> list[dict[str, Any]]:
        with _STORE_LOCK, self._connection() as db:
            rows = db.execute("SELECT * FROM inventory_proposals WHERE workspace_id=? AND user_id=? "
                               "ORDER BY created_at DESC LIMIT ?",
                               (identity.workspace_id, identity.user_id, limit)).fetchall()
        return [self._row(row) for row in rows]

    def get(self, identity: Any, proposal_id: str) -> dict[str, Any] | None:
        with _STORE_LOCK, self._connection() as db:
            row = db.execute("SELECT * FROM inventory_proposals WHERE workspace_id=? AND user_id=? "
                             "AND proposal_id=?", (identity.workspace_id, identity.user_id,
                             proposal_id)).fetchone()
        return self._row(row) if row else None

    def simulate(self, identity: Any, proposal_id: str, idempotency_key: str) -> dict[str, Any]:
        with _STORE_LOCK, self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM inventory_proposals WHERE workspace_id=? AND user_id=? "
                             "AND proposal_id=?", (identity.workspace_id, identity.user_id,
                             proposal_id)).fetchone()
            if row is None:
                db.rollback()
                raise KeyError("Draft proposal not found in this account.")
            existing = row["simulation_json"]
            if existing:
                result = json.loads(existing)
                db.commit()
                return result
            payload = json.loads(row["payload_json"])
            simulation = {
                "proposal_id": proposal_id, "simulation_id": str(uuid4()),
                "idempotency_key": idempotency_key, "status": "SIMULATED_ONLY",
                "proposed_units": int(payload["suggested_units"]),
                "simulated_units": int(payload["suggested_units"]),
                "real_purchase_order_created": False,
                "notice": "This is an isolated simulation record; no supplier or external system was contacted.",
                "created_at": datetime.now(UTC).isoformat(),
            }
            db.execute("UPDATE inventory_proposals SET status='simulated',simulation_json=? "
                       "WHERE proposal_id=?", (json.dumps(simulation, sort_keys=True), proposal_id))
            db.commit()
        return simulation

    def _row(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload_json"])
        simulation = json.loads(row["simulation_json"]) if row["simulation_json"] else None
        return {**payload, "proposal_id": row["proposal_id"], "status": row["status"],
                "created_at": row["created_at"], "simulation": simulation}


def _record(frame: pd.DataFrame, key_column: str, key: str) -> pd.Series:
    subset = frame.loc[frame[key_column].astype(str) == str(key)]
    if subset.empty:
        raise ValueError("Requested synthetic inventory record was not found.")
    return subset.iloc[0]


def _inventory_inputs(tables: InventoryTables, sku: str, location: str) -> dict[str, Any]:
    snapshots = tables.inventory_snapshot.loc[
        (tables.inventory_snapshot["sku"].astype(str) == sku)
        & (tables.inventory_snapshot["location"].astype(str) == location)
    ]
    policies = tables.sku_policy.loc[
        (tables.sku_policy["sku"].astype(str) == sku)
        & (tables.sku_policy["location"].astype(str) == location)
    ]
    history = tables.sales_history.loc[
        (tables.sales_history["sku"].astype(str) == sku)
        & (tables.sales_history["location"].astype(str) == location)
    ].sort_values("date")
    if snapshots.empty or policies.empty or len(history) < 20:
        raise ValueError("The selected SKU and location do not have a complete synthetic profile.")
    snapshot, policy = snapshots.iloc[0], policies.iloc[0]
    all_purchase_orders = tables.purchase_orders.loc[
        (tables.purchase_orders["sku"].astype(str) == sku)
        & (tables.purchase_orders["location"].astype(str) == location)
    ]
    purchase_orders = all_purchase_orders.loc[
        all_purchase_orders["status"].astype(str).str.casefold().isin({"confirmed", "open"})
    ]
    confirmed_qty = Decimal(0)
    snapshot_time = pd.to_datetime(snapshot["snapshot_time"], utc=True)
    incoming_pipeline: list[tuple[int, int]] = []
    if not purchase_orders.empty:
        expected = pd.to_datetime(purchase_orders["expected_date"], utc=True)
        eligible_orders = purchase_orders.loc[expected >= snapshot_time]
        confirmed_qty = sum((dec(value) for value in eligible_orders["open_qty"].tolist()), Decimal(0))
        for order in eligible_orders.itertuples(index=False):
            eta = pd.to_datetime(order.expected_date, utc=True)
            days_to_eta = max(0, int((eta - snapshot_time).days))
            incoming_pipeline.append((days_to_eta, int(order.open_qty)))
    in_transit_qty = int(snapshot["in_transit"])
    if in_transit_qty > 0:
        route_rows = tables.transfers.loc[
            (tables.transfers["sku"].astype(str) == sku)
            & (tables.transfers["destination_location"].astype(str) == location)
            & (tables.transfers["status"].astype(str).str.casefold() == "in_transit")
        ]
        if route_rows.empty:
            transit_days = 5
        else:
            transit_days = max(0, int((pd.to_datetime(route_rows["eta"], utc=True)
                                      - snapshot_time).dt.days.median()))
        incoming_pipeline.append((transit_days, in_transit_qty))
    sku_pos = tables.purchase_orders.loc[tables.purchase_orders["sku"].astype(str) == sku]
    supplier_id = str(sku_pos.iloc[0]["supplier_id"]) if not sku_pos.empty else str(tables.supplier.iloc[0]["supplier_id"])
    supplier = _record(tables.supplier, "supplier_id", supplier_id)
    stock = inventory_position(
        snapshot["on_hand"], snapshot["reserved"], snapshot["blocked"], snapshot["in_transit"],
        confirmed_qty, snapshot["backorders"],
    )
    values = np.maximum(history["units"].to_numpy(dtype=float), 0.0)
    segment = demand_segment(values)
    model = preferred_model(values)
    weekly_forecast = forecast_points(model, values, 6)
    weekly_mean = Decimal(str(float(np.mean(weekly_forecast))))
    weekly_std = Decimal(str(float(np.std(values, ddof=1)))) if values.size > 1 else Decimal(0)
    po_details = [
        {"po_id": str(order.po_id), "supplier_id": str(order.supplier_id),
         "expected_date": pd.to_datetime(order.expected_date, utc=True).date().isoformat(),
         "open_qty": int(order.open_qty), "status": str(order.status)}
        for order in all_purchase_orders.sort_values("expected_date").itertuples(index=False)
    ][:10]
    return {
        "snapshot": snapshot, "policy": policy, "supplier": supplier,
        "stock": stock, "history": history, "segment": segment, "model": model,
        "weekly_forecast": weekly_forecast, "weekly_mean": weekly_mean,
        "weekly_std": weekly_std, "incoming_pipeline": incoming_pipeline,
        "purchase_orders": po_details,
    }


def inventory_position_report(tables: InventoryTables, sku: str, location: str) -> dict[str, Any]:
    inputs = _inventory_inputs(tables, sku, location)
    snapshot, policy, supplier = inputs["snapshot"], inputs["policy"], inputs["supplier"]
    stock = inputs["stock"]
    cover = days_of_cover(stock["available_to_promise"], inputs["weekly_mean"])
    days = cover["days"]
    weeks = None if days is None else days / Decimal(7)
    return {
        "sku": sku, "location": location, "label": "SYNTHETIC",
        "on_hand": int(snapshot["on_hand"]), "reserved": int(snapshot["reserved"]),
        "blocked": int(snapshot["blocked"]), "available_to_promise": stock["available_to_promise"],
        "confirmed_incoming": stock["confirmed_incoming"], "backorders": stock["backorders"],
        "inventory_position": stock["inventory_position"],
        "lead_time_days": int(supplier["lead_time_days"]),
        "lead_time_std_days": int(supplier["lead_time_std"]),
        "review_period_days": int(policy["review_period_days"]),
        "max_stock_days": int(policy["max_stock_days"]),
        "service_level": float(policy["service_level"]),
        "supplier_id": str(supplier["supplier_id"]), "supplier_reliability": float(supplier["reliability"]),
        "unit_cost": money(dec(supplier["unit_cost"])),
        "weekly_demand_mean": inputs["weekly_mean"], "days_of_cover": cover["days"],
        "weeks_of_cover": weeks, "purchase_orders": inputs["purchase_orders"],
        "cover_status": cover["status"], "forecast_model": inputs["model"],
    }


def risk_ranking(tables: InventoryTables, horizon_weeks: int = 6, limit: int = 20) -> dict[str, Any]:
    if not 1 <= horizon_weeks <= 26 or not 1 <= limit <= 100:
        raise ValueError("Risk horizon or result limit is outside the allowed range.")
    rows: list[dict[str, Any]] = []
    for row in tables.sku_policy.itertuples(index=False):
        sku, location = str(row.sku), str(row.location)
        report = inventory_position_report(tables, sku, location)
        mean_daily = dec(report["weekly_demand_mean"]) / Decimal(7)
        horizon_demand = mean_daily * Decimal(horizon_weeks * 7)
        stock = dec(report["inventory_position"])
        excess_units = max(Decimal(0), stock - mean_daily * Decimal(report["max_stock_days"]))
        cover = report["days_of_cover"]
        lead_days = int(report["lead_time_days"])
        if cover is None:
            level, score = "LOW", 0
            reason = "No positive forecast demand in this series."
        elif float(cover) < lead_days:
            level, score = "HIGH", 3
            reason = "Available-to-promise cover is below supplier lead time."
        elif stock < horizon_demand:
            level, score = "MEDIUM", 2
            reason = "Inventory position is below forecast demand for the selected horizon."
        else:
            level, score = "LOW", 1
            reason = "Current position covers the selected horizon under the baseline forecast."
        if level == "LOW" and excess_units > 0:
            level = "EXCESS"
            reason = "Inventory position is above the policy maximum-stock target."
        rows.append({
            "sku": sku, "location": location, "risk_level": level, "risk_score": score,
            "reason": reason, "inventory_position": report["inventory_position"],
            "days_of_cover": cover, "lead_time_days": lead_days,
            "forecast_model": report["forecast_model"], "horizon_demand": horizon_demand,
            "excess_units": excess_units,
        })
    rows.sort(key=lambda item: (-int(item["risk_score"]),
                               float(item["days_of_cover"]) if item["days_of_cover"] is not None else float("inf"),
                               item["sku"], item["location"]))
    return {"label": "SYNTHETIC", "horizon_weeks": horizon_weeks,
            "count": len(rows), "rows": rows[:limit],
            "excess_count": sum(int(dec(item["excess_units"]) > 0) for item in rows),
            "excess_rows": sorted((item for item in rows if dec(item["excess_units"]) > 0),
                                  key=lambda item: (-float(item["excess_units"]), item["sku"], item["location"]))[:limit]}


def make_replenishment_draft(
    tables: InventoryTables, identity: Any, idempotency_key: str,
    sku: str, location: str, budget: Any | None = None,
    store: ProposalStore | None = None,
) -> dict[str, Any]:
    inputs = _inventory_inputs(tables, sku, location)
    policy, supplier = inputs["policy"], inputs["supplier"]
    formula = replenishment_formula(
        weekly_demand_mean=inputs["weekly_mean"], weekly_demand_std=inputs["weekly_std"],
        service_level=policy["service_level"], lead_time_days=supplier["lead_time_days"],
        lead_time_std_days=supplier["lead_time_std"], review_period_days=policy["review_period_days"],
        inventory_position_units=inputs["stock"]["inventory_position"],
        min_order_qty=supplier["min_order_qty"], pack_size=supplier["pack_size"],
        unit_cost=supplier["unit_cost"], max_stock_days=policy["max_stock_days"], budget=budget,
    )
    payload = {
        "sku": sku, "location": location, "label": "SYNTHETIC",
        "status": "DRAFT", "approval_status": "APPROVED_FOR_DRAFT_ONLY",
        "supplier_id": str(supplier["supplier_id"]), "forecast_model": inputs["model"],
        "suggested_units": formula["suggested_units"],
        "unit_cost": formula["unit_cost"], "estimated_cost": formula["estimated_cost"],
        "inventory_position": formula["inventory_position_units"],
        "reorder_point": formula["reorder_point_units"],
        "safety_stock": formula["safety_stock_units"],
        "reason": formula["reason"],
        "notice": "Draft only. No purchase order or supplier communication was created.",
    }
    return (store or ProposalStore()).create(identity, idempotency_key, payload)


def propose_transfers(
    tables: InventoryTables, *, sku: str | None = None, limit: int = 20,
) -> dict[str, Any]:
    if not 1 <= limit <= 100:
        raise ValueError("Transfer result limit is outside the allowed range.")
    locations = sorted(tables.sku_policy["location"].astype(str).unique())
    rows: list[dict[str, Any]] = []
    skus = [sku] if sku else sorted(tables.sku_policy["sku"].astype(str).unique())
    for selected_sku in skus:
        try:
            position = {location: inventory_position_report(tables, selected_sku, location)
                        for location in locations}
        except ValueError:
            continue
        for source in locations:
            source_report = position[source]
            source_cover = source_report["days_of_cover"]
            if source_cover is None:
                continue
            source_daily = dec(source_report["weekly_demand_mean"]) / Decimal(7)
            source_surplus = max(Decimal(0), dec(source_report["available_to_promise"])
                                - source_daily * Decimal(source_report["max_stock_days"]))
            for destination in locations:
                if source == destination:
                    continue
                destination_report = position[destination]
                destination_cover = destination_report["days_of_cover"]
                if destination_cover is None:
                    continue
                destination_daily = dec(destination_report["weekly_demand_mean"]) / Decimal(7)
                destination_need = max(Decimal(0),
                    destination_daily * Decimal(destination_report["lead_time_days"]
                                                + destination_report["review_period_days"])
                    - dec(destination_report["inventory_position"]))
                route = tables.transfers.loc[
                    (tables.transfers["sku"].astype(str) == selected_sku)
                    & (tables.transfers["source_location"].astype(str) == source)
                    & (tables.transfers["destination_location"].astype(str) == destination)
                ]
                if route.empty:
                    route_days, unit_cost = 5, Decimal("0.25")
                else:
                    durations = (pd.to_datetime(route["eta"], utc=True)
                                 - pd.to_datetime(route["ship_date"], utc=True)).dt.days
                    route_days = max(1, int(durations.median()))
                    unit_cost = dec(route["unit_cost"].median())
                quantity = int(max(Decimal(0), min(source_surplus, destination_need)))
                destination_supplier = dec(destination_report["unit_cost"])
                route_feasible = route_days <= max(1, int(destination_report["lead_time_days"]))
                economic = unit_cost <= destination_supplier * Decimal("0.15")
                if quantity <= 0 or not route_feasible or not economic:
                    continue
                rows.append({
                    "sku": selected_sku, "source_location": source,
                    "destination_location": destination, "quantity": quantity,
                    "route_days": route_days, "estimated_transfer_cost": money(unit_cost * quantity),
                    "source_surplus": source_surplus, "destination_need": destination_need,
                    "eligible": quantity <= source_surplus and quantity <= destination_need
                                and route_feasible and economic,
                    "label": "SYNTHETIC",
                })
    rows.sort(key=lambda item: (not item["eligible"], -float(item["destination_need"]),
                               item["sku"], item["source_location"], item["destination_location"]))
    return {"label": "SYNTHETIC", "rows": rows[:limit], "count": min(len(rows), limit)}


def simulate_scenarios(
    tables: InventoryTables, *, sku: str = "SKU-001", location: str = "LOC-001",
    replications: int = 200, seed: int = 20261101, horizon_days: int = 90,
) -> dict[str, Any]:
    if not 20 <= replications <= 2000 or not 7 <= horizon_days <= 90:
        raise ValueError("Scenario size is outside the allowed range.")
    inputs = _inventory_inputs(tables, sku, location)
    snapshot, policy, supplier = inputs["snapshot"], inputs["policy"], inputs["supplier"]
    values = np.maximum(inputs["history"]["units"].to_numpy(dtype=float), 0.0)
    daily_mean = max(0.0, float(inputs["weekly_mean"]) / 7.0)
    daily_std = float(np.std(values, ddof=1) / math.sqrt(7.0)) if values.size > 1 else 0.0
    service = float(policy["service_level"])
    z = NormalDist().inv_cdf(service)
    start = float(available_to_promise(snapshot["on_hand"], snapshot["reserved"], snapshot["blocked"]))
    unit_cost = float(supplier["unit_cost"])
    existing_backorders = int(snapshot["backorders"])
    opening_pipeline = [(day, qty) for day, qty in inputs["incoming_pipeline"]
                        if day <= horizon_days and qty > 0]
    policies = {"lean": 1.0, "balanced": 1.35, "resilient": 1.8}
    conditions = {"supplier_delay": (1.0, 7), "demand_spike": (1.5, 0)}
    output: list[dict[str, Any]] = []
    for condition, (demand_multiplier, added_lead_days) in conditions.items():
        for policy_name, buffer_multiplier in policies.items():
            rng = np.random.default_rng(seed + len(output))
            fill_rates: list[float] = []
            stockout_days: list[float] = []
            average_inventory: list[float] = []
            holding_costs: list[float] = []
            excess_units: list[float] = []
            expedite_costs: list[float] = []
            order_counts: list[float] = []
            for _ in range(replications):
                stock = max(0.0, start)
                pipeline: list[tuple[int, int]] = list(opening_pipeline)
                served = requested = lost = stock_sum = 0.0
                daily_stockouts = expedites = orders = 0
                lead = max(1, int(supplier["lead_time_days"]) + added_lead_days)
                review = max(1, int(policy["review_period_days"]))
                target = max(0.0, daily_mean * (lead + review)
                             + buffer_multiplier * z * math.sqrt(
                                 max(0.0, (lead + review) * daily_std**2
                                     + daily_mean**2 * float(supplier["lead_time_std"])**2)))
                target = min(target, daily_mean * float(policy["max_stock_days"]))
                reorder = target * 0.72
                for day in range(horizon_days):
                    arrivals = [item for item in pipeline if item[0] <= day]
                    stock += sum(item[1] for item in arrivals)
                    pipeline = [item for item in pipeline if item[0] > day]
                    multiplier = demand_multiplier if condition == "demand_spike" and day < 21 else 1.0
                    demand = int(rng.poisson(max(0.0, daily_mean * multiplier)))
                    if day == 0:
                        demand += existing_backorders
                    requested += demand
                    available = max(0.0, stock)
                    served_today = min(available, demand)
                    served += served_today
                    lost += demand - served_today
                    stock -= served_today
                    if demand > available:
                        daily_stockouts += 1
                    stock_sum += max(0.0, stock)
                    if day % review == 0 and stock + sum(item[1] for item in pipeline) <= reorder:
                        pack = max(int(supplier["pack_size"]), 1)
                        needed = max(0.0, target - stock - sum(item[1] for item in pipeline))
                        qty = int(math.ceil(needed / pack) * pack) if needed else 0
                        qty = max(int(supplier["min_order_qty"]), qty) if qty else 0
                        max_stock_qty = max(0, int((daily_mean * float(policy["max_stock_days"])
                                                    - stock - sum(item[1] for item in pipeline)) // pack) * pack)
                        qty = min(qty, max_stock_qty)
                        if qty < int(supplier["min_order_qty"]):
                            qty = 0
                        if qty:
                            orders += 1
                            actual_delay = lead if rng.random() <= float(supplier["reliability"]) else lead + 7
                            if actual_delay > lead + 2:
                                expedites += 1
                            pipeline.append((day + actual_delay, qty))
                fill_rates.append(served / requested if requested else 1.0)
                stockout_days.append(float(daily_stockouts))
                average_inventory.append(stock_sum / horizon_days)
                holding_costs.append(stock_sum / horizon_days * unit_cost * 0.01 * horizon_days / 30)
                excess_units.append(max(0.0, stock + sum(item[1] for item in pipeline) - target))
                expedite_costs.append(expedites * unit_cost * 0.15)
                order_counts.append(float(orders))
            output.append({
                "condition": condition, "policy": policy_name,
                "fill_rate": round(float(np.mean(fill_rates)), 4),
                "stockout_days": round(float(np.mean(stockout_days)), 2),
                "average_inventory_units": round(float(np.mean(average_inventory)), 2),
                "holding_cost_estimate": money(Decimal(str(float(np.mean(holding_costs))))),
                "excess_units": round(float(np.mean(excess_units)), 2),
            "expedite_cost_estimate": money(Decimal(str(float(np.mean(expedite_costs))))),
                "order_frequency": round(float(np.mean(order_counts)), 2),
                "replications": replications,
            })
    return {"label": "SYNTHETIC", "seed": seed, "horizon_days": horizon_days,
            "sku": sku, "location": location, "tradeoffs": output,
            "notice": "Fixed-seed scenario comparison, not an optimized policy or operating forecast."}

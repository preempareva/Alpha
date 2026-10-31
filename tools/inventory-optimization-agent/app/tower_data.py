"""Synthetic inventory tower tables and data quality checks."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data" / "generated" / "tower"
TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "sales_history": ("sku", "location", "date", "units", "revenue"),
    "inventory_snapshot": ("sku", "location", "snapshot_time", "on_hand", "reserved", "blocked",
                           "in_transit", "backorders"),
    "purchase_orders": ("po_id", "sku", "location", "supplier_id", "order_date", "expected_date",
                        "open_qty", "status"),
    "supplier": ("supplier_id", "lead_time_days", "lead_time_std", "min_order_qty", "pack_size",
                 "unit_cost", "reliability"),
    "transfers": ("transfer_id", "sku", "source_location", "destination_location", "qty", "ship_date",
                  "eta", "status", "unit_cost"),
    "sku_policy": ("sku", "location", "service_level", "review_period_days", "max_stock_days"),
}


@dataclass(frozen=True)
class InventoryTables:
    sales_history: pd.DataFrame
    inventory_snapshot: pd.DataFrame
    purchase_orders: pd.DataFrame
    supplier: pd.DataFrame
    transfers: pd.DataFrame
    sku_policy: pd.DataFrame

    def as_mapping(self) -> dict[str, pd.DataFrame]:
        return {name: getattr(self, name) for name in TABLE_COLUMNS}


def load_tables(data_root: Path | None = None) -> InventoryTables:
    """Read only the fixed synthetic table names from the configured data directory."""
    root = data_root or Path(os.getenv("INVENTORY_TOWER_DATA_ROOT", str(DATA_ROOT)))
    tables: dict[str, pd.DataFrame] = {}
    for name in TABLE_COLUMNS:
        path = root / f"{name}.csv"
        if not path.is_file():
            raise FileNotFoundError("Synthetic Inventory Control Tower data is missing; run Alpha bootstrap.")
        frame = pd.read_csv(path, low_memory=False)
        for column in ("date", "snapshot_time", "order_date", "expected_date", "ship_date", "eta"):
            if column in frame:
                frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
        tables[name] = frame
    return InventoryTables(**tables)


def validate_tables(tables: InventoryTables | Mapping[str, pd.DataFrame]) -> dict[str, object]:
    """Return bounded issue codes only; no cell values are copied to the report."""
    values = tables.as_mapping() if isinstance(tables, InventoryTables) else dict(tables)
    issues: list[str] = []
    if set(values) != set(TABLE_COLUMNS):
        return {"label": "SYNTHETIC", "valid": False,
                "issue_codes": ["table_set_mismatch"], "tables_checked": 0}

    for name, required in TABLE_COLUMNS.items():
        frame = values[name]
        if frame.empty:
            issues.append(f"{name}:empty")
            continue
        missing = set(required) - set(frame.columns)
        if missing:
            issues.append(f"{name}:missing_columns")
            continue
        if frame[list(required)].isna().any().any():
            issues.append(f"{name}:null_required")

    if issues:
        return {"label": "SYNTHETIC", "valid": False,
                "issue_codes": sorted(set(issues)), "tables_checked": len(values)}

    def unique(name: str, columns: list[str]) -> None:
        if values[name].duplicated(columns).any():
            issues.append(f"{name}:duplicate_key")

    unique("supplier", ["supplier_id"])
    unique("sales_history", ["sku", "location", "date"])
    unique("inventory_snapshot", ["sku", "location"])
    unique("sku_policy", ["sku", "location"])
    unique("purchase_orders", ["po_id"])
    unique("transfers", ["transfer_id"])

    sku_locations = set(map(tuple, values["sku_policy"][['sku', 'location']].astype(str).to_numpy()))
    sales_keys = set(map(tuple, values["sales_history"][['sku', 'location']].astype(str).to_numpy()))
    snapshot_keys = set(map(tuple, values["inventory_snapshot"][['sku', 'location']].astype(str).to_numpy()))
    if not sales_keys.issubset(sku_locations) or snapshot_keys != sku_locations:
        issues.append("sku_location_reference_mismatch")
    supplier_ids = set(values["supplier"]["supplier_id"].astype(str))
    if not set(values["purchase_orders"]["supplier_id"].astype(str)).issubset(supplier_ids):
        issues.append("purchase_orders:unknown_supplier")
    sku_ids = set(values["sku_policy"]["sku"].astype(str))
    if not set(values["sales_history"]["sku"].astype(str)).issubset(sku_ids):
        issues.append("sales_history:unknown_sku")

    for name, columns in {
        "sales_history": ["units", "revenue"],
        "inventory_snapshot": ["on_hand", "reserved", "blocked", "in_transit", "backorders"],
        "purchase_orders": ["open_qty"],
        "supplier": ["lead_time_days", "lead_time_std", "min_order_qty", "pack_size", "unit_cost"],
        "transfers": ["qty", "unit_cost"],
        "sku_policy": ["review_period_days", "max_stock_days"],
    }.items():
        numeric_columns = {column: pd.to_numeric(values[name][column], errors="coerce") for column in columns}
        if any(series.isna().any() or not np.isfinite(series.to_numpy(dtype=float)).all()
               for series in numeric_columns.values()):
            issues.append(f"{name}:invalid_numeric_measure")
        if any((series < 0).any() for series in numeric_columns.values()):
            issues.append(f"{name}:negative_measure")
    if not values["sku_policy"]["service_level"].between(0.5, 0.999).all():
        issues.append("sku_policy:service_level_range")
    if not values["supplier"]["reliability"].between(0, 1).all():
        issues.append("supplier:reliability_range")
    if (pd.to_datetime(values["sales_history"]["date"], errors="coerce", utc=True).isna().any()
            or (values["sales_history"]["units"] % 1 != 0).any()):
        issues.append("sales_history:invalid_date_or_units")
    if (pd.to_datetime(values["purchase_orders"]["expected_date"], errors="coerce", utc=True)
            < pd.to_datetime(values["purchase_orders"]["order_date"], errors="coerce", utc=True)).any():
        issues.append("purchase_orders:date_order")
    if (values["transfers"]["source_location"].astype(str)
            == values["transfers"]["destination_location"].astype(str)).any():
        issues.append("transfers:self_route")

    return {"label": "SYNTHETIC", "valid": not issues,
            "issue_codes": sorted(set(issues)), "tables_checked": len(values),
            "rows_by_table": {name: int(len(frame)) for name, frame in values.items()}}

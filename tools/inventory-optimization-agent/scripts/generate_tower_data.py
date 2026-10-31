"""Generate the fixed-seed, fictional Inventory Control Tower dataset."""

from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20261101
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "generated" / "tower"
LOCATIONS = ("LOC-001", "LOC-002", "LOC-003")


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def generate(out: Path = DEFAULT_OUT, *, seed: int = SEED) -> dict[str, int]:
    rng = np.random.default_rng(seed)
    skus = [f"SKU-{index:03d}" for index in range(1, 25)]
    supplier_rows = []
    for index in range(1, 9):
        supplier_rows.append({
            "supplier_id": f"SUP-{index:03d}",
            "lead_time_days": 7 + index * 2,
            "lead_time_std": 2 + index % 4,
            "min_order_qty": 6 if index % 2 else 12,
            "pack_size": (index % 4) + 1,
            "unit_cost": money(Decimal("3.75") + Decimal(index) * Decimal("1.13")),
            "reliability": round(0.94 - (index % 4) * 0.055, 3),
        })
    suppliers = pd.DataFrame(supplier_rows)
    weeks = pd.date_range("2024-01-01", periods=104, freq="W-MON", tz="UTC")
    sales_rows: list[dict[str, object]] = []
    base_daily: dict[tuple[str, str], float] = {}
    for sku_index, sku in enumerate(skus, 1):
        intermittent = sku_index % 6 == 0
        for location_index, location in enumerate(LOCATIONS, 1):
            mean_daily = (0.42 + (sku_index % 7) * 0.24) * (1 + location_index * 0.12)
            base_daily[(sku, location)] = mean_daily
            unit_price = Decimal("12.50") + Decimal(sku_index) * Decimal("1.85") + Decimal(location_index)
            for week_index, week in enumerate(weeks):
                yearly = 1 + 0.25 * np.sin(2 * np.pi * week_index / 52)
                promo = 1.8 if sku_index % 5 == 0 and week_index % 17 in {2, 3} else 1.0
                daily_rate = mean_daily * yearly * promo
                units = int(rng.poisson(daily_rate * 7))
                if intermittent and rng.random() < 0.68:
                    units = 0
                revenue = Decimal(units) * unit_price * Decimal("0.9" if promo > 1 else "1")
                sales_rows.append({
                    "sku": sku,
                    "location": location,
                    "date": week.date().isoformat(),
                    "units": units,
                    "revenue": money(revenue),
                })

    sales_frame = pd.DataFrame(sales_rows)
    trailing_mean = sales_frame.groupby(["sku", "location"], sort=False)["units"].apply(
        lambda values: float(values.tail(8).mean())
    ).to_dict()
    latest = weeks[-1]
    snapshots: list[dict[str, object]] = []
    policy_rows: list[dict[str, object]] = []
    for sku_index, sku in enumerate(skus, 1):
        for location_index, location in enumerate(LOCATIONS, 1):
            mean_weekly = trailing_mean[(sku, location)]
            on_hand = max(0, int(round(mean_weekly / 7 * rng.integers(25, 86))))
            reserved = int(round(on_hand * (0.04 + (sku_index % 3) * 0.025)))
            blocked = int(round(on_hand * (0.12 if (sku_index + location_index) % 7 == 0 else 0.0)))
            backorders = int(round(mean_weekly * (0.0 if (sku_index + location_index) % 4 else 0.8)))
            in_transit = int(round(mean_weekly * (0.0 if (sku_index + location_index) % 3 else 1.5)))
            snapshots.append({
                "sku": sku, "location": location, "snapshot_time": latest.isoformat(),
                "on_hand": on_hand, "reserved": reserved, "blocked": blocked,
                "in_transit": in_transit, "backorders": backorders,
            })
            policy_rows.append({
                "sku": sku, "location": location,
                "service_level": round((0.90, 0.95, 0.98)[sku_index % 3], 2),
                "review_period_days": (7, 14, 21)[location_index - 1],
                "max_stock_days": (42, 56, 70)[(sku_index + location_index) % 3],
            })

    supplier_by_sku = {sku: f"SUP-{(index % len(supplier_rows)) + 1:03d}"
                       for index, sku in enumerate(skus)}
    po_rows: list[dict[str, object]] = []
    po_number = 0
    for sku_index, sku in enumerate(skus, 1):
        for location_index, location in enumerate(LOCATIONS, 1):
            if (sku_index + location_index) % 3 == 0:
                continue
            po_number += 1
            supplier_id = supplier_by_sku[sku]
            supplier = suppliers.loc[suppliers.supplier_id == supplier_id].iloc[0]
            delay = 8 if sku_index % 8 == 0 else 0
            expected = latest + pd.Timedelta(days=int(supplier.lead_time_days) + delay)
            po_rows.append({
                "po_id": f"PO-SYN-{po_number:04d}", "sku": sku, "location": location,
                "supplier_id": supplier_id, "order_date": (latest - pd.Timedelta(days=7)).date().isoformat(),
                "expected_date": expected.date().isoformat(),
                "open_qty": int(rng.integers(6, 50)),
                "status": "confirmed" if sku_index % 9 else "delayed",
            })

    transfer_rows: list[dict[str, object]] = []
    transfer_number = 0
    for sku_index, sku in enumerate(skus, 1):
        for source_index, destination_index in ((0, 1), (1, 2)):
            transfer_number += 1
            ship = latest - pd.Timedelta(days=int(rng.integers(3, 24)))
            route_days = 2 + (source_index + destination_index + sku_index) % 5
            transfer_rows.append({
                "transfer_id": f"TR-SYN-{transfer_number:04d}", "sku": sku,
                "source_location": LOCATIONS[source_index],
                "destination_location": LOCATIONS[destination_index],
                "qty": int(rng.integers(4, 24)), "ship_date": ship.date().isoformat(),
                "eta": (ship + pd.Timedelta(days=route_days)).date().isoformat(),
                "status": "in_transit" if (sku_index + source_index) % 4 == 0 else "received",
                "unit_cost": money(Decimal("0.18") + Decimal(route_days) / Decimal("100")),
            })

    tables = {
        "sales_history": sales_frame,
        "inventory_snapshot": pd.DataFrame(snapshots),
        "purchase_orders": pd.DataFrame(po_rows),
        "supplier": suppliers,
        "transfers": pd.DataFrame(transfer_rows),
        "sku_policy": pd.DataFrame(policy_rows),
    }
    out.mkdir(parents=True, exist_ok=True)
    row_counts: dict[str, int] = {}
    for name, frame in tables.items():
        frame.to_csv(out / f"{name}.csv", index=False)
        row_counts[name] = int(len(frame))
    return row_counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    counts = generate(args.out, seed=args.seed)
    print(f"Wrote {sum(counts.values())} SYNTHETIC rows across {len(counts)} inventory tables.")


if __name__ == "__main__":
    main()

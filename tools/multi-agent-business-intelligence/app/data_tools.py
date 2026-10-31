"""Fixed, parameterized SQLite queries and an independent Python verifier."""

from __future__ import annotations

import math
import sqlite3
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from sqlglot import exp, parse

from .workflow import DB_PATH

MAX_ROWS = 20
ALLOWED_COLUMNS = frozenset({
    "order_id", "order_date", "product", "category", "region", "quantity", "gross", "refund",
    "period", "gross_revenue", "net_revenue", "order_lines", "value", "refund_percent",
})
ALLOWED_FUNCTIONS = frozenset({
    "COUNT", "NULLIF", "ROUND", "STRFTIME", "SUBSTRING", "SUM", "TIME_TO_STR", "TS_OR_DS_TO_TIMESTAMP"
})
COLUMNS = {"category": "category", "product": "product", "region": "region"}
METRICS = {
    "revenue": "ROUND(SUM(gross-refund),2)",
    "units": "SUM(quantity)",
}


class QueryRejected(ValueError):
    """A query or argument did not match the fixed read-only catalogue."""


@contextmanager
def _read_connection() -> Iterator[sqlite3.Connection]:
    if not Path(DB_PATH).exists():
        raise FileNotFoundError("Synthetic warehouse missing; run the BI seed script first.")
    db = sqlite3.connect(f"file:{Path(DB_PATH).as_posix()}?mode=ro", uri=True, timeout=1)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    deadline = time.monotonic() + 1.0
    db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    db.set_authorizer(_authorize)
    try:
        yield db
    finally:
        db.close()


def _authorize(action: int, arg1: str | None, arg2: str | None, db_name: str | None,
               trigger: str | None) -> int:
    del db_name, trigger
    if action == sqlite3.SQLITE_READ and arg1 == "orders" and (arg2 is None or arg2 in {
        "order_id", "order_date", "product", "category", "region", "quantity", "gross", "refund"
    }):
        return sqlite3.SQLITE_OK
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def _validate_date_range(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict) or set(value) != {"start", "end"}:
        raise QueryRejected("date_range must contain only start and end")
    try:
        start = date.fromisoformat(value["start"])
        end = date.fromisoformat(value["end"])
    except (TypeError, ValueError) as exc:
        raise QueryRejected("date range must use ISO dates") from exc
    if start > end:
        raise QueryRejected("date range start must be on or before end")
    return start.isoformat(), end.isoformat()


def _compile_query(name: str, arguments: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
    if name == "revenue_trend":
        grain = arguments["grain"]
        date_range = _validate_date_range(arguments["date_range"])
        period = {"month": "substr(order_date,1,7)", "week": "strftime('%Y-%W',order_date)"}.get(grain)
        if period is None:
            raise QueryRejected("unsupported time grain")
        sql = (
            f"SELECT {period} AS period, ROUND(SUM(gross),2) AS gross_revenue, "
            "ROUND(SUM(gross-refund),2) AS net_revenue, COUNT(*) AS order_lines "
            "FROM orders WHERE order_date>=? AND order_date<=? "
            "GROUP BY period ORDER BY period LIMIT ?"
        )
        return sql, (*date_range, MAX_ROWS)
    if name in {"top_categories", "top_products"}:
        metric = arguments["metric"]
        expression = METRICS.get(metric)
        group = "category" if name == "top_categories" else "product"
        limit = arguments["n"]
        date_range = _validate_date_range(arguments["date_range"])
        if expression is None or group not in COLUMNS.values() or not 1 <= limit <= MAX_ROWS:
            raise QueryRejected("unsupported metric, group, or result limit")
        sql = (
            f"SELECT {group}, {expression} AS value, COUNT(*) AS order_lines FROM orders "
            "WHERE order_date>=? AND order_date<=? "
            f"GROUP BY {group} ORDER BY value DESC,{group} ASC LIMIT ?"
        )
        return sql, (*date_range, limit)
    if name == "refund_rate":
        refund_group = COLUMNS.get(arguments["by"])
        if refund_group is None:
            raise QueryRejected("unsupported refund grouping")
        sql = (
            f"SELECT {refund_group}, ROUND(SUM(refund)*100.0/NULLIF(SUM(gross),0),2) AS refund_percent, "
            f"COUNT(*) AS order_lines FROM orders GROUP BY {refund_group} "
            f"ORDER BY refund_percent DESC,{refund_group} ASC LIMIT ?"
        )
        return sql, (MAX_ROWS,)
    if name == "region_breakdown":
        date_range = _validate_date_range(arguments["date_range"])
        sql = (
            "SELECT region, ROUND(SUM(gross),2) AS gross_revenue, "
            "ROUND(SUM(gross-refund),2) AS net_revenue, COUNT(*) AS order_lines "
            "FROM orders WHERE order_date>=? AND order_date<=? "
            "GROUP BY region ORDER BY net_revenue DESC,region ASC LIMIT ?"
        )
        return sql, (*date_range, MAX_ROWS)
    if name == "anomaly_check":
        metric = arguments["metric"]
        window = arguments["window"]
        if metric not in {"revenue", "units", "refund_rate"} or not 3 <= window <= 12:
            raise QueryRejected("unsupported anomaly metric or window")
        return (
            "SELECT substr(order_date,1,7) AS period, SUM(gross) AS gross_total, "
            "SUM(gross-refund) AS net_total, SUM(refund) AS refund_total, "
            "SUM(quantity) AS units_total FROM orders GROUP BY period ORDER BY period LIMIT ?",
            (MAX_ROWS,),
        )
    raise QueryRejected("tool is not in the fixed query catalogue")


def _check_select(sql: str) -> None:
    try:
        statements = parse(sql, read="sqlite")
    except Exception as exc:
        raise QueryRejected("query did not pass the SQLite AST check") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise QueryRejected("only one SELECT statement is permitted")
    tree = statements[0]
    tables = {table.name.casefold() for table in tree.find_all(exp.Table)}
    if tables != {"orders"}:
        raise QueryRejected("query references a table outside the allowlist")
    if any(column.name.casefold() not in ALLOWED_COLUMNS for column in tree.find_all(exp.Column)):
        raise QueryRejected("query references a column outside the allowlist")
    if any(isinstance(node, exp.Star) and not isinstance(node.parent, exp.Count) for node in tree.walk()):
        raise QueryRejected("wildcard column access is not permitted")
    for node in tree.find_all(exp.Func):
        if isinstance(node, (exp.And, exp.Or, exp.Not)):
            continue
        if node.sql_name().upper() not in ALLOWED_FUNCTIONS:
            raise QueryRejected("query calls a function outside the allowlist")


def execute_tool(name: str, arguments: dict[str, Any]) -> list[dict[str, Any]]:
    sql, params = _compile_query(name, arguments)
    _check_select(sql)
    with _read_connection() as db:
        rows = [dict(row) for row in db.execute(sql, params).fetchall()]
    if len(rows) > MAX_ROWS:
        raise QueryRejected("query result exceeds the row cap")
    if name == "anomaly_check":
        rows = _anomalies(rows, arguments["metric"], arguments["window"], arguments["z_threshold"])
    return rows


def _anomalies(rows: list[dict[str, Any]], metric: str, window: int,
               z_threshold: float) -> list[dict[str, Any]]:
    values = [_metric_value(row, metric) for row in rows]
    output = []
    for index, (row, value) in enumerate(zip(rows, values)):
        prior = values[max(0, index - window):index]
        if len(prior) < window:
            z_score = 0.0
        else:
            mean = sum(prior) / len(prior)
            variance = sum((item - mean) ** 2 for item in prior) / len(prior)
            deviation = math.sqrt(variance)
            z_score = (value - mean) / deviation if deviation else 0.0
        output.append({
            "period": row["period"],
            "metric_value": round(value, 2),
            "z_score": round(z_score, 4),
            "is_anomaly": abs(z_score) >= z_threshold,
        })
    return output[-MAX_ROWS:]


def _metric_value(row: dict[str, Any], metric: str) -> float:
    if metric == "revenue":
        return float(row["net_total"])
    if metric == "units":
        return float(row["units_total"])
    gross = float(row["gross_total"])
    return float(row["refund_total"]) * 100.0 / gross if gross else 0.0


def reference_rows(name: str, arguments: dict[str, Any]) -> list[dict[str, Any]]:
    """Independently aggregate raw synthetic rows in Python for verification."""
    raw = _read_source_rows()
    if "date_range" in arguments:
        start, end = _validate_date_range(arguments["date_range"])
        raw = [row for row in raw if start <= row["order_date"] <= end]
    if name == "revenue_trend":
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in raw:
            period = row["order_date"][:7] if arguments["grain"] == "month" else _week(row["order_date"])
            groups[period].append(row)
        return [{
            "period": period,
            "gross_revenue": _money(sum((_decimal(row["gross"]) for row in rows), Decimal(0))),
            "net_revenue": _money(sum((_decimal(row["gross"]) - _decimal(row["refund"]) for row in rows), Decimal(0))),
            "order_lines": len(rows),
        } for period, rows in sorted(groups.items())][:MAX_ROWS]
    if name in {"top_categories", "top_products"}:
        group = "category" if name == "top_categories" else "product"
        groups = _group_rows(raw, group)
        rows: list[dict[str, Any]] = []
        for value, entries in groups.items():
            if arguments["metric"] == "units":
                metric_value = sum(row["quantity"] for row in entries)
            else:
                net_total = sum((_decimal(row["gross"]) - _decimal(row["refund"])
                                 for row in entries), Decimal(0))
                metric_value = _money(net_total)
            rows.append({group: value, "value": metric_value, "order_lines": len(entries)})
        rows.sort(key=lambda item: (-float(item["value"]), str(item[group])))
        return rows[:arguments["n"]]
    if name == "refund_rate":
        groups = _group_rows(raw, arguments["by"])
        output: list[dict[str, Any]] = []
        for value, entries in groups.items():
            gross = sum((_decimal(row["gross"]) for row in entries), Decimal(0))
            refund = sum((_decimal(row["refund"]) for row in entries), Decimal(0))
            percent = (refund * Decimal(100) / gross) if gross else Decimal(0)
            output.append({arguments["by"]: value, "refund_percent": _money(percent), "order_lines": len(entries)})
        output.sort(key=lambda item: (-float(item["refund_percent"]), str(item[arguments["by"]])))
        return output[:MAX_ROWS]
    if name == "region_breakdown":
        groups = _group_rows(raw, "region")
        region_output: list[dict[str, Any]] = [{
            "region": region,
            "gross_revenue": _money(sum((_decimal(row["gross"]) for row in entries), Decimal(0))),
            "net_revenue": _money(sum((_decimal(row["gross"]) - _decimal(row["refund"])
                                       for row in entries), Decimal(0))),
            "order_lines": len(entries),
        } for region, entries in groups.items()]
        region_output.sort(key=lambda item: (-float(item["net_revenue"]), str(item["region"])))
        return region_output[:MAX_ROWS]
    if name == "anomaly_check":
        monthly: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in raw:
            monthly[row["order_date"][:7]].append(row)
        base = [{
            "period": period,
            "gross_total": float(sum(_decimal(row["gross"]) for row in entries)),
            "net_total": float(sum(_decimal(row["gross"]) - _decimal(row["refund"]) for row in entries)),
            "refund_total": float(sum(_decimal(row["refund"]) for row in entries)),
            "units_total": sum(row["quantity"] for row in entries),
        } for period, entries in sorted(monthly.items())]
        return _anomalies(base, arguments["metric"], arguments["window"], arguments["z_threshold"])
    raise QueryRejected("tool cannot be independently verified")


def _read_source_rows() -> list[dict[str, Any]]:
    sql = "SELECT order_date,product,category,region,quantity,gross,refund FROM orders ORDER BY order_date,order_id"
    _check_select(sql)
    with _read_connection() as db:
        return [dict(row) for row in db.execute(sql).fetchall()]


def _group_rows(rows: list[dict[str, Any]], column: str) -> dict[str, list[dict[str, Any]]]:
    if column not in COLUMNS.values():
        raise QueryRejected("grouping column is not permitted")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row[column])].append(row)
    return groups


def _week(value: str) -> str:
    year, week, _ = date.fromisoformat(value).isocalendar()
    return f"{year:04}-{week - 1:02}"


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def results_match(actual: list[dict[str, Any]], expected: list[dict[str, Any]]) -> bool:
    if len(actual) != len(expected):
        return False
    for actual_row, expected_row in zip(actual, expected):
        if actual_row.keys() != expected_row.keys():
            return False
        for key, expected_value in expected_row.items():
            actual_value = actual_row[key]
            if isinstance(expected_value, bool):
                if actual_value is not expected_value:
                    return False
            elif isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool):
                if not isinstance(actual_value, (int, float)) or not math.isclose(
                    float(actual_value), float(expected_value), rel_tol=0.0, abs_tol=0.001
                ):
                    return False
            elif actual_value != expected_value:
                return False
    return True

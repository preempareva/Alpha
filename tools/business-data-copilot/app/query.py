"""Allowlisted QueryPlan validation, DuckDB SQL compilation, and pandas verification."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd
from sqlglot import exp, parse

from .models import QueryPlan, measure_alias
from .planner import CopilotUnsupported

MAX_QUERY_ROWS = 500
MAX_RESULT_BYTES = 750_000
ALLOWED_FUNCTIONS = {"SUM", "AVG", "COUNT", "MIN", "MAX", "DATE_TRUNC", "TIMESTAMP_TRUNC", "CONTAINS"}


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    parameters: tuple[Any, ...]
    output_fields: tuple[str, ...]


def compile_query(
    plan: QueryPlan,
    *,
    table_name: str,
    columns: list[dict[str, Any]],
) -> CompiledQuery:
    if not re.fullmatch(r"d_[a-f0-9]{16}", table_name):
        raise CopilotUnsupported("Workspace table identifier is invalid.")
    if plan.limit > MAX_QUERY_ROWS:
        raise CopilotUnsupported(f"Queries are limited to {MAX_QUERY_ROWS} result rows.")
    column_map = {str(column["name"]): column for column in columns}
    select_parts: list[str] = []
    group_parts: list[str] = []
    output_fields: list[str] = []
    params: list[Any] = []

    dimensions = []
    for name in plan.dimensions:
        column = column_map.get(name)
        if column is None or column.get("sensitive") or column.get("role") not in {"dimension", "date"}:
            raise CopilotUnsupported("A query dimension is unavailable or sensitive.")
        dimensions.append(column)
        alias = f"d_{column['safe_name']}"
        expression = _identifier(str(column["safe_name"]))
        if column.get("role") == "date" and plan.time_grain:
            expression = f"DATE_TRUNC('{plan.time_grain}', {expression})"
            alias = f"date_{plan.time_grain}"
        select_parts.append(f"{expression} AS {_identifier(alias)}")
        group_parts.append(expression)
        output_fields.append(alias)

    date_column = next((
        column for column in columns if column.get("role") == "date" and not column.get("sensitive")
    ), None)
    if plan.time_grain and date_column is None:
        raise CopilotUnsupported("Time grouping needs a confirmed date column.")
    if plan.time_grain and not any(column.get("role") == "date" for column in dimensions):
        assert date_column is not None
        alias = f"date_{plan.time_grain}"
        expression = f"DATE_TRUNC('{plan.time_grain}', {_identifier(str(date_column['safe_name']))})"
        select_parts.insert(0, f"{expression} AS {_identifier(alias)}")
        group_parts.insert(0, expression)
        output_fields.insert(0, alias)

    measure_fields: list[tuple[str, dict[str, Any]]] = []
    for measure_index, measure in enumerate(plan.measures):
        column = column_map.get(measure.column)
        if column is None or column.get("role") == "exclude":
            raise CopilotUnsupported("A measure is unavailable in the confirmed schema.")
        if measure.aggregation not in {"count", "count_distinct"}:
            if column.get("role") != "measure" or column.get("data_type") not in {"number", "integer"}:
                raise CopilotUnsupported("This aggregation requires a confirmed numeric measure.")
        if measure.aggregation == "count_distinct":
            expression = f"COUNT(DISTINCT {_identifier(str(column['safe_name']))})"
        elif measure.aggregation == "count":
            expression = f"COUNT({_identifier(str(column['safe_name']))})"
        else:
            expression = f"{measure.aggregation.upper()}({_identifier(str(column['safe_name']))})"
        alias = measure_alias(measure.aggregation, column, measure_index)
        select_parts.append(f"{expression} AS {_identifier(alias)}")
        output_fields.append(alias)
        measure_fields.append((alias, column))

    where_parts = []
    for filter_item in plan.filters:
        column = column_map.get(filter_item.column)
        if column is None or column.get("sensitive") or column.get("role") == "exclude":
            raise CopilotUnsupported("Filters cannot reference sensitive or unavailable columns.")
        expression = _identifier(str(column["safe_name"]))
        operator = filter_item.operator
        value = _coerce_filter_value(filter_item.value, str(column["data_type"]))
        if operator == "contains":
            if column.get("data_type") != "text":
                raise CopilotUnsupported("Contains filters require a text column.")
            where_parts.append(f"CONTAINS({expression}, ?)")
            params.append(str(value))
        else:
            sql_operator = {"eq": "=", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[operator]
            where_parts.append(f"{expression} {sql_operator} ?")
            params.append(value)

    sql = f"SELECT {', '.join(select_parts)} FROM {_identifier(table_name)}"
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    if group_parts:
        sql += " GROUP BY " + ", ".join(group_parts)
    if plan.order_by:
        if plan.order_by.field not in output_fields:
            raise CopilotUnsupported("Sort order must use a selected output field.")
        sql += f" ORDER BY {_identifier(plan.order_by.field)} {plan.order_by.direction.upper()}"
        tie_fields = [field for field in output_fields
                      if (field.startswith("d_") or field.startswith("date_")) and field != plan.order_by.field]
        if tie_fields:
            sql += ", " + ", ".join(f"{_identifier(field)} ASC" for field in tie_fields)
    elif measure_fields:
        sql += f" ORDER BY {_identifier(measure_fields[0][0])} DESC"
        if output_fields and group_parts:
            sql += ", " + ", ".join(f"{_identifier(field)} ASC" for field in output_fields
                                     if field in {f"d_{item['safe_name']}" for item in dimensions} or field.startswith("date_"))
    sql += " LIMIT ?"
    params.append(min(plan.limit, MAX_QUERY_ROWS))
    _check_select(sql, table_name=table_name, allowed_columns={str(item["safe_name"]) for item in columns})
    return CompiledQuery(sql=sql, parameters=tuple(params), output_fields=tuple(output_fields))


def _check_select(sql: str, *, table_name: str, allowed_columns: set[str]) -> None:
    try:
        statements = parse(sql, read="duckdb")
    except Exception as exc:
        raise CopilotUnsupported("Compiled query did not pass the DuckDB AST check.") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise CopilotUnsupported("Only one compiled SELECT is permitted.")
    tree = statements[0]
    tables = {table.name.casefold() for table in tree.find_all(exp.Table)}
    if tables != {table_name.casefold()}:
        raise CopilotUnsupported("Compiled query references a table outside this user's dataset.")
    if any(column.name.casefold() not in allowed_columns for column in tree.find_all(exp.Column)):
        aliases = {alias.alias.casefold() for alias in tree.find_all(exp.Alias)}
        if any(column.name.casefold() not in allowed_columns | aliases for column in tree.find_all(exp.Column)):
            raise CopilotUnsupported("Compiled query references a column outside the confirmed schema.")
    if any(isinstance(node, exp.Star) and not isinstance(node.parent, exp.Count) for node in tree.walk()):
        raise CopilotUnsupported("Wildcard column selection is not permitted.")
    for function in tree.find_all(exp.Func):
        if function.sql_name().upper() not in ALLOWED_FUNCTIONS:
            raise CopilotUnsupported("Compiled query contains a function outside the allowlist.")
    if tree.args.get("joins") or tree.find(exp.Subquery) is not None or tree.find(exp.Command) is not None:
        raise CopilotUnsupported("Joins, subqueries, and commands are outside the Copilot query contract.")


def verify_with_pandas(
    source: pd.DataFrame,
    plan: QueryPlan,
    *,
    columns: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reapply filters and aggregations with pandas, independent of DuckDB SQL execution."""
    by_name = {str(column["name"]): column for column in columns}
    frame = source.copy()
    for filter_item in plan.filters:
        column = by_name[filter_item.column]
        field = str(column["safe_name"])
        value = _coerce_filter_value(filter_item.value, str(column["data_type"]))
        series = frame[field]
        if filter_item.operator == "contains":
            mask = series.astype("string").str.contains(re.escape(str(value)), case=True, na=False, regex=True)
        elif filter_item.operator == "eq":
            mask = series == value
        elif filter_item.operator == "ne":
            mask = series != value
        elif filter_item.operator == "gt":
            mask = series > value
        elif filter_item.operator == "gte":
            mask = series >= value
        elif filter_item.operator == "lt":
            mask = series < value
        else:
            mask = series <= value
        frame = frame[mask.fillna(False)]
    source_rows = len(frame)

    grouping: list[tuple[str, Any]] = []
    if plan.time_grain:
        date_column = next(column for column in columns if column.get("role") == "date")
        safe_name = str(date_column["safe_name"])
        key = f"date_{plan.time_grain}"
        frame[key] = _bucket_dates(frame[safe_name], plan.time_grain)
        grouping.append((key, key))
    for name in plan.dimensions:
        column = by_name[name]
        if column.get("role") == "date" and plan.time_grain:
            continue
        key = f"d_{column['safe_name']}"
        frame[key] = frame[str(column["safe_name"])]
        grouping.append((key, key))

    measure_fields = [(measure_alias(item.aggregation, by_name[item.column], index), item, by_name[item.column])
                      for index, item in enumerate(plan.measures)]
    output: list[dict[str, Any]] = []
    if grouping:
        group_values = frame.groupby([item[0] for item in grouping], dropna=False, sort=False)
        for group_key, group in group_values:
            if len(grouping) == 1 and not isinstance(group_key, tuple):
                group_key = (group_key,)
            row = {grouping[index][1]: _clean_value(group_key[index]) for index in range(len(grouping))}
            for alias, measure, column in measure_fields:
                row[alias] = _aggregate(group[str(column["safe_name"])], measure.aggregation)
            output.append(row)
    else:
        row = {alias: _aggregate(frame[str(column["safe_name"])], measure.aggregation)
               for alias, measure, column in measure_fields}
        output.append(row)

    dimension_fields = [key for key, _ in grouping]
    order_by = plan.order_by
    if order_by:
        output.sort(key=lambda row: tuple(_sort_key(row.get(key)) for key in dimension_fields))
        output.sort(key=lambda row: _sort_key(row.get(order_by.field)),
                    reverse=order_by.direction == "desc")
    elif measure_fields:
        output.sort(key=lambda row: tuple(_sort_key(row.get(key)) for key in dimension_fields))
        output.sort(key=lambda row: _sort_key(row.get(measure_fields[0][0])), reverse=True)
    expected = output[:min(plan.limit, MAX_QUERY_ROWS)]
    passed = _rows_match(actual_rows, expected)
    return {
        "verified": passed,
        "source_rows_after_filters": source_rows,
        "expected_result_rows": len(expected),
        "actual_result_rows": len(actual_rows),
        "verification_method": "independent pandas filter/group/aggregate pass",
    }


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", value):
        raise CopilotUnsupported("Generated SQL identifier is not safe.")
    return '"' + value.replace('"', '""') + '"'


def _coerce_filter_value(value: Any, data_type: str) -> Any:
    try:
        if data_type == "integer":
            integer_result = int(value)
            if isinstance(value, float) and integer_result != value:
                raise ValueError
            return integer_result
        if data_type == "number":
            number_result = float(value)
            if not math.isfinite(number_result):
                raise ValueError
            return number_result
        if data_type == "date":
            timestamp = pd.to_datetime(value, errors="raise", utc=True).tz_convert(None)
            return timestamp.to_pydatetime()
        if data_type == "boolean":
            if isinstance(value, bool):
                return value
            if str(value).casefold() in {"true", "yes", "1"}:
                return True
            if str(value).casefold() in {"false", "no", "0"}:
                return False
            raise ValueError
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError
        return str(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CopilotUnsupported("A filter value does not match its confirmed column type.") from exc


def _bucket_dates(series: pd.Series, grain: str) -> pd.Series:
    dates = pd.to_datetime(series, errors="coerce")
    if grain == "day":
        return dates.dt.normalize()
    if grain == "week":
        return dates.dt.to_period("W-SUN").dt.start_time
    if grain == "month":
        return dates.dt.to_period("M").dt.start_time
    return dates.dt.to_period("Y").dt.start_time


def _aggregate(series: pd.Series, aggregation: str) -> Any:
    values = series.dropna()
    if aggregation == "count":
        return int(values.count())
    if aggregation == "count_distinct":
        return int(values.nunique())
    if values.empty:
        return None
    if aggregation == "sum":
        return _clean_value(values.sum(min_count=1))
    if aggregation == "avg":
        return _clean_value(values.mean())
    if aggregation == "min":
        return _clean_value(values.min())
    return _clean_value(values.max())


def _sort_key(value: Any) -> tuple[int, Any]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return (1, "")
    if isinstance(value, pd.Timestamp):
        return (0, value.isoformat())
    if isinstance(value, (int, float)):
        return (0, float(value))
    return (0, str(value))


def _clean_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _rows_match(actual: list[dict[str, Any]], expected: list[dict[str, Any]]) -> bool:
    if len(actual) != len(expected):
        return False
    for actual_row, expected_row in zip(actual, expected):
        if set(actual_row) != set(expected_row):
            return False
        for key in expected_row:
            left, right = _clean_value(actual_row[key]), _clean_value(expected_row[key])
            if isinstance(left, (int, float)) and not isinstance(left, bool) and isinstance(right, (int, float)):
                if not math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-8):
                    return False
            elif isinstance(left, str) and hasattr(right, "isoformat"):
                if left[:19] != right.isoformat()[:19]:
                    return False
            elif left != right:
                return False
    return True


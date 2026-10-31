"""Typed upload, schema, and query contracts for Business Data Copilot."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

ColumnType = Literal["text", "integer", "number", "date", "boolean"]
ColumnRole = Literal["dimension", "measure", "date", "exclude"]
Aggregate = Literal["sum", "avg", "count", "count_distinct", "min", "max"]
FilterOperator = Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains"]
TimeGrain = Literal["day", "week", "month", "year"]


class ColumnProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    inferred_type: ColumnType
    null_count: int = Field(ge=0)
    invalid_count: int = Field(ge=0)
    cardinality: int = Field(ge=0)
    minimum: JsonValue | None = None
    maximum: JsonValue | None = None
    outlier_count: int = Field(default=0, ge=0)
    suggested_role: ColumnRole


class QualityWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["info", "warning", "high"]
    code: str
    column: str | None = None
    message: str


class UploadProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: str
    filename_label: str
    source_sha256: str
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=1)
    duplicate_rows: int = Field(ge=0)
    columns: list[ColumnProfile]
    warnings: list[QualityWarning]
    preview: list[dict[str, Any]]
    data_label: Literal["SYNTHETIC", "USER_UPLOADED"]


class ColumnConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    data_type: ColumnType
    role: ColumnRole
    sensitive: bool = False


class ConfirmSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: str = Field(min_length=1, max_length=80)
    columns: list[ColumnConfig] = Field(min_length=1, max_length=100)


class MeasurePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1, max_length=120)
    aggregation: Aggregate


class FilterPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1, max_length=120)
    operator: FilterOperator
    value: JsonValue


class OrderPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=140)
    direction: Literal["asc", "desc"] = "desc"


class QueryPlan(BaseModel):
    """Only the compiler turns this validated plan into parameterized SQL."""

    model_config = ConfigDict(extra="forbid")

    measures: list[MeasurePlan] = Field(min_length=1, max_length=8)
    dimensions: list[str] = Field(default_factory=list, max_length=8)
    filters: list[FilterPlan] = Field(default_factory=list, max_length=20)
    time_grain: TimeGrain | None = None
    order_by: OrderPlan | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    assumptions: list[str] = Field(default_factory=list, max_length=12)


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=4, max_length=1000)


class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str
    rows: list[dict[str, Any]]
    chart: dict[str, Any]
    plan: QueryPlan
    assumptions: list[str]
    planner_mode: Literal["deterministic", "llm_planned"]
    provenance: dict[str, Any]
    verified: bool
    verification: dict[str, Any]
    data_label: Literal["SYNTHETIC", "USER_UPLOADED"]


def measure_alias(aggregation: Aggregate, column: dict[str, Any], index: int) -> str:
    """Keep marked-sensitive source names out of result fields and Hub traces."""
    if column.get("sensitive"):
        return f"sensitive_{index + 1}_{aggregation}"
    return f"{aggregation}_{column['safe_name']}"


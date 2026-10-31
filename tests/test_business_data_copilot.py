from __future__ import annotations

import importlib
import asyncio
import io
import zipfile
from pathlib import Path
from typing import Any

import openpyxl
import pandas as pd
import pytest
from alpha_core.agent import AgentIdentity
from fastapi.testclient import TestClient

models = importlib.import_module("tools.business-data-copilot.app.models")
ingest = importlib.import_module("tools.business-data-copilot.app.ingest")
demo = importlib.import_module("tools.business-data-copilot.app.demo")
storage = importlib.import_module("tools.business-data-copilot.app.storage")
planner_module = importlib.import_module("tools.business-data-copilot.app.planner")
query_module = importlib.import_module("tools.business-data-copilot.app.query")
service_module = importlib.import_module("tools.business-data-copilot.app.service")


def identity(user: str = "employee-1", workspace: str = "workspace-a") -> AgentIdentity:
    return AgentIdentity(user_id=user, roles=frozenset({"employee"}), workspace_id=workspace)


def configured_demo(
    store: Any,
    owner: AgentIdentity,
    *,
    frame: pd.DataFrame | None = None,
    sensitive: set[str] | None = None,
) -> models.UploadProfile:
    source = frame if frame is not None else demo.build_demo_frame()
    preview = store.stage_frame(
        owner, source, content=demo.demo_csv_bytes(source), filename_label="synthetic.csv",
        data_label="SYNTHETIC",
    )
    columns = [
        models.ColumnConfig(
            name=column.name,
            data_type=column.inferred_type,
            role=column.suggested_role,
            sensitive=column.name in (sensitive or set()),
        )
        for column in preview.columns
    ]
    store.confirm(owner, models.ConfirmSchema(upload_id=preview.upload_id, columns=columns))
    return preview


def fake_xlsx(*, extra_member: str | None = None) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/worksheets/sheet1.xml", "<worksheet/>")
        if extra_member:
            archive.writestr(extra_member, "blocked")
    return stream.getvalue()


def test_upload_filename_size_and_magic_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    for filename in ("../orders.csv", "C:\\orders.csv", "folder\\orders.csv", "orders\u0301.csv"):
        with pytest.raises(ingest.UploadRejected):
            ingest.safe_extension(filename)
    with pytest.raises(ingest.UploadRejected):
        ingest.parse_upload("orders.xlsx", b"not a zip file")
    with pytest.raises(ingest.UploadRejected):
        ingest.parse_upload("orders.exe", b"x")
    monkeypatch.setattr(ingest, "MAX_UPLOAD_BYTES", 8)
    with pytest.raises(ingest.UploadRejected, match="limited"):
        ingest.parse_upload("orders.csv", b"a,b\n123,456\n")


def test_xlsx_rejects_macro_external_embedded_and_traversal_members() -> None:
    for member in (
        "xl/vbaProject.bin", "xl/externalLinks/externalLink1.xml",
        "xl/embeddings/payload.bin", "xl/../evil.xml", "xl\\..\\evil.xml",
    ):
        with pytest.raises(ingest.UploadRejected):
            ingest.parse_upload("orders.xlsx", fake_xlsx(extra_member=member))


def test_xlsx_formula_is_preserved_as_text_and_not_evaluated() -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["region", "note"])
    sheet.append(["North", "=cmd|\"/C calc\"!A0"])
    stream = io.BytesIO()
    workbook.save(stream)
    frame = ingest.parse_upload("formula.xlsx", stream.getvalue())
    assert frame.iloc[0]["note"] == '=cmd|"/C calc"!A0'


def test_profile_captures_quality_problems_without_hiding_them() -> None:
    dates = ["2025-01-01"] * 11 + ["bad"]
    frame = pd.DataFrame({"date": dates, "units": [-2, -2, *range(10)]})
    columns, warnings, duplicates = ingest.profile_frame(frame)
    assert duplicates == 1
    assert {warning.code for warning in warnings} >= {"duplicate_rows", "negative_numeric"}
    assert any(column.name == "date" and column.invalid_count == 1 for column in columns)


def test_storage_owner_workspace_isolation_and_staged_upload_ownership(tmp_path: Path) -> None:
    store = storage.CopilotStore(tmp_path)
    owner = identity()
    other_user = identity("employee-2")
    other_workspace = identity("employee-1", "workspace-b")
    preview = store.stage_frame(
        owner, demo.build_demo_frame(), content=b"synthetic-only", filename_label="synthetic.csv",
        data_label="SYNTHETIC",
    )
    config = [models.ColumnConfig(name=item.name, data_type=item.inferred_type, role=item.suggested_role)
              for item in preview.columns]
    confirmation = models.ConfirmSchema(upload_id=preview.upload_id, columns=config)
    with pytest.raises(storage.DatasetAccessDenied):
        store.confirm(other_user, confirmation)
    store.confirm(owner, confirmation)
    with pytest.raises(storage.DatasetUnavailable):
        store.manifest(other_user)
    with pytest.raises(storage.DatasetUnavailable):
        store.manifest(other_workspace)


def test_query_plan_is_parameterized_and_only_compiles_known_columns() -> None:
    columns = [
        {"name": "region", "safe_name": "region", "role": "dimension", "data_type": "text", "sensitive": False},
        {"name": "revenue", "safe_name": "revenue", "role": "measure", "data_type": "number", "sensitive": False},
        {"name": "cost", "safe_name": "cost", "role": "measure", "data_type": "number", "sensitive": False},
    ]
    payload = "North' OR 1=1 --"
    plan = models.QueryPlan(
        measures=[models.MeasurePlan(column="revenue", aggregation="sum")],
        filters=[models.FilterPlan(column="region", operator="eq", value=payload)],
    )
    compiled = query_module.compile_query(plan, table_name="d_0123456789abcdef", columns=columns)
    assert payload not in compiled.sql
    assert payload in compiled.parameters
    with pytest.raises(planner_module.CopilotUnsupported):
        planner_module.CopilotPlanner.validate_plan(
            models.QueryPlan(measures=[models.MeasurePlan(column="missing", aggregation="sum")]), columns,
        )
    with pytest.raises(ValueError):
        models.QueryPlan.model_validate({"measures": [{"column": "revenue", "aggregation": "delete"}]})
    with pytest.raises(planner_module.CopilotUnsupported):
        planner_module.CopilotPlanner().plan("delete from the uploaded data", columns)
    with pytest.raises(planner_module.CopilotClarification):
        planner_module.CopilotPlanner().plan("show the total", columns, allow_local_llm=False)


def test_sensitive_date_cannot_be_exposed_through_time_grain() -> None:
    columns = [{
        "name": "private_date", "safe_name": "private_date", "role": "date",
        "data_type": "date", "sensitive": True,
    }, {
        "name": "revenue", "safe_name": "revenue", "role": "measure",
        "data_type": "number", "sensitive": False,
    }]
    plan = models.QueryPlan(
        measures=[models.MeasurePlan(column="revenue", aggregation="sum")], time_grain="month",
    )
    with pytest.raises(planner_module.CopilotClarification):
        planner_module.CopilotPlanner.validate_plan(plan, columns)
    with pytest.raises(planner_module.CopilotUnsupported):
        query_module.compile_query(plan, table_name="d_0123456789abcdef", columns=columns)


def test_agent_hub_registers_copilot_tools_and_routes_owner_dataset_questions() -> None:
    hub = importlib.import_module("alpha_app.agent_hub")
    assert "copilot.profile" in hub.TOOL_NAMES
    assert "copilot.query" in hub.TOOL_NAMES
    plan = hub.deterministic_plan("Show revenue by region in my uploaded dataset")
    assert [step.tool_name for step in plan.steps] == ["copilot.query"]
    sensitive_plan = hub.deterministic_plan("Sum salary in my uploaded dataset")
    assert [step.tool_name for step in sensitive_plan.steps] == ["copilot.query"]


def test_column_name_is_compiled_to_a_safe_identifier(tmp_path: Path) -> None:
    hostile = 'revenue"; DROP TABLE d_0123456789abcdef--'
    frame = pd.DataFrame({hostile: [2.0, 5.0], "region": ["North", "South"]})
    store = storage.CopilotStore(tmp_path)
    owner = identity()
    preview = store.stage_frame(owner, frame, content=b"synthetic-fixture", filename_label="fixture.csv")
    store.confirm(owner, models.ConfirmSchema(upload_id=preview.upload_id, columns=[
        models.ColumnConfig(name=hostile, data_type="number", role="measure"),
        models.ColumnConfig(name="region", data_type="text", role="dimension"),
    ]))
    manifest = store.manifest(owner)
    safe = manifest["columns"][0]["safe_name"]
    assert safe.isidentifier()
    plan = models.QueryPlan(measures=[models.MeasurePlan(column=hostile, aggregation="sum")])
    compiled = query_module.compile_query(plan, table_name=manifest["table_name"], columns=manifest["columns"])
    assert hostile not in compiled.sql


def test_sensitive_aggregate_is_deterministic_redacted_and_not_in_hub_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frame = pd.DataFrame({
        "region": ["North", "South", "North"], "salary": [100.0, 200.0, 300.0],
    })
    store = storage.CopilotStore(tmp_path)
    owner = identity()
    configured_demo(store, owner, frame=frame, sensitive={"salary"})
    calls = 0
    planner = planner_module.CopilotPlanner()

    def should_not_call_local_model() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(planner_module, "get_provider", should_not_call_local_model)
    service = service_module.CopilotService(store, planner)
    redacted_plans: list[dict[str, Any]] = []
    original_audit = store.audit

    def capture_audit(identity_arg: AgentIdentity, **kwargs: Any) -> None:
        redacted_plans.append(kwargs.get("plan", {}))
        original_audit(identity_arg, **kwargs)

    monkeypatch.setattr(store, "audit", capture_audit)
    result = service.query(owner, "total salary by region")
    serialized = str({"plan": result["plan"], "rows": result["rows"], "audit": redacted_plans})
    assert result["verified"] is True
    assert "salary" not in serialized.casefold()
    assert "sensitive_1_sum" in result["rows"][0]
    assert calls == 0
    hub_profile = store.profile_for_hub(owner)
    assert all(column["name"] != "salary" for column in hub_profile["columns"])
    owner_profile = store.profile(owner)
    assert all("salary" not in row for row in owner_profile["preview"])


def test_pandas_verifier_detects_tampered_result(tmp_path: Path) -> None:
    store = storage.CopilotStore(tmp_path)
    owner = identity()
    configured_demo(store, owner)
    service = service_module.CopilotService(store)
    result = service.query(owner, "total revenue by region")
    manifest = store.manifest(owner)
    source = store.read_frame(owner, manifest)
    plan, _mode = planner_module.CopilotPlanner().plan(
        "total revenue by region", manifest["columns"], profile=store.profile_for_hub(owner),
        allow_local_llm=False,
    )
    tampered = [dict(row) for row in result["rows"]]
    tampered[0]["sum_revenue"] = float(tampered[0]["sum_revenue"]) + 1
    check = query_module.verify_with_pandas(source, plan, columns=manifest["columns"], actual_rows=tampered)
    assert check["verified"] is False


def test_csv_formula_escaping_preserves_numeric_values() -> None:
    assert service_module._csv_value("=1+1") == "'=1+1"
    assert service_module._csv_value("   =1+1") == "'   =1+1"
    assert service_module._csv_value("-4") == "'-4"
    assert service_module._csv_value(-4) == -4


def test_monthly_trend_is_sorted_by_time_and_verified(tmp_path: Path) -> None:
    store = storage.CopilotStore(tmp_path)
    owner = identity()
    configured_demo(store, owner)
    result = service_module.CopilotService(store).query(owner, "Show monthly revenue trend")
    assert result["verified"] is True
    assert result["chart"]["type"] == "line"
    dates = [row["date_month"] for row in result["rows"]]
    assert dates == sorted(dates)


def test_verified_export_escapes_formula_like_dimension_values(tmp_path: Path) -> None:
    frame = pd.DataFrame({"label": ["=1+1", "+cmd"], "amount": [3, 4]})
    store = storage.CopilotStore(tmp_path)
    owner = identity()
    configured_demo(store, owner, frame=frame)
    service = service_module.CopilotService(store)
    result = service.query(owner, "total amount by label")
    exported = service.export_csv(owner, result["query_id"]).decode("utf-8-sig")
    assert "'=1+1" in exported and "'+cmd" in exported


def test_authenticated_api_requires_csrf_and_runs_synthetic_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("tools.business-data-copilot.app.main")
    store = storage.CopilotStore(tmp_path)
    user = {"id": "test-user", "username": "analyst", "role": "employee", "groups": [], "workspace_id": "test-workspace"}

    class TestCodec:
        def issue_csrf(self, subject: str) -> str:
            assert subject == user["id"]
            return "csrf-ok"

        def verify_csrf(self, token: str, subject: str) -> None:
            if token != "csrf-ok" or subject != user["id"]:
                raise importlib.import_module("alpha_core.auth").InvalidCsrfToken("bad token")

    class KnowledgeModule:
        @staticmethod
        def _session_codec() -> TestCodec:
            return TestCodec()

    monkeypatch.setattr(main, "STORE", store)
    monkeypatch.setattr(main, "SERVICE", service_module.CopilotService(store))
    monkeypatch.setattr(main, "_knowledge_module", lambda: KnowledgeModule())
    main.app.dependency_overrides[main.authenticated_user] = lambda: user
    try:
        with TestClient(main.app) as client:
            denied = client.post("/api/demo")
            assert denied.status_code == 403
            headers = {"X-CSRF-Token": "csrf-ok", "X-User-ID": "forged-user", "X-Workspace-ID": "forged-workspace"}
            staged = client.post("/api/demo", headers=headers)
            assert staged.status_code == 200
            data = staged.json()
            columns = [{
                "name": item["name"], "data_type": item["inferred_type"],
                "role": item["suggested_role"], "sensitive": False,
            } for item in data["columns"]]
            confirmed = client.post("/api/confirm", headers=headers, json={
                "upload_id": data["upload_id"], "columns": columns,
            })
            assert confirmed.status_code == 200
            result = client.post("/api/query", headers=headers, json={"question": "Show monthly revenue by region"})
            assert result.status_code == 200
            assert result.json()["verified"] is True
            export = client.get(f"/api/export/{result.json()['query_id']}.csv")
            assert export.status_code == 200
            assert export.headers["content-type"].startswith("text/csv")
            uploaded = client.post(
                "/api/upload", headers=headers,
                files={"file": ("small.csv", b"region,revenue\nNorth,12\nSouth,7\n", "text/csv")},
            )
            assert uploaded.status_code == 200
            assert uploaded.json()["filename_label"] == "small.csv"
    finally:
        main.app.dependency_overrides.clear()


def test_upload_body_middleware_stops_large_stream_before_form_parsing() -> None:
    main = importlib.import_module("tools.business-data-copilot.app.main")
    sent: list[dict[str, Any]] = []
    called = False

    async def downstream(scope: Any, receive: Any, send: Any) -> None:
        nonlocal called
        called = True
        await receive()

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"123456", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/api/upload", "headers": []}
    middleware = main.UploadBodyLimit(downstream, max_bytes=5)
    asyncio.run(middleware(scope, receive, send))
    starts = [message for message in sent if message["type"] == "http.response.start"]
    assert called
    assert starts and starts[0]["status"] == 413

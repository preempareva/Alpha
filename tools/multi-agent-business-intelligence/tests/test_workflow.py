from importlib import import_module
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ALPHA_ROOT = ROOT.parents[1]
workflow = import_module("tools.multi-agent-business-intelligence.app.workflow")


@pytest.fixture(autouse=True)
def seeded():
    subprocess.run([sys.executable, "-m", "tools.multi-agent-business-intelligence.scripts.seed_data"], cwd=ALPHA_ROOT, check=True, capture_output=True)


def test_monthly_result_passes_verifier():
    result = workflow.run_workflow("Show monthly revenue")
    assert result["status"] == "complete"
    assert len(result["rows"]) == 12
    assert [s["agent"] for s in result["trace"]] == ["router", "router", "sql_analyst", "verifier", "report_writer"]


def test_unsupported_question_is_rejected():
    with pytest.raises(ValueError):
        workflow.run_workflow("Tell me customer names")


def test_query_only_connection_rejects_writes():
    with workflow.connect_readonly() as db:
        with pytest.raises(Exception):
            db.execute("DELETE FROM orders")


def test_result_row_cap_is_enforced():
    assert all(len(workflow.run_workflow(q)["rows"]) <= workflow.MAX_ROWS for q in ["top products", "refund rates"])

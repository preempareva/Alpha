from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(__import__("os").getenv("BI_DATABASE_PATH", str(ROOT / "data/runtime/retail.db")))
MAX_STEPS = 5
MAX_ROWS = 20

TOOLS = {
    "monthly_revenue": {
        "description": "Monthly gross and net revenue from completed synthetic orders",
        "sql": "SELECT substr(order_date,1,7) AS month, ROUND(SUM(gross),2) AS gross_revenue, ROUND(SUM(gross-refund),2) AS net_revenue FROM orders GROUP BY month ORDER BY month LIMIT ?",
    },
    "top_products": {
        "description": "Top products by units sold",
        "sql": "SELECT product, SUM(quantity) AS units, ROUND(SUM(gross-refund),2) AS net_revenue FROM orders GROUP BY product ORDER BY units DESC LIMIT ?",
    },
    "refund_rate": {
        "description": "Refund rate by product category",
        "sql": "SELECT category, ROUND(SUM(refund)*100.0/NULLIF(SUM(gross),0),2) AS refund_percent, COUNT(*) AS order_lines FROM orders GROUP BY category ORDER BY refund_percent DESC LIMIT ?",
    },
}


@contextmanager
def connect_readonly():
    if not DB_PATH.exists():
        raise FileNotFoundError("Synthetic warehouse missing; run scripts/seed_data.py first.")
    db = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.set_authorizer(authorizer)
    try:
        yield db
    finally:
        db.close()


def authorizer(action, arg1, arg2, db_name, trigger):
    # All writes, schema changes, attach and pragmas are rejected; reads limited to orders.
    if action in {sqlite3.SQLITE_READ} and arg1 == "orders":
        return sqlite3.SQLITE_OK
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def route(question: str) -> str:
    q = question.lower()
    if any(t in q for t in ("month", "monthly", "revenue", "sales trend")):
        return "monthly_revenue"
    if any(t in q for t in ("top", "best", "most", "product")):
        return "top_products"
    if any(t in q for t in ("refund", "return")):
        return "refund_rate"
    raise ValueError("I can answer monthly revenue, top products, or refund-rate questions from this demo dataset.")


def run_workflow(question: str) -> dict:
    if len(question.strip()) < 4 or len(question) > 500:
        raise ValueError("Question must be between 4 and 500 characters.")
    trace = [{"agent": "router", "state": "started"}]
    tool = route(question)
    trace.append({"agent": "router", "state": "selected_tool", "tool": tool})
    if len(trace) >= MAX_STEPS:
        raise RuntimeError("Workflow step budget exceeded.")
    definition = TOOLS[tool]
    with connect_readonly() as db:
        rows = [dict(r) for r in db.execute(definition["sql"], (MAX_ROWS,)).fetchall()]
    trace.append({"agent": "sql_analyst", "state": "query_complete", "rows": len(rows), "tool": tool})
    verified = bool(rows) and len(rows) <= MAX_ROWS and all(isinstance(r, dict) for r in rows)
    if tool == "monthly_revenue":
        verified = verified and all(float(r["net_revenue"]) <= float(r["gross_revenue"]) for r in rows)
    if not verified:
        trace.append({"agent": "verifier", "state": "rejected"})
        return {"status": "needs_review", "answer": "The result did not pass verification.", "rows": [], "trace": trace}
    trace.append({"agent": "verifier", "state": "verified"})
    description = definition["description"]
    summary = f"{description}: {len(rows)} grouped result(s). Values are calculated from the synthetic demo warehouse."
    trace.append({"agent": "report_writer", "state": "complete"})
    return {"status": "complete", "answer": summary, "tool": tool, "rows": rows, "trace": trace,
            "disclaimer": "Synthetic demonstration; not a business performance claim."}

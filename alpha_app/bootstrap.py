"""Create ignored demo assets from their source scripts when a fresh clone needs them."""

from __future__ import annotations

import subprocess
import sys
import sqlite3
import json
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
SETUP = (
    ("customer-churn-prediction", "artifacts/churn_pipeline.joblib", ("generate_data", "train")),
    ("customer-sentiment-intelligence", "artifacts/sentiment.joblib", ("generate_data", "train")),
    ("sales-pipeline-forecasting", "artifacts/sales.joblib", ("generate_data", "train")),
    ("customer-segmentation-agent", "data/generated/transactions.csv", ("generate_data",)),
    ("intelligent-inventory-forecasting", "data/generated/demand.csv", ("generate_data",)),
    ("inventory-optimization-agent", "data/generated/weekly_sales.csv", ("generate_data",)),
    ("multi-agent-business-intelligence", "data/runtime/retail.db", ("seed_data",)),
    ("enterprise-knowledge-assistant", "instance/knowledge.db", ("seed_demo",)),
)


def seed_missing() -> None:
    for project, check, scripts in SETUP:
        project_root = ROOT / "tools" / project
        asset = project_root / check
        needs_seed = not asset.exists()
        if project == "enterprise-knowledge-assistant" and asset.exists():
            try:
                with sqlite3.connect(asset) as db:
                    count = db.execute("SELECT count(*) FROM documents WHERE active=1").fetchone()[0]
                needs_seed = count < 30
            except sqlite3.Error:
                needs_seed = True
        if not needs_seed:
            continue
        for script in scripts:
            module = f"tools.{project}.scripts.{script}"
            subprocess.run([sys.executable, "-m", module], cwd=ROOT, check=True)
    questions = ROOT / "tools" / "enterprise-knowledge-assistant" / "data" / "evaluation" / "questions.json"
    try:
        needs_questions = len(json.loads(questions.read_text(encoding="utf-8"))) < 100
    except (OSError, ValueError):
        needs_questions = True
    if needs_questions:
        subprocess.run([sys.executable, "-m", "tools.enterprise-knowledge-assistant.scripts.build_questions"], cwd=ROOT, check=True)


if __name__ == "__main__":
    seed_missing()

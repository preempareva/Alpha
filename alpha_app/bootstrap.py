"""Create ignored demo assets from their source scripts when a fresh clone needs them."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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
        if (project_root / check).exists():
            continue
        for script in scripts:
            module = f"tools.{project}.scripts.{script}"
            subprocess.run([sys.executable, "-m", module], cwd=ROOT, check=True)


if __name__ == "__main__":
    seed_missing()

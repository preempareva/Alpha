"""Regenerate ignored synthetic demo assets in a clean Project Alpha checkout.

This deliberately refuses to overwrite any expected generated asset. Run it in a
fresh clone or clean temporary checkout, not over an existing local workspace.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEPS = (
    ("tools.customer-churn-prediction.scripts.generate_data", "tools/customer-churn-prediction/data/generated/customer_snapshots.csv"),
    ("tools.customer-churn-prediction.scripts.train", "tools/customer-churn-prediction/artifacts/churn_pipeline.joblib"),
    ("tools.customer-sentiment-intelligence.scripts.generate_data", "tools/customer-sentiment-intelligence/data/generated/reviews.csv"),
    ("tools.customer-sentiment-intelligence.scripts.train", "tools/customer-sentiment-intelligence/artifacts/sentiment.joblib"),
    ("tools.sales-pipeline-forecasting.scripts.generate_data", "tools/sales-pipeline-forecasting/data/generated/opportunities.csv"),
    ("tools.sales-pipeline-forecasting.scripts.train", "tools/sales-pipeline-forecasting/artifacts/sales.joblib"),
    ("tools.customer-segmentation-agent.scripts.generate_data", "tools/customer-segmentation-agent/data/generated/transactions.csv"),
    ("tools.intelligent-inventory-forecasting.scripts.generate_data", "tools/intelligent-inventory-forecasting/data/generated/demand.csv"),
    ("tools.inventory-optimization-agent.scripts.generate_data", "tools/inventory-optimization-agent/data/generated/weekly_sales.csv"),
    ("tools.inventory-optimization-agent.scripts.generate_tower_data", "tools/inventory-optimization-agent/data/generated/tower/sales_history.csv"),
    ("tools.multi-agent-business-intelligence.scripts.seed_data", "tools/multi-agent-business-intelligence/data/runtime/retail.db"),
    ("tools.enterprise-knowledge-assistant.scripts.seed_demo", "tools/enterprise-knowledge-assistant/instance/knowledge.db"),
    ("tools.business-data-copilot.scripts.generate_demo", "data/generated/demo_orders.csv"),
)


def main() -> int:
    env = os.environ.copy()
    env.update({
        "PYTHON_DOTENV_DISABLED": "1",
        "LLM_PROVIDER": "none",
        "BI_DATABASE_PATH": str(ROOT / "tools/multi-agent-business-intelligence/data/runtime/retail.db"),
        "DATABASE_PATH": str(ROOT / "tools/enterprise-knowledge-assistant/instance/knowledge.db"),
        "ALPHA_DEMO_ALICE_PASSWORD": secrets.token_urlsafe(24),
        "ALPHA_DEMO_BOB_PASSWORD": secrets.token_urlsafe(24),
        "ALPHA_DEMO_ADMIN_PASSWORD": secrets.token_urlsafe(24),
    })
    existing = [relative for _, relative in STEPS if (ROOT / relative).exists()]
    if existing:
        print("Refusing to overwrite existing generated assets:", file=sys.stderr)
        for relative in existing:
            print(f"  {relative}", file=sys.stderr)
        print("Run from a fresh clone or clean temporary checkout.", file=sys.stderr)
        return 2

    for module, expected in STEPS:
        print(f"Generating {expected}")
        subprocess.run([sys.executable, "-m", module], cwd=ROOT, env=env, check=True)
        if not (ROOT / expected).is_file():
            raise RuntimeError(f"Generator {module} did not create its expected output: {expected}")
    print(f"Generated {len(STEPS)} synthetic demo assets; generated contents were not inspected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

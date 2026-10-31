from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    demo = importlib.import_module("tools.business-data-copilot.app.demo")
    target = ROOT / "data" / "generated" / "demo_orders.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    demo.build_demo_frame().to_csv(target, index=False, date_format="%Y-%m-%d")
    print("Wrote the SYNTHETIC demo dataset to the ignored data/generated folder.")

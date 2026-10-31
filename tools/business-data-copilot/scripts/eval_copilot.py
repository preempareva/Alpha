from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    evaluation = importlib.import_module("tools.business-data-copilot.app.evaluation")
    metrics = evaluation.run_copilot_evaluation(ROOT / "docs" / "eval")
    print(
        f"Copilot evaluation: {metrics['questions_passed']}/{metrics['question_count']} questions; "
        f"refusals {metrics['refusal_correctness']:.4f}; "
        f"verifier catch {metrics['verifier_tamper_catch_rate']:.4f}."
    )

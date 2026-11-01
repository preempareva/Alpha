"""Run the authored retrieval benchmark and persist only measured results."""

from __future__ import annotations

import json
import os
from datetime import date
from importlib import import_module
from pathlib import Path
import sys

os.environ["LLM_PROVIDER"] = "none"
module = import_module("tools.enterprise-knowledge-assistant.app.main")
AskRequest, retrieve = module.AskRequest, module.retrieve
ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
THRESHOLDS = json.loads((PROJECT_ROOT / "docs" / "eval" / "thresholds.json").read_text(encoding="utf-8"))["knowledge"]
MIN_RECALL_AT_5 = THRESHOLDS["min_recall_at_5"]
MIN_ABSTENTION_ACCURACY = THRESHOLDS["min_abstention_accuracy"]
MAX_ACL_LEAKAGE_RATE = THRESHOLDS["max_acl_leakage_rate"]
cases = json.loads((ROOT / "data/evaluation/questions.json").read_text(encoding="utf-8"))

answerable_hits = []
reciprocal_ranks = []
correct_citations = 0
returned_citations = 0
abstention_results = []
acl_cases = []
expired_leaks = 0
type_totals: dict[str, list[bool]] = {}

with module.connect() as db:
    document_count = db.execute("SELECT count(*) FROM documents WHERE active=1").fetchone()[0]
if document_count < 30:
    raise SystemExit(f"Seed the 30-document synthetic corpus first; found {document_count} documents.")

for case in cases:
    user = {"id": "synthetic-evaluator", "groups": case["user_groups"]}
    result = retrieve(AskRequest(question=case["question"], limit=5), user)
    filenames = [citation["filename"] for citation in result["citations"]]
    expected_file = case.get("expected_file")
    if case["answerable"] and expected_file:
        hit = expected_file in filenames
        answerable_hits.append(float(hit))
        reciprocal_ranks.append(1 / (filenames.index(expected_file) + 1) if hit else 0.0)
        correct_citations += sum(filename == expected_file for filename in filenames)
        returned_citations += len(filenames)
    if result["abstained"] == case["expected_abstain"]:
        abstention_results.append(True)
    else:
        abstention_results.append(False)
    type_totals.setdefault(case["type"], []).append(result["abstained"] == case["expected_abstain"])
    if case["type"] == "cross-group-attack":
        acl_cases.append(float(expected_file in filenames))
    if case.get("excluded_file") and case["excluded_file"] in filenames:
        expired_leaks += 1

metrics = {
    "run_date": date.today().isoformat(),
    "dataset": "authored synthetic 30-document corpus",
    "cases": len(cases),
    "case_types": {name: len(values) for name, values in type_totals.items()},
    "recall_at_5": round(sum(answerable_hits) / max(1, len(answerable_hits)), 4),
    "mrr_at_5": round(sum(reciprocal_ranks) / max(1, len(reciprocal_ranks)), 4),
    "citation_precision": round(correct_citations / max(1, returned_citations), 4),
    "abstention_accuracy": round(sum(abstention_results) / max(1, len(abstention_results)), 4),
    "acl_leakage_rate": round(sum(acl_cases) / max(1, len(acl_cases)), 4),
    "expired_version_leaks": expired_leaks,
    "by_case_type_accuracy": {name: round(sum(values) / len(values), 4) for name, values in type_totals.items()},
    "limitations": [
        "All 30 source documents are fictional and authored for this demo.",
        "The benchmark is a small local retrieval check, not enterprise answer quality or real user performance.",
        "LLM synthesis is disabled for this run; no Ollama availability is assumed.",
        "Citation precision treats the single labelled source file as the relevant target.",
    ],
}
metrics["thresholds"] = {
    "minimum_recall_at_5": MIN_RECALL_AT_5,
    "minimum_abstention_accuracy": MIN_ABSTENTION_ACCURACY,
    "maximum_acl_leakage_rate": MAX_ACL_LEAKAGE_RATE,
    "maximum_expired_version_leaks": THRESHOLDS["max_expired_version_leaks"],
}
metrics["passed"] = (
    metrics["recall_at_5"] >= MIN_RECALL_AT_5
    and metrics["abstention_accuracy"] >= MIN_ABSTENTION_ACCURACY
    and metrics["acl_leakage_rate"] <= MAX_ACL_LEAKAGE_RATE
    and metrics["expired_version_leaks"] <= THRESHOLDS["max_expired_version_leaks"]
)

lines = [
    "# Knowledge Assistant retrieval evaluation",
    "",
    f"Measured on **{metrics['run_date']}** using {metrics['cases']} authored questions over the seeded synthetic corpus.",
    "The run uses deterministic FTS5 retrieval with LLM synthesis disabled.",
    "",
    "| Measure | Result |",
    "|---|---:|",
    f"| Recall@5 | {metrics['recall_at_5']:.4f} |",
    f"| MRR@5 | {metrics['mrr_at_5']:.4f} |",
    f"| Citation precision | {metrics['citation_precision']:.4f} |",
    f"| Abstention accuracy | {metrics['abstention_accuracy']:.4f} |",
    f"| ACL leakage rate | {metrics['acl_leakage_rate']:.4f} |",
    f"| Expired-version citations | {metrics['expired_version_leaks']} |",
    "",
    "## Cases",
    "",
]
lines.extend(f"- {name}: {count}" for name, count in metrics["case_types"].items())
lines.extend(["", "## Limits", ""])
lines.extend(f"- {item}" for item in metrics["limitations"])
(ROOT / "docs" / "eval_knowledge.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
report_path = ROOT / "data" / "evaluation" / "ci_report.json"
report_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
print(json.dumps(metrics, indent=2))
if not metrics["passed"]:
    print("Knowledge retrieval evaluation is below the recorded baseline.", file=sys.stderr)
    raise SystemExit(1)

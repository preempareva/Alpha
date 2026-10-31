import json
from pathlib import Path
from importlib import import_module

module = import_module("tools.enterprise-knowledge-assistant.app.main")
AskRequest, ask = module.AskRequest, module.ask

ROOT = Path(__file__).resolve().parents[1]
cases = json.loads((ROOT / "data/evaluation/questions.json").read_text(encoding="utf-8"))
recalls, reciprocal_ranks, abstain_ok = [], [], []
for case in cases:
    result = ask(AskRequest(question=case["question"], limit=5), "alice", "general,finance,hr")
    files = [c["filename"] for c in result["citations"]]
    if case["expected_file"]:
        recalls.append(float(case["expected_file"] in files))
        reciprocal_ranks.append(1 / (files.index(case["expected_file"]) + 1) if case["expected_file"] in files else 0)
    else:
        abstain_ok.append(float(result["abstained"]))
print(f"Known-answer Recall@5: {sum(recalls)/len(recalls):.3f}")
print(f"Known-answer MRR@5: {sum(reciprocal_ranks)/len(reciprocal_ranks):.3f}")
print(f"No-answer abstention: {sum(abstain_ok)/len(abstain_ok):.3f}")

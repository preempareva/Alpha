from pathlib import Path
from importlib import import_module

module = import_module("tools.enterprise-knowledge-assistant.app.main")
init_db, ingest = module.init_db, module.ingest
seed_demo_users = module.seed_demo_users

ROOT = Path(__file__).resolve().parents[1]
init_db()
seed_demo_users()
fixtures = [
    ("travel-policy.md", "Travel Policy", "general,finance"),
    ("security-guide.md", "Account Security Guide", "general"),
    ("hr-benefits.md", "Benefits Enrollment Guide", "hr"),
]
for filename, title, groups in fixtures:
    result = ingest(filename, (ROOT / "data" / "synthetic" / filename).read_bytes(), title,
                    "Demo Knowledge Owner", "1", groups.split(","), None, None)
    print(f"{title}: {result['status']} ({result['chunks']} chunks)")

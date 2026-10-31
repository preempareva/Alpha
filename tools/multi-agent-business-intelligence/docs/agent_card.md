# BI Analyst Workflow card

- **Purpose:** Answer three limited synthetic retail analysis intents and return a traceable table.
- **Workflow steps:** Intent router, SQL analyst, independent result verifier, report writer.
- **Tools:** Three fixed parameterized SELECT statements. No user-supplied SQL, external side effects, or arbitrary tool selection.
- **Controls:** SQLite `mode=ro`, authorizer allowlist, bounded question length, fixed row limit, maximum four-step workflow, output verification.
- **Evaluation:** Unit checks cover happy path, unsupported intent, write denial, and result row cap.
- **Limitations:** Deterministic routing rather than model planning; schema is fixed and synthetic; no user authentication, privacy boundary, or operational observability.

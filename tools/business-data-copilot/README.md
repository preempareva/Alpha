# Business Data Copilot

Business Data Copilot adds a guided, read-only workflow to Alpha for small CSV and XLSX files. It profiles the upload, lets the signed-in user confirm column types and roles, and answers bounded analytics questions with parameterized DuckDB queries plus a separate pandas verification pass.

## Run

From the Project Alpha folder, start the existing workspace with ./run.ps1 in PowerShell (or ./run.sh on macOS/Linux).

Open the Business Data Copilot card. Sign in with the same Knowledge Assistant account used by Alpha, then choose Use synthetic demo or upload a .csv or .xlsx file. Review the inferred schema, mark sensitive columns, and confirm it before asking a question.

Example questions include:
- Show monthly revenue by region
- Average cost by product
- Total units by channel
- Total revenue for the last 6 months by region

The deterministic planner is the default. An optional local Ollama planner can be enabled with LLM_PROVIDER=ollama and COPILOT_LOCAL_PLANNER=1; it sees confirmed nonsensitive column names/types and sample-free profiling statistics only. It never receives uploaded row samples or marked-sensitive schema fields. Paid or remote LLM providers are not supported.

## Limits and data handling

- Default upload limit: 10 MiB (COPILOT_MAX_UPLOAD_BYTES may be set from 1 byte through 50 MiB).
- At most 50,000 rows and 100 columns; cells are capped at 10,000 characters.
- XLSX expanded content is capped at 50 MiB. Macro projects, external links, embedded objects, and unsafe ZIP paths are rejected.
- Workbook formulas are read as formula text; Alpha does not calculate them.
- Preview staging remains in process memory for 15 minutes and is capped at 100 MiB across the process.
- Confirmed tables are stored in instance/workspaces/<opaque-workspace-hash>/copilot.duckdb; queries open this store read-only. Data expires after 30 days. Query audit metadata expires after 90 days.
- Sensitive columns are hidden from planning prompts, previews after confirmation, grouping, filtering, Hub profile output, and result labels. An explicit aggregate can be computed by deterministic code; the source name is redacted from its returned plan and audit record.
- Every successful result must match an independent pandas calculation. A mismatch is withheld. Query results are capped at 500 rows and 750 KiB. CSV text cells beginning with spreadsheet formula characters are escaped.
- Data is not encrypted by Copilot at rest. Protect the host account and use full-disk encryption when storing private files. This local demo does not provide multi-user enterprise hosting or a distributed worker setup.

See docs/ for the data card, agent card, threat model, runbook, and demo script. See docs/eval/copilot.md for the measured synthetic evaluation and its limits.

# Business Data Copilot runbook

## Start the workspace

From the Project Alpha root, run ./run.ps1 in PowerShell (or ./run.sh on macOS/Linux). Open the Business Data Copilot card in the Alpha shell. Sign in with a Knowledge Assistant user; Alpha's local demo credentials are printed once during the first seed unless chosen through the demo password environment variables.

## Analyze a file

1. Choose a .csv or .xlsx file no larger than 10 MiB by default.
2. Review the inferred columns, types, null counts, and preview.
3. Set each column's type and role. Mark sensitive fields before confirming.
4. Confirm the schema. The file is loaded to the user's workspace table.
5. Ask a question such as Show monthly revenue by region or Average cost by product.
6. Review the verification badge, plan, assumptions, and dataset hash. Download a result CSV if needed.

The Use synthetic demo action is the easiest smoke path. The demo is generated in memory with a fixed seed and carries the SYNTHETIC label.

## Environment

- COPILOT_MAX_UPLOAD_BYTES: default 10485760, allowed 1 byte through 50 MiB.
- COPILOT_DATA_ROOT: default <project-root>/instance/workspaces.
- COPILOT_LOCAL_PLANNER: default 0; set to 1 only to permit schema-only local planning.
- LLM_PROVIDER: defaults to none. For optional local planning, use the shared Ollama provider; paid or remote providers are unsupported.

Confirmed dataset tables expire after 30 days; query audits after 90 days. The next Copilot request checks manifest expiry, and application startup purges expired tables. There is no automated backup or external sync.

## Troubleshooting

- Sign-in required: sign in through Copilot or the Knowledge Assistant using the local demo account.
- File rejected: save as UTF-8 CSV or a normal .xlsx workbook; remove macros, external links, or embedded objects; check the byte/row/column limits.
- Need to correct the schema: upload the source file again and confirm it with updated types and roles.
- Question needs clarification: name a confirmed numeric measure and grouping dimension, for example Total revenue by region.
- Query refused: arbitrary SQL, write requests, sensitive filters, and unsupported filters are intentionally unavailable.
- Dataset expired: upload or stage the synthetic demo again and confirm its schema.

## Maintenance checks

From the Project Alpha root, run the following:

    python -m pytest tests/test_business_data_copilot.py -q
    python tools/business-data-copilot/scripts/eval_copilot.py

Evaluation writes only task statuses, counts, and expected-result hashes to docs/eval/copilot.*; it does not store generated result rows.

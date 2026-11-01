# Project Alpha

Project Alpha is one local workspace for fourteen focused AI and analytics demos. Each tool has its own guided screen and API; the Alpha shell adds signed-session access, a cross-tool Hub, and reviewable local workflows.

## Run it

CI targets Python 3.12 and 3.13. The current development environment also runs on Python 3.14.

**Windows:** open PowerShell in this folder and run:

```powershell
./run.ps1
```

**macOS/Linux:** run:

```sh
chmod +x ./run.sh   # first run only
./run.sh
```

Then open <http://127.0.0.1:8000>. The launch script uses `../EXtra/project-alpha-support/.venv` and installs pinned dependencies on first run. In this Projects workspace, ignored runtime tables, model artifacts, and caches are kept under that support folder and exposed at their expected paths; a clean clone regenerates its own ignored demo assets. Press Ctrl+C in the terminal to stop the server.

## What each tool actually does

| Product | Data | Method and side effects |
|---|---|---|
| Business Data Copilot | A local CSV/XLSX upload or fixed-seed SYNTHETIC sample | Deterministic DuckDB query planning with a separate pandas check; optional local Ollama planner is off by default. Read-only analysis; confirmed uploads are stored locally and are not encrypted at rest. |
| Knowledge Assistant | Fictional authored policy and procedure documents, or documents supplied by the local user | SQLite FTS5 retrieval; optional local Ollama embeddings use a 0.6 lexical / 0.4 vector score. ACL and expiry filters apply before results. Answer synthesis is off by default. |
| Helpdesk Triage | Fictional requests and authored knowledge snippets | Deterministic classification and matching. Creates a local `NEEDS_REVIEW` ticket draft; there is no ITSM, account, or device integration. |
| Travel Itinerary Planner | Fictional activity catalog and user-entered trip constraints | Deterministic constraint ranking. An explicit weather lookup calls Open-Meteo; it does not book or pay for travel. |
| Demand Forecasting | Fixed-seed SYNTHETIC weekly demand | Last-eight-week average compared with a last-value baseline. It does not represent stock on hand or make purchase decisions. |
| Customer Churn Prediction | Fixed-seed SYNTHETIC subscription snapshots | Calibrated logistic-regression model and temporal holdout. Scores are review signals; there is no outreach. |
| Sales Pipeline Forecast | Fixed-seed SYNTHETIC opportunities | Calibrated logistic-regression scoring over a temporal holdout. Weighted pipeline is not committed revenue; there is no CRM write. |
| Customer Sentiment Insights | Fixed-seed SYNTHETIC reviews | TF-IDF plus logistic-regression baseline and keyword themes. No real customer feedback is included. |
| BI Analyst Workflow | Fixed-seed SYNTHETIC retail orders | Fixed read-only query catalogue, deterministic planning by default, optional local Ollama tool planning, and independent numeric verification. |
| Inventory Control Tower | Fixed-seed SYNTHETIC sales, stock, supplier, purchase-order, transfer, and policy tables | Naive, seasonal-naive, moving-average, ETS, and Croston SBA forecasts; decimal stock rules and seeded scenarios. Replenishment is a local draft requiring persisted review; execution is simulated. |
| Sales Follow-up Prioritizer | Fictional CRM opportunities | Transparent recency and engagement rules. Creates a message draft; there is no email or CRM integration. |
| Incident Evidence Correlator (synthetic) | Generated fictional metric, log, and trace events | Deterministic evidence correlation and hypotheses. It does not connect to a live telemetry service or change infrastructure. |
| Supplier Quote Comparison | User-entered or sample quote terms | Deterministic landed-cost calculations and explicit comparison weights. It does not award a contract or contact suppliers. |
| Customer Segmentation | Fixed-seed SYNTHETIC transactions | RFM features and k-means clustering; returns aggregate profiles and does not target individuals. |

The optional shared LLM adapter supports local Ollama only and defaults to `LLM_PROVIDER=none`. The Hub uses registered tools with bounded arguments and independent checks; it cannot run arbitrary code, SQL, or external writes.

## Use the workspace

- Start at the overview. Search by product name or filter by Work, Planning, or Insights.
- Open a tool, fill in its sample inputs, then run the analysis.
- Review the result, assumptions, source/evidence notes, and approval step before acting on recommendations.
- Use **API docs** on a tool page to inspect that tool's request and response schema.

The tool screens live in `static/`; the Alpha API shell is in `alpha_app/`; the project implementations and tests are in `tools/`. The Inventory Control Tower uses the existing `replenishment` slug. The separate demand tool and both legacy inventory API paths remain mounted.

## Data and security limits

Generated examples are fictional and labelled SYNTHETIC. Weather is the only live external data lookup and runs only when requested; see `docs/EXTERNAL_DATA_SOURCES.md` for source attribution. These prototypes are not validated for real business decisions or deployment.

Alpha binds to localhost. The Knowledge Assistant has local demo accounts and server-side roles/groups, but it is not an enterprise identity system. Do not upload confidential documents. Copilot and the inventory draft ledger are not encrypted at rest. On first run, the Knowledge Assistant prints one-time demo passwords; set `ALPHA_DEMO_*_PASSWORD` before starting if you want to choose them. See `.env.example` for the supported local settings.

## Development checks

Run the full test suite from this folder:

```powershell
python -m pytest
```

CI also runs the supported Ruff and mypy scopes, JavaScript syntax checks, fixed-seed evaluations, and a Windows fast-test subset. See [docs/architecture.md](docs/architecture.md), [docs/BUILD_STATE.md](docs/BUILD_STATE.md), [docs/BUILD_REPORT.md](docs/BUILD_REPORT.md), and [docs/CASE_STUDIES.md](docs/CASE_STUDIES.md).

# Project Alpha

Project Alpha puts thirteen focused AI and analytics demos behind one local workspace. It gives each tool its own guided form, result view, source or evidence details, and API documentation link.

## Run it

Requirements: Python 3.12 or newer.

**Windows:** open PowerShell in this folder and run:

```powershell
./run.ps1
```

**macOS/Linux:** run:

```sh
chmod +x ./run.sh   # first run only
./run.sh
```

Then open <http://127.0.0.1:8000>. The launch script uses a shared `.venv` in the parent `ai projects` folder and installs the pinned dependencies on first run. It seeds generated demo data and model files as needed. Press Ctrl+C in the terminal to stop the server.

## Use the workspace

- Start at the overview. Search by tool name or filter by Work, Planning, or Insights.
- Open a tool, fill in its example or your own sample inputs, then run the analysis.
- Review the result, assumptions, source/evidence notes, and approval step before acting on recommendations.
- Use **API docs** on a tool page to inspect that tool's request and response schema.

The tool screens live in `static/`; the Alpha API shell is in `alpha_app/`; the original project implementations and their tests are in `tools/`.

## Data and model boundaries

Generated examples are fictional and labelled synthetic in the tools. Travel itineraries use a fictional activity catalog; a user-triggered weather lookup can use Open-Meteo and shows attribution. Forecast, scoring, grouping, sentiment, and investigation results are demonstrations for review. Do not use them as real business decisions without replacing the sample data and validating the approach.

Alpha binds to localhost. The Knowledge Assistant has local demo accounts with server-side roles and groups, but it is not an enterprise identity system and is not suitable for confidential documents or deployment. Its first run prints one-time demo passwords; copy `.env.example` to `.env` and set the `ALPHA_DEMO_*_PASSWORD` values before the first run to choose them. LLM use defaults to off (`LLM_PROVIDER=none`). The optional shared adapter supports local Ollama only; no paid LLM provider is included.

## Development checks

Run the full test suite from this folder:

```powershell
python -m pytest
```

The suite covers each project's current tests and the combined workspace health routes. `AGENTS.md` contains the project engineering constraints.

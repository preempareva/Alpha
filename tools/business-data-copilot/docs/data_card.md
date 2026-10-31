# Business Data Copilot data card

## Data sources

| Dataset | Source | Label | Use |
|---|---|---|---|
| Demo orders | Fixed-seed generator in app/demo.py | SYNTHETIC | Demonstrate schema profiling, aggregation, charting, and verification |
| User dataset | File selected by the signed-in Alpha user | USER_UPLOADED | Private, owner-scoped profiling and read-only analysis |

The synthetic demo contains date, region, product, channel, units, revenue, cost, and segment. It intentionally contains missing dimension values, one duplicate row, one negative unit count, and an outlier revenue value. It is fictional and has no external license.

## Processing

CSV and XLSX are parsed in bounded memory. XLSX formulas remain text and are never evaluated. Upload bytes are not persisted before schema confirmation. Confirmed data is loaded into an owner-scoped table in a workspace DuckDB file; the workspace directory name is a one-way hash of the server-derived workspace ID. A manifest stores the original file hash, ingestion time, expiry, schema, and sample-free profile statistics.

The query connection is read-only. The compiler accepts typed aggregates, dimensions, and filters from a validated plan and binds all filter values. Query outputs are capped, checked by an independent pandas pass, and audited with a question hash and a redacted plan.

## Privacy and retention

- A user can read only the dataset table whose owner and workspace hashes match their authenticated server session.
- Sensitive columns are removed from Hub profiles, local planner schema, confirmed previews, dimensions, filters, returned plan names, and audit plans. Explicitly requested aggregate results use generic output labels.
- Raw row samples are never included in local-model prompts.
- Upload preview frames expire from process memory after 15 minutes. Confirmed datasets expire after 30 days. Redacted query audit metadata expires after 90 days. Download results are cached in process for at most 15 minutes.
- Copilot does not encrypt data at rest. The host's filesystem protections apply.
- A user-uploaded dataset's format and content are not independently licensed or validated by Alpha. The uploader is responsible for having permission to analyze the file.

## Intended use and limits

This is an educational local analytics demo for small files. Column inference is heuristic, date parsing can be ambiguous, and a correct SQL/pandas match does not prove that the user's question was interpreted as intended. Users should review the selected schema and returned assumptions. It is not a governed enterprise data platform.

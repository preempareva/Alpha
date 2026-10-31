# Enterprise Knowledge Assistant

A permission-aware, local-first knowledge assistant prototype built from the supplied AI Project Blueprint. It indexes approved Markdown, text, HTML, and PDF files, answers with retrieved source excerpts, and abstains when evidence is weak. All starter content is fictional and synthetic.

## Run in Alpha

Open the unified workspace from project-alpha with powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1. This tool opens as a workflow inside the Alpha site at http://127.0.0.1:8000.

## What works

- Upload and index `.md`, `.txt`, `.html`, and text-based `.pdf` files with title, owner, version, effective dates, and access groups.
- Track ingestion jobs, document freshness, source retirement, and idempotent re-indexing by content hash.
- Split content by headings and paragraphs, retaining page and heading metadata where available.
- Search only active, currently effective documents visible to the requesting user's groups. SQLite FTS5 is the deterministic lexical baseline.
- Return concise evidence excerpts and citations. The first release intentionally does not call an LLM: it cannot invent a synthesized answer, and reports when evidence is weak.
- Submit minimal positive/negative answer feedback; health and evaluation endpoints are available.

## Evaluation and limits

Run `python -m pytest`. The small, authored benchmark is in `data/evaluation/questions.json`; run `python scripts/evaluate.py` for Recall@5 and MRR. This measures retrieval only, not answer faithfulness or enterprise performance. Current baseline has no vector embeddings, OCR, external identity provider, multi-tenant database, or telemetry exporter. Scanned PDFs are marked for review. Do not upload confidential material to this demo.

See `docs/` for the project charter, architecture, data register/card, threat model, retrieval card, runbook, and demo script. Runtime data lives in `instance/` and is gitignored.





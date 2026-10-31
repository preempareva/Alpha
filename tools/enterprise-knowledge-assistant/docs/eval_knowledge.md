# Knowledge Assistant retrieval evaluation

Measured on **2026-11-01** using 127 authored questions over the seeded synthetic corpus.
The run uses deterministic FTS5 retrieval with LLM synthesis disabled.

| Measure | Result |
|---|---:|
| Recall@5 | 0.9770 |
| MRR@5 | 0.9521 |
| Citation precision | 0.7311 |
| Abstention accuracy | 1.0000 |
| ACL leakage rate | 0.0000 |
| Expired-version citations | 0 |

## Cases

- answerable: 87
- unanswerable: 10
- ambiguous: 10
- outdated: 10
- cross-group-attack: 10

## Limits

- All 30 source documents are fictional and authored for this demo.
- The benchmark is a small local retrieval check, not enterprise answer quality or real user performance.
- LLM synthesis is disabled for this run; no Ollama availability is assumed.
- Citation precision treats the single labelled source file as the relevant target.

# Knowledge Assistant retrieval model card

## System

The default retriever uses SQLite FTS5 lexical search with BM25-style ordering. When an optional local embedding provider is available, lexical and normalized vector scores are fused at 0.6 and 0.4 respectively. Without embeddings, retrieval is lexical only. Active-document, effective-date, and access-group constraints are applied to the candidate set.

Answer synthesis is disabled in the deterministic configuration. The system returns citations from retrieved passages and abstains when evidence is missing, ambiguous, expired, or inaccessible. An optional local Ollama provider is bounded and must not determine identity or access.

## Evaluation

The fixed synthetic benchmark covers answerable, unanswerable, ambiguous, expired-version, and cross-group questions. Its latest recorded Recall@5 is 0.977; abstention accuracy is 1.000; ACL leakage and expired-version leakage are both 0. The run and limits are in `docs/eval_knowledge.md`; CI applies the tolerances in the repository-level `docs/eval/thresholds.json`.

## Limits and use

These results describe only the authored corpus and questions. They do not establish correctness for real policies, legal or HR guidance, enterprise-scale retrieval, or any specific embedding model. Keep a human source review in the workflow and verify citations before acting.

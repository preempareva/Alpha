# Retrieval card

- **Purpose:** Find approved source excerpts for employee questions.
- **Method:** SQLite FTS5 lexical retrieval over title, heading, and chunk text; when local Ollama embeddings are available, normalized lexical and cosine scores are combined at 0.6 and 0.4. Active status, effective dates, and access groups are enforced before citations are returned.
- **Answer behavior:** Returns evidence excerpts and an instruction to review them. It does not synthesize policy answers or call an LLM. No results yields a fixed abstention.
- **Evaluation:** Six authored synthetic questions, including one unanswerable query. `python scripts/evaluate.py` reports Recall@5, MRR@5, and no-answer abstention. Small set, not statistically representative.
- **Known limits:** With `LLM_PROVIDER=none` (the default), retrieval is lexical and can miss paraphrases. Optional embeddings require a running local Ollama server and embedding model; failures fall back to FTS5. Score thresholds need evaluation on a larger labelled set; there is no reranker, PDF extraction is text-only, and the benchmark does not measure answer faithfulness.
- **Change control:** Record retrieval code, corpus and evaluation question changes together; review ACL isolation and abstention after each change.

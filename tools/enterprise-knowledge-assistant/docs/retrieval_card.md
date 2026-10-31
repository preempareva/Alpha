# Retrieval card

- **Purpose:** Find approved source excerpts for employee questions.
- **Method:** SQLite FTS5 lexical retrieval over title, heading and chunk text; active status, effective dates, and access groups are enforced before citations are returned.
- **Answer behavior:** Returns evidence excerpts and an instruction to review them. It does not synthesize policy answers or call an LLM. No results yields a fixed abstention.
- **Evaluation:** Six authored synthetic questions, including one unanswerable query. `python scripts/evaluate.py` reports Recall@5, MRR@5, and no-answer abstention. Small set, not statistically representative.
- **Known limits:** Lexical matching misses paraphrases; score threshold needs tuning against a larger labelled set; no embeddings/reranker; PDF extraction is text-only; no answer-faithfulness metric applies until a composer is introduced.
- **Change control:** Record retrieval code, corpus and evaluation question changes together; review ACL isolation and abstention after each change.

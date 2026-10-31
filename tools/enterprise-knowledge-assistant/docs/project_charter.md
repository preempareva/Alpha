# Project charter

- **Problem:** Staff search fragmented guidance and cannot tell which approved source supports an answer.
- **Users:** Employees, knowledge owners, and administrators.
- **Trigger/output:** A natural-language question returns the most relevant currently effective, access-permitted source excerpts with document version and location; it abstains when no evidence is retrieved.
- **Value measure:** Retrieval Recall@5/MRR, correct abstention, freshness, answer latency, and user feedback. No business savings claim is made.
- **Data:** Three fictional Markdown policy/how-to documents authored for this demo. No company documents or personal data.
- **Constraints:** Local prototype; demo identity headers are not authentication; no LLM, OCR, vector search, or production secrets.
- **Non-goals:** Legal/policy approval, autonomous action, broad drive ingestion, company-wide deployment, and claims of production performance.

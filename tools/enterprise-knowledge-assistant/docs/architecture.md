# Architecture and workflow

```mermaid
flowchart LR
  U[Employee browser] --> API[FastAPI]
  A[Owner uploads approved file] --> API
  API --> P[Type validation and parser]
  P --> C[Heading-aware chunks]
  C --> DB[(SQLite metadata and FTS5)]
  U --> Q[Question + verified demo groups]
  Q --> ACL[Active, effective-date, ACL filters]
  ACL --> FTS[Lexical retrieval]
  FTS --> R[Evidence excerpts + citation metadata]
  R --> U
  API --> J[Ingestion job status and minimal feedback]
```

Ingestion is synchronous in this first local version. Each job records completion or `NEEDS_REVIEW`. A source update creates a new document version and deactivates prior versions after extraction succeeds. Retirement removes chunks from the search index while retaining metadata for audit. On questions, group filtering is applied before citations are built. The current deployment uses a request header as a demo principal; an actual deployment must validate identity server-side.

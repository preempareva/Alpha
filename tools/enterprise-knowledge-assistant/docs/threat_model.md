# Threat model

## Assets and boundaries

Protected material is uploaded source text and access metadata. Inputs cross an untrusted upload/question boundary; the local database is the storage boundary. The included sample contains only synthetic content.

## Main threats and controls

- **Cross-group disclosure:** group filter is applied before citations; automated test checks a restricted document. Demo groups come from caller-controlled headers and are not suitable for real deployment.
- **Malicious source instructions / prompt injection:** no model executes source text in this version. Excerpts are displayed as escaped text in the browser. Reassess before adding an LLM.
- **Stale or revoked guidance:** effective dates and active status filter retrieval; retiring a source deletes its FTS entries.
- **Upload abuse:** extension allowlist, bounded body read, UTF-8 decoding and PDF text extraction; failed parser jobs are visible. Add malware scanning and authentication before deployment.
- **XSS:** dynamic fields are HTML-escaped by the demo UI.
- **Sensitive logs:** question text is not persisted; feedback stores a hash. Application/server access logs still need a retention and redaction policy.
- **Abuse of admin endpoints:** no admin authorization in local demo. Do not expose it to a network or upload confidential material.

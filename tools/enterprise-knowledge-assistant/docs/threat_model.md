# Threat model

## Assets and boundaries

Protected material is uploaded source text and access metadata. Inputs cross an untrusted upload/question boundary; the local database is the storage boundary. The included sample contains only synthetic content.

## Main threats and controls

- **Cross-group disclosure:** group membership and role come from the server-side users table. The access group predicate is inside the SQLite retrieval query; automated tests spoof identity headers and confirm zero cross-group citations.
- **Malicious source instructions / prompt injection:** no model executes source text in this version. Excerpts are displayed as escaped text in the browser. Reassess before adding an LLM.
- **Stale or revoked guidance:** effective dates and active status filter retrieval; retiring a source deletes its FTS entries.
- **Upload abuse:** extension allowlist, bounded body read, UTF-8 decoding and PDF text extraction; failed parser jobs are visible. Upload and retirement require the server-side admin role. Malware scanning remains absent.
- **XSS:** dynamic fields are HTML-escaped by the demo UI.
- **Sensitive logs:** question text is not persisted; feedback stores a hash. Application/server access logs still need a retention and redaction policy.
- **Session theft/replay:** sessions are signed, HttpOnly, same-site cookies with an eight-hour age limit. The local signing secret is ignored by Git. Use HTTPS and set `ALPHA_HTTPS=1` before exposing the app; the demo binds to localhost and is not a production identity system.
- **Abuse of admin endpoints:** admin checks run on the server and are covered by role tests. Do not expose the demo to a network or upload confidential material.

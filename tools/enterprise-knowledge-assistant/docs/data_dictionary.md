# Data dictionary

- `documents`: source metadata, owner, version, effective interval, access groups, SHA-256, indexing timestamp and active status.
- `chunks`: stable chunk ID, parent document, order, optional PDF page, heading and excerpt text.
- `chunks_fts`: SQLite FTS5 lexical index. Entries for retired documents are deleted immediately.
- `jobs`: filename, lifecycle status, failure reason and timestamps; malformed uploads end in `NEEDS_REVIEW`.
- `feedback`: random feedback ID, user ID, hashed question, cited chunk IDs, binary helpful rating, optional reason and timestamp. Raw question is not stored.

Dates are ISO 8601. Effective windows are evaluated in UTC server date. Group names are case-sensitive. Database is local SQLite; production retention, encryption, deletion, tenancy and migration policies are not yet implemented.

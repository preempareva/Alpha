# Threat model

The request text is untrusted. It only reaches deterministic intent matching; user text is never interpolated into SQL. Queries are selected from a fixed allowlist, parameterized for row limits, run on a read-only SQLite connection, and bounded in output size. The workflow cannot mutate data or call external systems. A denial-of-service risk remains from concurrent requests and there is no authentication, tenancy, or network protection; keep this prototype local. Synthetic data only.

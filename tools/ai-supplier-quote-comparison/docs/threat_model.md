# Threat model

Quote fields are untrusted and typed/range validated. The service performs only deterministic arithmetic and returns the submitted suppliers/terms; no external supplier action is possible. It has no authentication or persistence, so it is local synthetic demo only. A wrong tax/freight assumption could distort rankings; missing terms are surfaced and incompatible currencies rejected. Keep review weights visible and require procurement approval outside this prototype.

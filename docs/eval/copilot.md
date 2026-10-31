# Business Data Copilot evaluation

- Data: SYNTHETIC, generated with a fixed seed.
- Planner: LLM off (LLM_PROVIDER=none).
- Gold questions: **40**, numeric correctness **40/40 (1.0000)**.
- Refusals: **4/4 (1.0000)**.
- Verifier tamper detection: **5/5 (1.0000)**.
- Query latency p50/p95: **150.718 / 187.191 ms**.

Expected numbers were calculated by a separate pandas aggregation path. The saved evaluation contains only task status, row counts, and expected-result hashes; it does not store generated rows or numeric result values.

The questions are hand-authored templates over one synthetic dataset. These scores do not estimate accuracy on arbitrary spreadsheets, real user data, or ambiguous requests.

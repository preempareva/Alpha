# Project Alpha case studies

These case studies describe reproducible local demonstrations over authored or fixed-seed synthetic fixtures. Evaluation scores are regression evidence for those fixtures, not claims about real users, organizations, or production data.

## Knowledge Assistant: retrieve, cite, or abstain

The Knowledge Assistant searches a small fictional policy corpus with FTS5 and applies active-version and access-group filters before returning citations. Its authored benchmark recorded Recall@5 **0.977**, abstention accuracy **1.000**, ACL leakage **0**, and expired-version citations **0**. The use case demonstrates source-grounded answers and refusal when the fixture offers no authorized, current evidence. It does not validate real policy advice or enterprise-wide retrieval.

## BI Analyst Workflow: bounded analysis with a verifier

The BI workflow routes questions to a fixed read-only catalogue over fictional retail orders. A separate Python aggregation checks the result before display. In the 40-case authored benchmark, tool selection, argument matching, numeric correctness, and refusal/clarification correctness each scored **1.000**; the verifier caught **5/5** injected numeric changes. These figures cover templated questions on one fixed-seed dataset, not arbitrary analyst requests or a live warehouse.

## Agent Hub: one reviewed cross-project plan

The Hub runs allowlisted tools with identity-scoped traces and approval records. Its expanded deterministic benchmark covered **80 tasks**, including **20** cross-project plans that combined four source tools. The recorded cross-project completion and trace checks were **20/20**; correct refusal and policy-denial checks were **12/12** and **6/6**. BI verifier tampering was caught **5/5** times. The planner was deterministic, Ollama was not run, and browser-driven screenshots were not verified.

## Business Data Copilot: controlled spreadsheet analysis

Copilot profiles a confirmed local CSV/XLSX dataset and answers bounded read-only questions with an independent verifier and formula-safe CSV export. Its synthetic 40-question evaluation recorded **40/40** numeric questions, **4/4** refusal cases, and **5/5** verifier tampering catches. Uploads are user-provided and locally stored; DuckDB data is not encrypted at rest. The fixed demo does not establish accuracy on arbitrary spreadsheets.

## Inventory Control Tower: forecast and compare policies

The Tower validates six synthetic tables, compares rolling-origin forecast candidates, and simulates six buffer-policy scenarios. Its recorded selection rule chose the naive baseline for intermittent demand and ETS for seasonal demand across **36** metric groups and **6** scenarios. Approval-gated actions stop at local draft and simulation records; no purchase order or supplier message is sent. Forecast error and scenario assumptions describe only the fixed-seed panel and are not real replenishment advice or savings evidence.

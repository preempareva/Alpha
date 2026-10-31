# Business Data Copilot demo script

1. Start Project Alpha and open the Copilot card.
2. Sign in with the existing local Knowledge Assistant account.
3. Select Use synthetic demo. Point out the SYNTHETIC label and the deliberately imperfect fictional dataset.
4. Review inferred types and quality indicators. Mark segment sensitive for the privacy demonstration and confirm.
5. Run Show monthly revenue by region. Review the table/chart and the independent pandas verification badge.
6. Expand Query plan and assumptions and Provenance. Explain that the dataset hash and query ID help trace the result; they do not certify source quality.
7. Download the CSV and note that textual spreadsheet formulas are escaped.
8. In a separate test session, try a write request or SQL injection phrase; the planner should refuse it. A modified result should fail the independent verifier.
9. Open Agent Hub and ask Show revenue by region in my uploaded dataset. The Hub uses the caller-scoped copilot.query tool; it does not read another user's dataset.

The evaluation numbers in docs/eval/copilot.md refer only to the fixed-seed synthetic benchmark, not this interactive demonstration or arbitrary user files.

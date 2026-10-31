# Investigation card

- **Inputs:** Synthetic metric/log/trace events associated with a fixture incident ID.
- **Process:** Group evidence, identify threshold-crossing signal, inspect nearby dependency events, write a bounded hypothesis and read-only checks.
- **Guardrail:** No deployment, rollback, restart, scaling, or configuration tool is available.
- **Evaluation:** Tests check evidence correlation and safe handling of an unknown incident.
- **Limits:** Fixture-only, fixed rules, no true causal inference, no secret redaction pipeline for real telemetry, no latency/cost monitoring.

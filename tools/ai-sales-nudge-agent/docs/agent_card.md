# Agent card

- **Inputs:** Fictional lead stage, days since contact, recent engagement and human-authored next step.
- **Decision:** A fixed transparent rule ranks review priority; draft text is a template filled with synthetic lead context.
- **Control:** Only draft storage and local approval exist; external messages cannot be sent.
- **Evaluation gap:** No outcomes exist to evaluate uplift or contact appropriateness. Current tests cover draft-only behavior and approval idempotency.
- **Risks:** Stale CRM fields, over-contact, misleading score and inappropriate personalization. Requires consent, suppression rules, owner review and measured experiments before real use.

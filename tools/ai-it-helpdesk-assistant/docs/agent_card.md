# Helpdesk Triage agent card

- **Input:** User-written IT issue, 12–3,000 characters.
- **Output:** Suggested category/priority, a deterministic KB match, missing-context prompts, and a ticket draft in `NEEDS_REVIEW`.
- **Sensitive input:** Simple secret-pattern check rejects common password/OTP phrases; it is not a complete secret detector. UI warns users not to enter credentials.
- **Actions:** No privileged actions; approval records local demo state only.
- **Evaluation:** Tests cover VPN guidance, secret rejection, and repeated approval.
- **Limitations:** Synthetic KB, keyword routing, no identity/asset context, no real ticket-system integration.

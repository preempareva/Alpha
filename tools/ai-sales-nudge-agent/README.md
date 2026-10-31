# AI Sales Nudge Agent

Synthetic CRM demo that ranks leads using transparent recency and engagement rules and writes a suggested message as a draft. Drafts require an explicit local approval state; the project has no send/email/CRM integration.

## Run in Alpha

Open the unified workspace from project-alpha with powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1. This tool opens as a workflow inside the Alpha site at http://127.0.0.1:8000.

## Limits

The score weights are illustrative, not learned or validated. There is no conversion outcome data, causal uplift evaluation, consent check, CRM permission model, or message dispatch. Never treat ranking as a claim of sales effectiveness.





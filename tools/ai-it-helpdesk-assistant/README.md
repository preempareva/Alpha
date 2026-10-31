# Helpdesk Triage

Local synthetic-data prototype that classifies a help request, suggests an authored knowledge article, asks for missing context, and stores a ticket draft in `NEEDS_REVIEW`. A demo approval changes only local state; no ITSM system, account, or device is contacted.

## Run in Alpha

Open the unified workspace from project-alpha with powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1. This tool opens as a workflow inside the Alpha site at http://127.0.0.1:8000.

## Guardrails and limits

Do not enter passwords or one-time codes. Suggestions are deterministic and the content is fictional. Priority/category labels need service-owner validation. The local approval endpoint is intentionally unauthenticated for this demo and must not be exposed to a network or connected to production ticketing.





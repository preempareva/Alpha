# AI Observability Investigator

Local incident-investigation demo that correlates a small fictional event set across metric, log, and trace signals, produces a hypothesis with evidence, and proposes safe next checks. It never executes infrastructure changes.

## Run in Alpha

Open the unified workspace from project-alpha with powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1. This tool opens as a workflow inside the Alpha site at http://127.0.0.1:8000.

## Limits

The telemetry is authored synthetic fixtures, not an OpenTelemetry collector integration. Correlation logic is a transparent rule, not a causal root-cause model. No production logs, traces, secrets, or infrastructure controls are connected.





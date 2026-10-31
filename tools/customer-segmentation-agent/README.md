# Customer Segmentation Agent

Exploratory RFM segmentation using locally generated synthetic transactions, log-scaled monetary value, standardized features, and k-means. The API returns aggregate profiles and a silhouette score. It does not infer sensitive traits, name individuals, export audiences, or automate targeting.

## Run in Alpha

Open the unified workspace from project-alpha with powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1. This tool opens as a workflow inside the Alpha site at http://127.0.0.1:8000.

## Limits

Transactions are fictional and generated in four simple behavioral regimes, so clusters can look cleaner than real data. A single silhouette score does not validate usefulness or stability. No sensitive features are present; real use would require authorized data, stability checks, analyst labels, privacy review, and controlled experiments before any action.





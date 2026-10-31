# Threat model

The demo accepts a single feature record and returns a probability-like score. Inputs are validated for type and numeric range. No real personal data should be submitted. The endpoint has no authentication or authorization, and the demo UI has no persistent customer database. Do not expose this prototype on a public network. The only bundled data is generated synthetic data; generated CSV and model artifacts are gitignored. Scores can cause harmful over-contact if misused, so no campaign/action endpoint exists and the interface states human review is required.

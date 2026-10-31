# Threat model

Inputs are schema and range validated; SKU history must exist; policy is selected from a fixed set. No external tools or ordering endpoint are available. The unauthenticated local API uses synthetic data only and must not be exposed to a public network. Main operational risk is an analyst treating a simulated suggestion as an order instruction; the UI and API mark all results as synthetic and awaiting approval.

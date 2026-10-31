# Runbook

Run `python scripts/seed_data.py` to recreate the disposable synthetic warehouse; then start the local API. If the warehouse is missing, the API returns 503 with the seeding instruction. `/health` checks process liveness. `/api/trace` runs a deterministic example and shows the bounded trace. Reset only the gitignored `data/runtime/retail.db` by rerunning the seed script. Before using a real warehouse, add authenticated read-only credentials, row/column policies, query review, audit/retention and concurrency/timeout controls.

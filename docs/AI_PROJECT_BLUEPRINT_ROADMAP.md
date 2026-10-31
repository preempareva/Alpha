# AI Project Blueprint execution tracker

The supplied handbook describes 13 projects and explicitly advises a sequential portfolio, with synthetic/public/authorized data and honest limits. Each project now has a separate local prototype folder. These are MVP learning builds; none is presented as a production deployment or as evidence of enterprise savings.

| Blueprint | Project | Local project | Prototype status |
|---:|---|---|---|
| 1 | Enterprise Knowledge Assistant | [enterprise-knowledge-assistant](enterprise-knowledge-assistant/README.md) | Implemented: ingestion, ACL-filtered lexical retrieval, citations, abstention, UI, evaluation |
| 2 | AI IT Helpdesk Assistant | [ai-it-helpdesk-assistant](ai-it-helpdesk-assistant/README.md) | Implemented: safe intake, KB guidance, ticket draft and review state |
| 3 | Travel Itinerary Planner | [travel-itinerary-planner](travel-itinerary-planner/README.md) | Implemented: constrained itinerary using a cited fictional catalog |
| 4 | Intelligent Inventory Forecasting | [intelligent-inventory-forecasting](intelligent-inventory-forecasting/README.md) | Implemented: temporal baseline backtest and forecast ranges |
| 5 | Customer Churn Prediction | [customer-churn-prediction](customer-churn-prediction/README.md) | Implemented: point-in-time synthetic model, calibrated score API, time holdout |
| 6 | Sales Pipeline Forecasting | [sales-pipeline-forecasting](sales-pipeline-forecasting/README.md) | Implemented: temporal synthetic win model and weighted pipeline score |
| 7 | Customer Sentiment Intelligence | [customer-sentiment-intelligence](customer-sentiment-intelligence/README.md) | Implemented: sentiment baseline, temporal evaluation, theme signals |
| 8 | Multi-Agent Business Intelligence System | [multi-agent-business-intelligence](multi-agent-business-intelligence/README.md) | Implemented: bounded read-only analysis workflow with verifier and trace |
| 9 | Autonomous Inventory Optimization Agent | [inventory-optimization-agent](inventory-optimization-agent/README.md) | Implemented: simulated reorder recommendation awaiting approval |
| 10 | AI Sales Nudge Agent | [ai-sales-nudge-agent](ai-sales-nudge-agent/README.md) | Implemented: transparent prioritization and draft-only message workflow |
| 11 | AI Observability Investigator | [ai-observability-investigator](ai-observability-investigator/README.md) | Implemented: synthetic metric/log/trace evidence and read-only investigation |
| 12 | Supplier Quote Comparison | [ai-supplier-quote-comparison](ai-supplier-quote-comparison/README.md) | Implemented: landed-cost arithmetic, missing-term flags, analyst review |
| 13 | Customer Segmentation Agent | [customer-segmentation-agent](customer-segmentation-agent/README.md) | Implemented: synthetic RFM clustering and aggregate profiles |

## Shared release gates still open

- Replace synthetic fixtures with source-authorized data and document the actual source licence, owner, and retention rules.
- Expand project-specific labelled evaluations, failure cases, calibration/stability checks, and independent review.
- Add real identity/access controls, secrets management, deployment hardening, persistent audit, monitoring, and recovery appropriate to each project.
- Validate with intended users and record a real demo/release report before calling any project production-ready.
- Do not make causal impact, savings, or model performance claims from synthetic results.

## Run

Each tool folder has a `README.md` describing its workflow and limits. Launch all tools through Project Alpha; the root `requirements.txt` pins the shared runtime dependencies.

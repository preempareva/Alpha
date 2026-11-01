# AI Project Blueprint execution tracker

The supplied handbook describes 13 projects and advises using synthetic, public, or authorized data with honest limits. Alpha now contains those 13 local prototypes plus Business Data Copilot. These are learning builds; none is presented as a production deployment or as evidence of business savings.

| Blueprint | Project | Local project | Prototype status |
|---:|---|---|---|
| 1 | Knowledge Assistant | [enterprise-knowledge-assistant](../tools/enterprise-knowledge-assistant/README.md) | Implemented: ingestion, ACL-filtered retrieval, citations, abstention, UI, evaluation |
| 2 | Helpdesk Triage | [ai-it-helpdesk-assistant](../tools/ai-it-helpdesk-assistant/README.md) | Implemented: safe intake, KB guidance, ticket draft and review state |
| 3 | Travel Itinerary Planner | [travel-itinerary-planner](../tools/travel-itinerary-planner/README.md) | Implemented: constrained itinerary using a cited fictional catalog |
| 4 | Demand Forecasting | [intelligent-inventory-forecasting](../tools/intelligent-inventory-forecasting/README.md) | Implemented: temporal baseline backtest and forecast ranges |
| 5 | Customer Churn Prediction | [customer-churn-prediction](../tools/customer-churn-prediction/README.md) | Implemented: point-in-time synthetic model, calibrated score API, time holdout |
| 6 | Sales Pipeline Forecast | [sales-pipeline-forecasting](../tools/sales-pipeline-forecasting/README.md) | Implemented: temporal synthetic win model and weighted pipeline score |
| 7 | Customer Sentiment Insights | [customer-sentiment-intelligence](../tools/customer-sentiment-intelligence/README.md) | Implemented: sentiment baseline, temporal evaluation, theme signals |
| 8 | BI Analyst Workflow | [multi-agent-business-intelligence](../tools/multi-agent-business-intelligence/README.md) | Implemented: bounded read-only analysis workflow with verifier and trace |
| 9 | Inventory Control Tower | [inventory-optimization-agent](../tools/inventory-optimization-agent/README.md) | Merged demand and replenishment views; drafts and execution remain simulated |
| 10 | Sales Follow-up Prioritizer | [ai-sales-nudge-agent](../tools/ai-sales-nudge-agent/README.md) | Implemented: transparent prioritization and draft-only message workflow |
| 11 | Incident Evidence Correlator (synthetic) | [ai-observability-investigator](../tools/ai-observability-investigator/README.md) | Implemented: synthetic metric/log/trace evidence and read-only investigation |
| 12 | Supplier Quote Comparison | [ai-supplier-quote-comparison](../tools/ai-supplier-quote-comparison/README.md) | Implemented: landed-cost arithmetic, missing-term flags, analyst review |
| 13 | Customer Segmentation | [customer-segmentation-agent](../tools/customer-segmentation-agent/README.md) | Implemented: synthetic RFM clustering and aggregate profiles |

Business Data Copilot is the fourteenth workspace tool and is documented in [its README](../tools/business-data-copilot/README.md).

## Shared release gates still open

- Replace synthetic fixtures with source-authorized data and document the actual source licence, owner, and retention rules.
- Expand project-specific labelled evaluations, failure cases, calibration/stability checks, and independent review.
- Add real identity/access controls, secrets management, deployment hardening, persistent audit, monitoring, and recovery appropriate to each project.
- Validate with intended users and record a real demo/release report before calling any project production-ready.
- Do not make causal impact, savings, or model performance claims from synthetic results.

## Run

Each tool folder has a `README.md` describing its workflow and limits. Launch all tools through Project Alpha; the root `requirements.txt` pins the shared runtime dependencies.

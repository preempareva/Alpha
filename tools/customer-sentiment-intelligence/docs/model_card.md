# Model card

- **Task:** Three-class sentiment on authored synthetic review snippets.
- **Method:** TF-IDF word unigrams/bigrams and class-weighted logistic regression.
- **Split:** Time-based holdout by review date; no random shuffle.
- **Baseline:** Most-frequent class.
- **Metrics:** Accuracy, macro F1, and per-class precision/recall/F1 in `artifacts/evaluation.json`.
- **Themes:** Static keyword matching for quality, delivery, support, and setup. Not unsupervised topic discovery.
- **Limits:** Templated generated language; does not generalize evidence to real customer feedback or other languages; no human annotation or business outcome testing.

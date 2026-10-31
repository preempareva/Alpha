# Segmentation card

- **Input:** Synthetic transaction dates and amounts grouped by synthetic customer ID.
- **Features:** Recency, transaction frequency, and log-scaled monetary sum.
- **Method:** StandardScaler + k-means (`n_init=10`, fixed seed); selectable k from 2 to 8.
- **Evaluation:** Silhouette score and aggregate profiles; no causal or outcome evaluation.
- **Limitations:** Data is constructed from four known regimes, no stability across time/resamples, no purchase categories, and no evidence that segments are actionable.
- **Guardrail:** Aggregate profiles only; no individual-level targeting or sensitive inference.

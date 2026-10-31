# Intelligent Inventory Forecasting

Synthetic weekly demand forecast prototype with a last-eight-week mean baseline, 10th/50th/90th percentile-style ranges, and an eight-week temporal holdout compared with a last-value baseline.

## Run in Alpha

Open the unified workspace from project-alpha with powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1. This tool opens as a workflow inside the Alpha site at http://127.0.0.1:8000.

## Limits

The data is synthetic and not stock-on-hand truth. No stockout censoring, promotion calendar, lifecycle, locations, price, or supplier data is present. The simple range is not a calibrated prediction interval. Do not use it for real buying decisions or claim savings.





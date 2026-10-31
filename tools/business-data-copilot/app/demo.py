"""Fixed-seed fictional order data with explicit quality defects for demonstrations."""

from __future__ import annotations

import io

import numpy as np
import pandas as pd


def build_demo_frame() -> pd.DataFrame:
    rng = np.random.default_rng(421)
    size = 240
    products = np.array(["Comet", "Harbor", "Juniper", "Lumen"])
    regions = np.array(["North", "South", "East", "West"])
    channels = np.array(["Online", "Partner", "Retail"])
    dates = pd.date_range("2025-01-01", periods=120, freq="D")
    frame = pd.DataFrame({
        "date": rng.choice(dates, size=size),
        "region": rng.choice(regions, size=size),
        "product": rng.choice(products, size=size),
        "channel": rng.choice(channels, size=size),
        "units": rng.integers(1, 32, size=size),
        "revenue": np.round(rng.lognormal(mean=5.1, sigma=0.48, size=size), 2),
        "cost": np.round(rng.lognormal(mean=4.1, sigma=0.35, size=size), 2),
        "segment": rng.choice(["small", "mid-market", "enterprise"], size=size),
    })
    frame.loc[7, "region"] = None
    frame.loc[19, "channel"] = None
    frame.loc[33, "units"] = -4
    frame.loc[61, "revenue"] = 18_750.0
    frame = pd.concat([frame, frame.iloc[[5]]], ignore_index=True)
    frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.tz_convert(None)
    return frame


def demo_csv_bytes(frame: pd.DataFrame | None = None) -> bytes:
    output = io.BytesIO()
    (frame if frame is not None else build_demo_frame()).to_csv(output, index=False, date_format="%Y-%m-%d")
    return output.getvalue()

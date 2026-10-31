"""Causal demand baselines, empirical-residual intervals, and rolling-origin scoring."""

from __future__ import annotations

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

MODEL_ORDER = ("naive", "seasonal_naive", "moving_average", "croston_sba", "ets", "lightgbm_global")
MODEL_LABELS = {
    "naive": "Naive last value", "seasonal_naive": "Seasonal naive (52 weeks)",
    "moving_average": "Moving average (8 weeks)", "croston_sba": "Croston SBA",
    "ets": "ETS (statsmodels)", "lightgbm_global": "LightGBM global challenger",
}
DEFAULT_HORIZONS = (1, 2, 4, 6)
DEFAULT_CUTOFF_BACKSTEPS = (26, 13, 6)
SEED = 20261101
DEFAULT_SELECTED_MODELS = {
    "intermittent": "croston_sba", "seasonal": "seasonal_naive", "steady": "moving_average",
}


class ModelUnavailable(ValueError):
    """Raised when a selected optional forecaster cannot run."""


def demand_segment(values: np.ndarray) -> str:
    if values.size and float(np.mean(values <= 0)) >= 0.4:
        return "intermittent"
    return "seasonal" if values.size >= 104 else "steady"


def preferred_model(values: np.ndarray) -> str:
    segment = demand_segment(_nonnegative(values))
    return _evaluated_model_selection().get(segment, DEFAULT_SELECTED_MODELS[segment])


@lru_cache(maxsize=1)
def _evaluated_model_selection() -> dict[str, str]:
    report_path = Path(__file__).resolve().parents[3] / "docs" / "eval" / "inventory_forecast.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        selected = report.get("selected_models", {})
    except (OSError, ValueError, AttributeError):
        return {}
    if not isinstance(selected, dict):
        return {}
    return {str(segment): str(model) for segment, model in selected.items()
            if segment in DEFAULT_SELECTED_MODELS and model in MODEL_ORDER}


def _nonnegative(values: np.ndarray) -> np.ndarray:
    clean = np.nan_to_num(np.asarray(values, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    return np.maximum(clean, 0.0)


def croston_sba(values: np.ndarray, horizon: int, alpha: float = 0.1) -> np.ndarray:
    series = _nonnegative(values)
    positive = np.flatnonzero(series > 0)
    if positive.size == 0:
        return np.zeros(horizon, dtype=float)
    demand_size = float(series[positive[0]])
    interval = float(max(1, positive[0] + 1))
    since = 0
    for index in range(int(positive[0]) + 1, series.size):
        since += 1
        if series[index] > 0:
            demand_size += alpha * (float(series[index]) - demand_size)
            interval += alpha * (float(since) - interval)
            since = 0
    estimate = max(0.0, (1.0 - alpha / 2.0) * demand_size / max(interval, 1e-9))
    return np.full(horizon, estimate, dtype=float)


def _lightgbm_frame(panel: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Build pooled one-step examples using history no later than ``cutoff``."""
    rows: list[dict[str, Any]] = []
    eligible = panel.loc[pd.to_datetime(panel["date"], utc=True) <= cutoff]
    for (sku, location), group in eligible.groupby(["sku", "location"], sort=True):
        values = _nonnegative(group.sort_values("date")["units"].to_numpy(dtype=float))
        for index in range(52, len(values)):
            rows.append({
                "sku_code": int(str(sku).split("-")[-1]),
                "location_code": int(str(location).split("-")[-1]),
                "lag_1": values[index - 1], "lag_2": values[index - 2],
                "lag_4": values[index - 4], "lag_8": values[index - 8],
                "lag_13": values[index - 13], "lag_52": values[index - 52],
                "mean_4": float(values[index - 4:index].mean()),
                "mean_13": float(values[index - 13:index].mean()),
                "target": values[index],
            })
    return pd.DataFrame(rows)


def _lightgbm_forecast(
    panel: pd.DataFrame, sku: str, location: str, horizon: int, cutoff: pd.Timestamp,
) -> np.ndarray:
    try:
        from lightgbm import LGBMRegressor
    except ImportError as exc:
        raise ModelUnavailable("Optional LightGBM is not installed.") from exc
    training = _lightgbm_frame(panel, cutoff)
    if training.empty:
        raise ModelUnavailable("Insufficient pooled history for LightGBM.")
    columns = [column for column in training.columns if column != "target"]
    estimator = LGBMRegressor(
        objective="poisson", n_estimators=120, learning_rate=0.035, num_leaves=15,
        max_depth=-1, min_child_samples=20, random_state=SEED, n_jobs=1, verbosity=-1,
        deterministic=True, force_col_wise=True,
    )
    estimator.fit(training[columns], training["target"])
    history = _nonnegative(panel.loc[
        (panel["sku"] == sku) & (panel["location"] == location)
        & (pd.to_datetime(panel["date"], utc=True) <= cutoff)
    ].sort_values("date")["units"].to_numpy(dtype=float)).tolist()
    if len(history) < 52:
        raise ModelUnavailable("LightGBM requires at least 52 weeks of target history.")
    result: list[float] = []
    for _ in range(horizon):
        row = {
            "sku_code": int(sku.split("-")[-1]), "location_code": int(location.split("-")[-1]),
            "lag_1": history[-1], "lag_2": history[-2], "lag_4": history[-4],
            "lag_8": history[-8], "lag_13": history[-13], "lag_52": history[-52],
            "mean_4": float(np.mean(history[-4:])), "mean_13": float(np.mean(history[-13:])),
        }
        prediction = max(0.0, float(estimator.predict(pd.DataFrame([row], columns=columns))[0]))
        result.append(prediction)
        history.append(prediction)
    return np.asarray(result, dtype=float)


def forecast_points(
    model: str, values: np.ndarray, horizon: int, *, panel: pd.DataFrame | None = None,
    sku: str | None = None, location: str | None = None, cutoff: pd.Timestamp | None = None,
) -> np.ndarray:
    """Forecast ``horizon`` future weekly units using only the supplied training series."""
    if not 1 <= horizon <= 26:
        raise ValueError("Forecast horizon must be 1 to 26 weeks.")
    series = _nonnegative(values)
    if series.size < 8:
        raise ValueError("At least eight weekly observations are required.")
    if model == "naive":
        result = np.full(horizon, float(series[-1]))
    elif model == "seasonal_naive":
        if series.size >= 52:
            first = series.size - 52
            result = np.asarray([series[first + (index % 52)] for index in range(horizon)])
        else:
            result = np.full(horizon, float(series[-1]))
    elif model == "moving_average":
        result = np.full(horizon, float(np.mean(series[-8:])))
    elif model == "croston_sba":
        result = croston_sba(series, horizon)
    elif model == "ets":
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
        except ImportError as exc:
            raise ModelUnavailable("Statsmodels ETS is not installed.") from exc
        seasonal = "add" if series.size >= 104 else None
        try:
            fitted = ExponentialSmoothing(
                series, trend="add", seasonal=seasonal,
                seasonal_periods=52 if seasonal else None,
                damped_trend=True, initialization_method="estimated",
            ).fit(optimized=True, remove_bias=False)
            result = np.asarray(fitted.forecast(horizon), dtype=float)
        except (ValueError, ArithmeticError, np.linalg.LinAlgError) as exc:
            raise ModelUnavailable("ETS could not be fitted to this history.") from exc
    elif model == "lightgbm_global":
        if panel is None or sku is None or location is None or cutoff is None:
            raise ValueError("The global challenger needs a panel, SKU, location, and cutoff date.")
        result = _lightgbm_forecast(panel, sku, location, horizon, cutoff)
    else:
        raise ValueError("Unknown forecast model.")
    return _nonnegative(np.asarray(result, dtype=float))


def empirical_interval(values: np.ndarray, point: float, *, window: int = 8) -> tuple[float, float, float]:
    """Use rolling, training-only moving-average residual quantiles for asymmetric bands."""
    series = _nonnegative(values)
    start = max(window, series.size - 52)
    residuals = [
        float(series[index] - np.mean(series[index - window:index]))
        for index in range(start, series.size)
    ]
    if not residuals:
        return max(0.0, point), point, max(0.0, point)
    quantiles = np.asarray(np.quantile(np.asarray(residuals), [0.1, 0.5, 0.9], method="linear"), dtype=float)
    low, median, high = float(quantiles[0]), float(quantiles[1]), float(quantiles[2])
    return max(0.0, point + low), max(0.0, point + median), max(0.0, point + high)


def forecast_series(
    history: pd.DataFrame, sku: str, location: str, horizon: int = 6, model: str = "auto",
) -> dict[str, Any]:
    series = history.loc[(history["sku"] == sku) & (history["location"] == location)].sort_values("date")
    values = _nonnegative(series["units"].to_numpy(dtype=float))
    if values.size < 20:
        raise ValueError("At least 20 weekly observations are required for an inventory forecast.")
    if model == "auto":
        model = preferred_model(values)
    points = forecast_points(model, values, horizon)
    last_date = pd.to_datetime(series["date"], utc=True).max()
    future = pd.date_range(last_date + pd.Timedelta(weeks=1), periods=horizon, freq="W-MON")
    rows = []
    for week, point in zip(future, points, strict=True):
        lower, median, upper = empirical_interval(values, float(point))
        rows.append({"week": week.date().isoformat(), "p10": round(lower, 2),
                     "p50": round(median, 2), "p90": round(upper, 2)})
    return {"label": "SYNTHETIC", "sku": sku, "location": location,
            "horizon_weeks": horizon, "model": model,
            "segment": demand_segment(values), "forecast": rows,
            "interval_method": "rolling empirical residual quantiles (training data only)"}


def _mase_scale(train: np.ndarray) -> float:
    differences = np.abs(np.diff(train))
    scale = float(np.mean(differences)) if differences.size else 0.0
    return scale if scale > 0 else 1.0


def rolling_origin_backtest(
    panel: pd.DataFrame, *, horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    cutoff_backsteps: tuple[int, ...] = DEFAULT_CUTOFF_BACKSTEPS,
) -> dict[str, Any]:
    """Evaluate multiple SKUs, rolling cutoffs, lead horizons, and empirical intervals."""
    observations: dict[tuple[str, int, str], dict[str, list[float]]] = defaultdict(
        lambda: {"actual": [], "predicted": [], "lower": [], "upper": [], "mase_scale": []}
    )
    unavailable: dict[str, int] = defaultdict(int)
    dates = pd.to_datetime(panel["date"], utc=True)
    candidates = ["naive", "seasonal_naive", "moving_average", "ets"]
    if lightgbm_available():
        candidates.append("lightgbm_global")
    groups = panel.assign(_date=dates).groupby(["sku", "location"], sort=True)
    for (sku, location), group in groups:
        group = group.sort_values("_date")
        values = _nonnegative(group["units"].to_numpy(dtype=float))
        segment = demand_segment(values)
        models = [*candidates, *( ["croston_sba"] if segment == "intermittent" else [])]
        for backstep in sorted(set(cutoff_backsteps), reverse=True):
            cutoff_index = len(values) - backstep
            if cutoff_index < max(20, max(horizons)) or cutoff_index >= len(values):
                continue
            train = values[:cutoff_index]
            truth = values[cutoff_index:min(len(values), cutoff_index + max(horizons))]
            if truth.size == 0:
                continue
            cutoff_date = pd.Timestamp(group.iloc[cutoff_index - 1]["_date"])
            residuals = np.asarray([
                values[index] - float(np.mean(values[index - 8:index]))
                for index in range(max(8, len(train) - 52), len(train))
            ], dtype=float)
            if residuals.size:
                quantiles = np.asarray(np.quantile(residuals, [0.1, 0.5, 0.9], method="linear"), dtype=float)
                low_delta, high_delta = float(quantiles[0]), float(quantiles[2])
            else:
                low_delta = high_delta = 0.0
            for model in models:
                try:
                    prediction = forecast_points(
                        model, train, min(max(horizons), truth.size), panel=panel,
                        sku=str(sku), location=str(location), cutoff=cutoff_date,
                    )
                except ModelUnavailable:
                    unavailable[model] += 1
                    continue
                scale = _mase_scale(train)
                for horizon in horizons:
                    if truth.size < horizon:
                        continue
                    key = (segment, horizon, model)
                    record = observations[key]
                    predicted = prediction[horizon - 1]
                    actual = values[cutoff_index + horizon - 1]
                    record["actual"].append(float(actual))
                    record["predicted"].append(float(predicted))
                    record["lower"].append(max(0.0, float(predicted + low_delta)))
                    record["upper"].append(max(0.0, float(predicted + high_delta)))
                    record["mase_scale"].append(scale)

    metrics: list[dict[str, Any]] = []
    for (segment, horizon, model), group_metrics in sorted(observations.items()):
        actual = np.asarray(group_metrics["actual"])
        predicted = np.asarray(group_metrics["predicted"])
        denominator = float(np.sum(np.abs(actual)))
        metrics.append({
            "segment": segment, "horizon_weeks": horizon, "model": model,
            "n": int(actual.size),
            "wape": float(np.sum(np.abs(actual - predicted)) / denominator) if denominator else None,
            "mase": float(np.mean(np.abs(actual - predicted))
                          / max(float(np.mean(group_metrics["mase_scale"])), 1e-9)),
            "bias_units": float(np.mean(predicted - actual)),
            "interval_coverage_10_90": float(np.mean(
                (actual >= np.asarray(group_metrics["lower"]))
                & (actual <= np.asarray(group_metrics["upper"]))
            )),
        })
    selected = select_models(metrics)
    optional = "available" if lightgbm_available() else "not installed; guarded optional challenger skipped"
    return {"mode": "SYNTHETIC", "cutoff_backsteps_weeks": list(sorted(set(cutoff_backsteps), reverse=True)),
            "horizons_weeks": list(horizons), "metrics": metrics, "selected_models": selected,
            "selection_rule": "lowest aggregate WAPE; select the simplest model within 2% of the best score",
            "optional_lightgbm": optional, "unavailable_fit_counts": dict(sorted(unavailable.items()))}


def select_models(metrics: list[dict[str, Any]]) -> dict[str, str]:
    scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for item in metrics:
        score = item.get("wape")
        if isinstance(score, (int, float)) and np.isfinite(score):
            scores[str(item["segment"])][str(item["model"])].append(float(score))
    selected: dict[str, str] = {}
    for segment, candidates in scores.items():
        means = {model: float(np.mean(values)) for model, values in candidates.items() if values}
        if not means:
            continue
        best = min(means.values())
        eligible = {model for model, score in means.items() if score <= best * 1.02}
        selected[segment] = next(model for model in MODEL_ORDER if model in eligible)
    return selected


def lightgbm_available() -> bool:
    try:
        import lightgbm  # noqa: F401
    except ImportError:
        return False
    return True

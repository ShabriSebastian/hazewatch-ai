"""Trivial forecasters the real model must beat.

Reporting an R-squared in isolation says nothing: PM2.5 is autocorrelated, so a
model that simply repeats the current value already looks impressive. These are
the honest reference points, and every headline metric in this project is quoted
against them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def persistence(df: pd.DataFrame, horizon: int) -> np.ndarray:
    """Assume conditions hold: PM2.5(t+h) = PM2.5(t).

    Hard to beat at short lead times, and the reason a forecast has to prove
    itself at 12-24 hours rather than at 1.
    """
    return df["pm25"].to_numpy(dtype=float)


def climatology(
    train: pd.DataFrame, target: pd.DataFrame, horizon: int
) -> np.ndarray:
    """Mean PM2.5 for this site and hour-of-year, learned from the training split."""
    key = ["institution_id", "_doy", "_hour"]
    tr = train.copy()
    tr["_doy"] = tr["time"].dt.dayofyear
    tr["_hour"] = tr["time"].dt.hour

    lookup = tr.groupby(key)["pm25"].mean()
    site_mean = tr.groupby("institution_id")["pm25"].mean()
    global_mean = float(tr["pm25"].mean())

    tg = target.copy()
    future = tg["time"] + pd.to_timedelta(horizon, unit="h")
    tg["_doy"] = future.dt.dayofyear
    tg["_hour"] = future.dt.hour

    idx = pd.MultiIndex.from_frame(tg[key])
    values = lookup.reindex(idx).to_numpy(dtype=float)

    # Fall back site mean -> global mean for hour/day combinations unseen in training.
    fallback = tg["institution_id"].map(site_mean).to_numpy(dtype=float)
    values = np.where(np.isnan(values), fallback, values)
    return np.where(np.isnan(values), global_mean, values)


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs(y_true[mask] - y_pred[mask])))


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    if not mask.any():
        return float("nan")
    return float(np.sqrt(np.mean((y_true[mask] - y_pred[mask]) ** 2)))


def r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    if not mask.any():
        return float("nan")
    yt, yp = y_true[mask], y_pred[mask]
    ss_res = np.sum((yt - yp) ** 2)
    ss_tot = np.sum((yt - np.mean(yt)) ** 2)
    return float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan")


def skill(model_mae: float, reference_mae: float) -> float:
    """Fractional improvement over a reference. 0.18 means 18% lower error."""
    if not reference_mae or np.isnan(reference_mae) or np.isnan(model_mae):
        return float("nan")
    return float((reference_mae - model_mae) / reference_mae)

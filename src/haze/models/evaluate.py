"""Evaluation, including the metrics that actually matter to a decision-maker.

Regression error is necessary but not sufficient. What a head teacher cares
about is: when the air was going to become dangerous, did this system tell me,
how often did it cry wolf, and how much notice did I get? Those three questions
are answered here as hit rate, false alarm rate and lead time.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from .. import config
from ..alerts import thresholds
from ..institutions import BY_ID
from . import baselines


def window_mask(t: pd.Series, start: str, end: str) -> pd.Series:
    """Rows inside an inclusive [start, end] date window."""
    return (t >= start) & (t <= end + " 23:59:59")


def embargo_mask(t: pd.Series, start: str, hours: int) -> pd.Series:
    """Rows in the `hours` immediately *before* a held-out window.

    Their `target_1h..24h` values reach inside the window, so leaving them in
    training leaks a sliver of the held-out period through the labels. It is only
    144 rows per boundary out of ~110k - 0.13% - and almost certainly does not
    move a metric. It is excluded anyway, because "almost certainly" is not the
    standard a reviewer will hold a held-out claim to.
    """
    if not hours:
        return pd.Series(False, index=t.index)
    boundary = pd.Timestamp(start, tz="UTC")
    return (t >= boundary - pd.Timedelta(hours=hours)) & (t < boundary)


def distinct_receptors(df: pd.DataFrame) -> list[str]:
    """One institution id per genuinely distinct observed PM2.5 series.

    The six institutions are not six independent receptors. CAMS global
    composition is ~0.4 degrees native, and the three Pontianak sites sit ~3 km
    apart, as do the three Kuching sites - so Open-Meteo returns a byte-identical
    PM2.5 series for every member of each trio. Verified at the source: the six
    requests snapped to five distinct grid cells and returned two distinct
    `pm2_5` arrays. This is upstream resolution, not a join bug here; each
    institution really is fetched separately (`features/build.py` ->
    `ingest.weather.air_quality`, one cache key per coordinate pair).

    Scoring all six therefore triples every count without adding information:
    99 reported alert episodes are 33 distinct ones. Pooled *rates* barely move,
    because the copies are near-identical, but the sample size behind them is
    three times smaller than it looks, and that is what decides how much the
    numbers are worth.

    Clustering on the observed series rather than on `city` is deliberate: it
    detects the duplication instead of assuming it, so this becomes a no-op on
    its own if the PM2.5 source is ever upgraded to something site-resolving.
    """
    representatives: list[str] = []
    seen: list[pd.Series] = []
    for inst_id in sorted(df["institution_id"].unique()):
        series = df.loc[df["institution_id"] == inst_id].set_index("time")["pm25"]
        if not any(series.equals(other) for other in seen):
            seen.append(series)
            representatives.append(inst_id)
    return representatives


def split(
    df: pd.DataFrame,
    extra_holdouts: Sequence[tuple[str, str]] | None = None,
    embargo_hours: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Train / validation / test by time.

    The demo event (Aug-Oct 2023) is held out entirely. Training still contains
    the 2022 and 2024 haze seasons, so the model has seen haze dynamics - just
    not this haze.

    `extra_holdouts` removes further `(start, end)` windows from training without
    returning them - used by `scripts/06_validate_events.py` to build a model
    that has seen neither validation event, so a second episode can be scored
    genuinely out of sample. Defaults to None, leaving the served model's split
    exactly as it was.

    `embargo_hours` additionally drops the rows immediately preceding every
    held-out window, whose forecast targets would otherwise reach into it.
    """
    t = df["time"]
    test_mask = window_mask(t, config.TEST_START, config.TEST_END)
    val_mask = window_mask(t, config.VAL_START, config.VAL_END)

    excluded = test_mask | val_mask
    for start, end in extra_holdouts or ():
        excluded |= window_mask(t, start, end)

    if embargo_hours:
        for start in (config.TEST_START, config.VAL_START,
                      *(s for s, _ in extra_holdouts or ())):
            excluded |= embargo_mask(t, start, embargo_hours)

    return df[~excluded].copy(), df[val_mask].copy(), df[test_mask].copy()


def horizon_metrics(
    test: pd.DataFrame,
    train: pd.DataFrame,
    predictions: dict[int, np.ndarray],
) -> list[dict]:
    """Model error against persistence and climatology at each lead time."""
    rows = []
    for lead, pred in sorted(predictions.items()):
        truth = test[f"target_{lead}h"].to_numpy(dtype=float)
        pers = baselines.persistence(test, lead)
        clim = baselines.climatology(train, test, lead)

        model_mae = baselines.mae(truth, pred)
        pers_mae = baselines.mae(truth, pers)
        clim_mae = baselines.mae(truth, clim)

        rows.append(
            {
                "lead_hours": lead,
                "model_mae": round(model_mae, 2),
                "persistence_mae": round(pers_mae, 2),
                "climatology_mae": round(clim_mae, 2),
                "improvement_vs_persistence": round(baselines.skill(model_mae, pers_mae), 4),
            }
        )
    return rows


def _exceedance_events(times: np.ndarray, values: np.ndarray, threshold: float, gap_h: int = 6):
    """Contiguous runs where observed PM2.5 sits above threshold.

    Runs separated by less than `gap_h` are merged: a brief dip mid-episode is
    the same event to anyone acting on it.
    """
    above = values >= threshold
    events: list[tuple[np.datetime64, np.datetime64]] = []
    start = None
    last = None
    for i, flag in enumerate(above):
        if flag:
            if start is None:
                start = times[i]
            last = times[i]
        elif start is not None:
            gap = (times[i] - last) / np.timedelta64(1, "h")
            if gap >= gap_h:
                events.append((start, last))
                start = None
    if start is not None:
        events.append((start, last))
    return events


def alert_metrics(
    test: pd.DataFrame,
    forecasts: dict[int, np.ndarray],
    horizon: int = 24,
    trigger: dict[int, np.ndarray] | None = None,
    receptors: Sequence[str] | None = None,
) -> dict:
    """Hit rate, false alarm rate and warning lead time, per institution then pooled.

    An hour counts as a *warning* if any available lead time predicts a breach.
    It counts as an *event hour* if the observed value breaches within the
    horizon. Lead time is measured per distinct observed episode: how far ahead
    of its onset the first correct warning was issued.

    `trigger` supplies an alternative set of predictions to fire alerts on -
    normally the upper prediction band. A warning system is not a regression
    scoreboard: missing an episode costs a school an outdoor assembly in
    hazardous air, while a false alarm costs an unnecessary indoor day. Those
    are not symmetric, so alerting on the upper band and accepting more false
    alarms is the correct trade, not a way of flattering the numbers. Both
    rates are reported so the trade stays visible.

    `receptors` restricts scoring to the given institution ids - pass
    `distinct_receptors(df)` to score one site per distinct PM2.5 series rather
    than counting each duplicated trio three times. Defaults to None, which
    scores every institution exactly as before, so the published artifacts stay
    reproducible from this function unchanged.
    """
    keep = None if receptors is None else set(receptors)
    frame = test.copy().reset_index(drop=True)
    for lead, pred in forecasts.items():
        frame[f"_pred_{lead}"] = pred
    trigger = trigger or forecasts
    for lead, pred in trigger.items():
        frame[f"_trig_{lead}"] = pred

    leads = sorted(forecasts)
    hits = misses = false_alarms = 0
    lead_times: list[float] = []
    events_total = 0

    for inst_id, group in frame.groupby("institution_id"):
        inst = BY_ID.get(inst_id)
        if inst is None or (keep is not None and inst_id not in keep):
            continue
        threshold = thresholds.alert_threshold(inst.type).pm25

        group = group.sort_values("time").reset_index(drop=True)
        times = group["time"].to_numpy()
        observed = group["pm25"].to_numpy(dtype=float)

        # Predicted breach within the horizon, from each issuance hour.
        predicted = np.zeros(len(group), dtype=bool)
        for lead in leads:
            col = f"_trig_{lead}" if f"_trig_{lead}" in group else f"_pred_{lead}"
            predicted |= group[col].to_numpy(dtype=float) >= threshold

        # Observed breach within the horizon, from each issuance hour.
        actual = np.zeros(len(group), dtype=bool)
        for lead in range(1, horizon + 1):
            col = f"target_{lead}h"
            if col in group:
                actual |= group[col].to_numpy(dtype=float) >= threshold

        valid = ~np.isnan(observed)
        hits += int(np.sum(predicted & actual & valid))
        misses += int(np.sum(~predicted & actual & valid))
        false_alarms += int(np.sum(predicted & ~actual & valid))

        # Lead time per observed episode.
        for onset, _ in _exceedance_events(times, observed, threshold):
            events_total += 1
            window = (times >= onset - np.timedelta64(horizon, "h")) & (times < onset)
            warned = np.where(window & predicted)[0]
            if warned.size:
                first = times[warned[0]]
                lead_times.append(float((onset - first) / np.timedelta64(1, "h")))

    denom_hit = hits + misses
    denom_far = hits + false_alarms
    return {
        "hit_rate": round(hits / denom_hit, 4) if denom_hit else 0.0,
        "false_alarm_rate": round(false_alarms / denom_far, 4) if denom_far else 0.0,
        "median_lead_time_hours": round(float(np.median(lead_times)), 1) if lead_times else 0.0,
        "events_evaluated": events_total,
    }

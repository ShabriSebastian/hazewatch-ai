"""Evaluation, including the metrics that actually matter to a decision-maker.

Regression error is necessary but not sufficient. What a head teacher cares
about is: when the air was going to become dangerous, did this system tell me,
how often did it cry wolf, and how much notice did I get? Those three questions
are answered here as hit rate, false alarm rate and lead time.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

from .. import config
from ..alerts import thresholds
from ..institutions import BY_ID
from . import baselines


def spatial_resolution(df: pd.DataFrame) -> dict:
    """The disclosure block: what the PM2.5 source can and cannot tell apart.

    Published alongside the metrics rather than buried in a diagnostic, because
    every per-institution figure in this system is really a per-locality figure
    and a reader cannot tell that from the output alone.
    """
    groups = receptor_groups(df)
    return {
        "source": "CAMS reanalysis via Open-Meteo",
        "native_resolution_deg": 0.4,
        "note": (
            "CAMS global composition is ~0.4 degrees native. The Pontianak "
            "institutions sit ~3 km apart, as do the Kuching ones, so each trio "
            "shares one grid cell and receives an identical PM2.5 series. "
            "Forecasts and alerts are per-locality, not per-institution. "
            "Institutions listed together cannot be distinguished by this data "
            "source, and no metric here should be read as evidence about one "
            "site rather than its locality."
        ),
        "groups": groups,
        "distinct_receptors": len(groups),
        "institutions": int(df["institution_id"].nunique()),
    }


def wilson_ci95(successes: int, trials: int) -> tuple[float, float] | None:
    """95% Wilson score interval for a proportion.

    Wilson rather than the normal approximation, and rather than a percentile
    bootstrap. Episode counts here are small (33 and 21 on the two validation
    windows) and the rates sit near the top of the range, where both
    alternatives misbehave: the normal approximation runs past 1.0, and the
    bootstrap returns a degenerate upper edge - resampling 31 successes out of
    33 puts an all-successes draw well inside the 97.5th percentile, so the
    interval reports exactly 100%. Wilson stays inside [0, 1] and stays honest
    at the tails: the same 31/33 gives [80.4%, 98.3%].
    """
    if trials <= 0:
        return None
    z = 1.959963984540054
    p = successes / trials
    denom = 1 + z * z / trials
    centre = p + z * z / (2 * trials)
    margin = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials))
    return ((centre - margin) / denom, (centre + margin) / denom)


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
    return list(receptor_groups(df))


def receptor_groups(df: pd.DataFrame) -> dict[str, list[str]]:
    """Map each distinct PM2.5 series to every institution sharing it.

    The grouping *is* the spatial-resolution disclosure: any institution listed
    under another's key is not independently resolved by the data, and a
    forecast for one is a forecast for all of them. Callers surface this so a
    reader never has to infer it from six identical-looking rows.
    """
    groups: dict[str, list[str]] = {}
    seen: list[tuple[str, pd.Series]] = []
    for inst_id in sorted(df["institution_id"].unique()):
        series = df.loc[df["institution_id"] == inst_id].set_index("time")["pm25"]
        match = next((rep for rep, other in seen if series.equals(other)), None)
        if match is None:
            seen.append((inst_id, series))
            groups[inst_id] = [inst_id]
        else:
            groups[match].append(inst_id)
    return groups


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


def episode_detection_flags(
    test: pd.DataFrame,
    trigger: dict[int, np.ndarray],
    receptors: Sequence[str] | None = None,
    horizon: int = 24,
) -> list[tuple[str, np.datetime64, int]]:
    """Per distinct observed episode: `(institution_id, onset, warned)`.

    `alert_metrics` returns the detection *rate*; this returns the outcomes
    behind it, keyed by episode, so two models can be compared on the same
    episodes rather than through two independent intervals. With 21 episodes in
    the 2024 window, the paired comparison is the only one with any power - an
    unpaired test at that size can barely distinguish anything from anything.
    """
    keep = set(receptors) if receptors is not None else set(distinct_receptors(test))
    frame = test.copy().reset_index(drop=True)
    for lead, pred in trigger.items():
        frame[f"_trig_{lead}"] = pred

    out: list[tuple[str, np.datetime64, int]] = []
    for inst_id, group in frame.groupby("institution_id"):
        inst = BY_ID.get(inst_id)
        if inst is None or inst_id not in keep:
            continue
        threshold = thresholds.alert_threshold(inst.type).pm25
        group = group.sort_values("time").reset_index(drop=True)
        times = group["time"].to_numpy()
        observed = group["pm25"].to_numpy(dtype=float)

        predicted = np.zeros(len(group), dtype=bool)
        for lead in sorted(trigger):
            predicted |= group[f"_trig_{lead}"].to_numpy(dtype=float) >= threshold

        for onset, _ in _exceedance_events(times, observed, threshold):
            window = (times >= onset - np.timedelta64(horizon, "h")) & (times < onset)
            out.append((inst_id, onset, int(bool(np.any(window & predicted)))))
    return out


def alert_metrics(
    test: pd.DataFrame,
    forecasts: dict[int, np.ndarray],
    horizon: int = 24,
    trigger: dict[int, np.ndarray] | None = None,
    receptors: Sequence[str] | None = None,
) -> dict:
    """Alert performance, scored per locality then pooled.

    Two rates are co-primary, because they answer different questions and take
    different values:

    * **hit_rate** is *hour-level*: of the issuance hours with a breach coming
      inside the horizon, how many carried a warning. This is the figure the
      published artifacts report.
    * **episode_detection_rate** is *episode-level*: of the distinct observed
      episodes, how many were warned about at all before onset. This is what a
      head teacher means by "did you warn me about this episode", and it runs
      well above the hour-level rate - 93.9% against 79.5% on the 2023 window.

    Reporting only the first understates the system; reporting only the second
    flatters it. Both are returned, and `episode_detection_ci95` comes with the
    episode-level one because its denominator is small enough to matter.

    `specificity` is reported alongside `false_alarm_rate` for a reason worth
    stating: false alarm rate is 1 - precision, so it moves with how often the
    event happens even when the model has not changed. Comparing it across two
    seasons with different base rates is what made the 2024 validation look like
    a regression when specificity had in fact improved, 80.0% to 90.3%.
    Specificity is prevalence-free and is the figure to compare across years.

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
    # Episode-level figures are always counted over genuinely distinct PM2.5
    # series, whether or not the caller deduplicated the hour-level scoring.
    # Counting the Pontianak and Kuching trios three times each is what inflated
    # 33 episodes to 99, and no metric downstream of here should inherit that.
    distinct = set(distinct_receptors(test))
    if keep is not None:
        distinct &= keep

    frame = test.copy().reset_index(drop=True)
    for lead, pred in forecasts.items():
        frame[f"_pred_{lead}"] = pred
    trigger = trigger or forecasts
    for lead, pred in trigger.items():
        frame[f"_trig_{lead}"] = pred

    leads = sorted(forecasts)
    hits = misses = false_alarms = true_negatives = 0
    lead_times: list[float] = []
    events_total = 0
    distinct_episodes = 0
    distinct_detected = 0

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
        true_negatives += int(np.sum(~predicted & ~actual & valid))

        # Lead time per observed episode, and whether the episode was caught at
        # all. The second is only counted for distinct receptors - resampling or
        # rating the duplicated trios would treat one episode as three.
        is_distinct = inst_id in distinct
        for onset, _ in _exceedance_events(times, observed, threshold):
            events_total += 1
            window = (times >= onset - np.timedelta64(horizon, "h")) & (times < onset)
            warned = np.where(window & predicted)[0]
            if is_distinct:
                distinct_episodes += 1
                distinct_detected += int(warned.size > 0)
            if warned.size:
                first = times[warned[0]]
                lead_times.append(float((onset - first) / np.timedelta64(1, "h")))

    denom_hit = hits + misses
    denom_far = hits + false_alarms
    denom_spec = true_negatives + false_alarms
    denom_prev = hits + misses + false_alarms + true_negatives
    ci = wilson_ci95(distinct_detected, distinct_episodes)
    return {
        "hit_rate": round(hits / denom_hit, 4) if denom_hit else 0.0,
        "false_alarm_rate": round(false_alarms / denom_far, 4) if denom_far else 0.0,
        "specificity": round(true_negatives / denom_spec, 4) if denom_spec else 0.0,
        "alertable_hour_prevalence": (
            round(denom_hit / denom_prev, 4) if denom_prev else 0.0
        ),
        "median_lead_time_hours": round(float(np.median(lead_times)), 1) if lead_times else 0.0,
        "events_evaluated": events_total,
        "distinct_episodes": distinct_episodes,
        "episode_detection_rate": (
            round(distinct_detected / distinct_episodes, 4) if distinct_episodes else 0.0
        ),
        "episode_detection_ci95": None if ci is None else [round(ci[0], 4), round(ci[1], 4)],
    }

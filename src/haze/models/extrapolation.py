"""Detecting when the forecast has left the range the model was trained on.

A tree ensemble predicts the average of the training targets that fall in each
leaf. It therefore *cannot* return a value above its training maximum, no matter
how extreme the inputs get. Our training targets top out near 113 ug/m3; the
held-out September 2023 episode reached 307. The forecast for that hour reads
around 86 - not because the model failed, but because 86 is roughly the highest
average any leaf can offer.

That distinction is invisible in a number. A chart drawn from the raw point
forecast next to an observed 307 reads as a broken model. So the API says so
explicitly, per forecast point, and the frontend renders "beyond the model's
trained range" instead of a falsely precise figure.

There are in fact *two* ceilings, and the lower one is what binds:

* the **data ceiling** - the largest training target, 112.9 ug/m3;
* the **model ceiling** - the largest value the forest can actually emit, which
  is strictly lower. Each tree returns a leaf mean over at least
  `min_samples_leaf=20` training rows, so no leaf is a pure extreme. Measured
  across the persisted forests, the highest reachable upper-band value is about
  90 ug/m3, and the highest reachable ensemble mean about 83. The model runs out
  of range a full 20 ug/m3 below the point the training data runs out.

That is measurable directly from the persisted trees - `tree_.value.max()` per
estimator - so the bound is derived from the model we actually serve rather than
assumed from the data.

Two independent signals, either of which is sufficient:

* **Band saturation** - the upper band has climbed to within a fraction of the
  model ceiling *for that lead time*. The ensemble is pressed against its own
  structural limit and cannot report anything worse, so the number has stopped
  being a severity estimate and become a floor.

* **Feature novelty** - some input feature falls outside the range the model ever
  saw in training. During the 2023 episode this fires for interpretable reasons:
  unprecedented local fire radiative power, and `pm25_lag_*` above 112.9, meaning
  the model is being shown a present-tense concentration it has never seen.

Deliberately free of any sklearn import - the forests are only ever duck-typed
for `.estimators_[i].tree_.value` - so the fixture store can apply exactly the
same rule as the real precompute path and the two payload shapes stay identical.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from .. import config

METHOD = "random_forest_tree_quantiles"

# Features whose range is fixed by construction rather than learned from data.
# One-hot site identity is always 0 or 1 (`site_` + institution id, so
# `site_id-ptk-sman1` and `site_my-kch-greenroad`); sine/cosine encodings are
# always in [-1, 1]. Including them would mean every point is trivially "in
# range" on 12 of 37 features, diluting the signal without adding information.
BOUNDED_SUFFIXES = ("_sin", "_cos")
BOUNDED_PREFIXES = ("site_",)

REASON_SATURATED = "band_saturated"
REASON_FEATURE = "feature_out_of_range"
REASON_BOTH = "both"


def is_learned_range(feature: str) -> bool:
    """True for features whose training range is empirical, not structural."""
    return not (
        feature.startswith(BOUNDED_PREFIXES) or feature.endswith(BOUNDED_SUFFIXES)
    )


def training_ranges(train, features: list[str]) -> dict:
    """Summarise what the model actually saw during training.

    `train` must be the training split - use `evaluate.split(df)[0]`, so the
    held-out demo episode cannot leak in and quietly raise the ceiling it is
    supposed to be measured against.

    The target ceiling is computed across every lead time rather than taken from
    `pm25`, because that is the quantity a forecast prediction is bounded by. It
    is derived here rather than written down anywhere: a hardcoded 113 would go
    silently stale the first time the data window moved.
    """
    targets = [c for c in train.columns if c.startswith("target_")]
    if not targets:
        raise ValueError("No target_* columns found; cannot derive a training ceiling.")

    ceiling = float(np.nanmax(train[targets].to_numpy(dtype=float)))

    ranges: dict[str, dict[str, float]] = {}
    for name in features:
        if not is_learned_range(name) or name not in train.columns:
            continue
        column = train[name].replace([np.inf, -np.inf], np.nan)
        lo, hi = float(column.min()), float(column.max())
        if not (np.isfinite(lo) and np.isfinite(hi)):
            continue
        ranges[name] = {"lo": lo, "hi": hi}

    return {
        "target_max_pm25": round(ceiling, 1),
        "observed_max_pm25": round(float(np.nanmax(train["pm25"].to_numpy(dtype=float))), 1),
        "saturation_fraction": config.EXTRAPOLATION_SATURATION_FRACTION,
        "n_train_rows": int(len(train)),
        "features": ranges,
    }


def model_ceilings(models: dict, upper_percentile: int | None = None) -> dict:
    """The highest values each forest can structurally emit, per lead time.

    A decision tree returns the mean of the training targets in whichever leaf an
    input lands in, so the largest output tree `t` can ever produce is
    `t.tree_.value.max()`. It follows that across the ensemble:

    * the mean prediction is bounded by the mean of the per-tree maxima;
    * the p-th percentile of the tree predictions is bounded by the p-th
      percentile of those same maxima.

    These are the numbers the band is actually pressed against - materially lower
    than the training target maximum, because `min_samples_leaf=20` means every
    leaf averages at least twenty rows and none is a pure extreme.

    Reads only `.estimators_` and `.tree_.value`, so no sklearn import is needed.
    """
    upper_percentile = upper_percentile or config.ALERT_TRIGGER_PERCENTILE
    by_lead: dict[str, dict[str, float]] = {}
    for lead, model in models.items():
        maxima = np.array([est.tree_.value.max() for est in model.estimators_], dtype=float)
        by_lead[str(int(lead))] = {
            "mean": round(float(maxima.mean()), 2),
            "upper": round(float(np.percentile(maxima, upper_percentile)), 2),
            "max": round(float(maxima.max()), 2),
        }

    uppers = [v["upper"] for v in by_lead.values()]
    return {
        "upper_percentile": int(upper_percentile),
        "by_lead": by_lead,
        "mean_upper": round(float(np.mean(uppers)), 1),
        "min_upper": round(float(np.min(uppers)), 1),
        "max_upper": round(float(np.max(uppers)), 1),
    }


def saturation_threshold(ranges: dict, lead_hours: int | None = None) -> float | None:
    """The `pm25_upper` value at which the band counts as pressed against the ceiling.

    Returns None when no model ceiling has been measured, which disables the
    saturation signal rather than silently falling back to a wrong reference.
    Measuring against the *training target* maximum would never fire: the forests
    top out around 90, so a fraction of 112.9 is unreachable by construction.
    """
    ceilings = ranges.get("model_ceiling")
    if not ceilings:
        return None

    fraction = float(
        ranges.get("saturation_fraction", config.EXTRAPOLATION_SATURATION_FRACTION)
    )
    by_lead = ceilings.get("by_lead", {})
    ceiling = by_lead.get(str(int(lead_hours))) if lead_hours is not None else None
    reference = ceiling["upper"] if ceiling else ceilings.get("mean_upper")
    if reference is None:
        return None
    return float(reference) * fraction


def out_of_range_features(row, ranges: dict) -> list[str]:
    """Names of features whose value falls outside the training range.

    Hard min/max, not a percentile envelope. p1/p99 would flag roughly 2% of
    perfectly ordinary hours by construction, which is far too noisy for a
    per-point boolean: the flag has to mean "the model is off its map", not
    "this hour was somewhat unusual".
    """
    outside = []
    for name, bounds in ranges.get("features", {}).items():
        value = row.get(name) if hasattr(row, "get") else None
        if value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(value):
            continue
        if value < bounds["lo"] or value > bounds["hi"]:
            outside.append(name)
    return outside


def combine(saturated: bool, novel: bool) -> tuple[bool, str | None]:
    """Fold the two signals into the flag and its reason.

    Split out from `classify` so the precompute path can evaluate feature
    novelty once per issuance row and reuse it across all 24 lead times, instead
    of rescanning 25 feature ranges twenty-four times over.
    """
    if saturated and novel:
        return True, REASON_BOTH
    if saturated:
        return True, REASON_SATURATED
    if novel:
        return True, REASON_FEATURE
    return False, None


def classify(
    pm25_upper: float | None,
    row,
    ranges: dict,
    lead_hours: int | None = None,
) -> tuple[bool, str | None]:
    """Whether this forecast point has left the model's trained range, and why.

    `row` may be None where no feature vector is available (the fixture store),
    in which case only the band-saturation signal applies. Note the asymmetry:
    saturation is a property of the individual point, while feature novelty is a
    property of the issuance - one out-of-range input taints every lead time
    forecast from it, which is the honest reading.
    """
    threshold = saturation_threshold(ranges, lead_hours)
    saturated = (
        pm25_upper is not None
        and threshold is not None
        and float(pm25_upper) >= threshold
    )
    novel = bool(out_of_range_features(row, ranges)) if row is not None else False
    return combine(saturated, novel)


def summarise(points: list[dict], ranges: dict) -> dict:
    """The response-level `uncertainty` block for one forecast issuance.

    Carries the percentiles the band has always used - undocumented until now -
    so the frontend need not hardcode them, and a sentence it can render as-is.
    """
    flagged = [p for p in points if p.get("beyond_training_range")]
    from_lead = min((int(p["lead_hours"]) for p in flagged), default=None)
    data_ceiling = float(ranges["target_max_pm25"])
    model_ceiling = (ranges.get("model_ceiling") or {}).get("mean_upper")

    if from_lead is None:
        note = (
            "This forecast stays inside the range the model was trained on; read "
            "the values as ordinary predictions."
        )
    else:
        note = (
            f"From +{from_lead}h this forecast is beyond the model's trained range. A "
            f"tree ensemble averages training targets within each leaf, so it cannot "
            f"report above about {model_ceiling:g} ug/m3 however bad the air actually "
            f"gets. Read the value as a floor, not a severity estimate: alert timing "
            f"is unaffected, but for real severity use the observed reading from "
            f"/institutions/{{id}}/observation."
        ) if model_ceiling else (
            f"From +{from_lead}h this forecast is beyond the model's trained range. "
            f"Read the value as a floor, not a severity estimate."
        )

    return {
        "method": METHOD,
        "lower_percentile": config.BAND_LOWER_PERCENTILE,
        "upper_percentile": config.ALERT_TRIGGER_PERCENTILE,
        "n_estimators": config.RF_N_ESTIMATORS,
        "training_target_max_pm25": round(data_ceiling, 1),
        "model_ceiling_pm25": model_ceiling,
        "any_point_beyond_training_range": bool(flagged),
        "beyond_training_range_from_lead_hours": from_lead,
        "note": note,
    }


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------
def write_training_ranges(ranges: dict, path: Path | None = None) -> Path:
    path = Path(path or config.TRAINING_RANGES_JSON)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(ranges, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


@lru_cache(maxsize=4)
def load_training_ranges(path: Path | None = None) -> dict | None:
    """Read the measured ranges, or None when they have never been written.

    Cached: the fixture store consults this on every forecast request, and the
    file only changes when the pipeline is re-run, which restarts the process.
    """
    path = Path(path or config.TRAINING_RANGES_JSON)
    if not path.exists():
        return None
    with path.open() as fh:
        return json.load(fh)

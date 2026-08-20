#!/usr/bin/env python3
"""Rescore both validation runs on distinct receptors instead of duplicated ones.

The six institutions are not six independent receptors. CAMS global composition
is ~0.4 degrees native; the three Pontianak sites sit ~3 km apart, as do the
three Kuching sites, so Open-Meteo returns a byte-identical PM2.5 series for
every member of each trio. Verified at the source rather than inferred: the six
cached requests snapped to five distinct grid cells and returned two distinct
`pm2_5` arrays. Nothing in this repository broadcasts a city value across a
trio - each institution is fetched separately, on its own cache key.

Every count in both published runs is therefore inflated threefold. This script
reports each run twice - exactly as published, and deduplicated - so the
difference is visible rather than asserted.

    python scripts/09_rescore_dedup.py        (make rescore)

Two things this script must never do, matching `scripts/06_validate_events.py`:

* **It never writes to `models/v1/`.** The served metrics and the competition
  artifacts stay byte-identical. Output goes to `diagnostics/`.
* **It never touches `data/replay/`.** Served artifacts are re-checksummed
  before exiting and any movement fails the run.

Output: `diagnostics/dedup_rescore.json`.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from haze import config  # noqa: E402
from haze.models import evaluate, rf  # noqa: E402

# Imported rather than redefined: the whole point is to reproduce the published
# runs before correcting them, and a second copy of these constants would drift.
# Loaded by path because the module name starts with a digit, so `import` cannot
# reach it. Its `__main__` guard means nothing executes on import.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_validate_events", Path(__file__).resolve().parent / "06_validate_events.py"
)
_validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_validate)

ALL_HORIZONS = _validate.ALL_HORIZONS
SECOND_EVENT = _validate.SECOND_EVENT
EMBARGO_HOURS = _validate.EMBARGO_HOURS
SERVED_ARTIFACTS = _validate.SERVED_ARTIFACTS
_checksums = _validate._checksums

OUT_DIR = config.ROOT / "diagnostics"
OUT_JSON = OUT_DIR / "dedup_rescore.json"

BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 42


# --------------------------------------------------------------------------
def bootstrap_ci(flags: list[int]) -> dict:
    """95% percentile bootstrap interval for a rate over distinct episodes."""
    if not flags:
        return {"n_episodes": 0, "point": None, "ci95_low": None, "ci95_high": None}
    arr = np.asarray(flags, dtype=float)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = rng.choice(arr, size=(BOOTSTRAP_DRAWS, arr.size), replace=True).mean(axis=1)
    return {
        "n_episodes": int(arr.size),
        "point": round(float(arr.mean()), 4),
        "ci95_low": round(float(np.percentile(draws, 2.5)), 4),
        "ci95_high": round(float(np.percentile(draws, 97.5)), 4),
    }


def score_both_ways(
    models: dict, features: list[str], train: pd.DataFrame, frame: pd.DataFrame, label: str
) -> dict:
    """Alert metrics for one window, as published and deduplicated."""
    print(f"\n  scoring {label} ({len(frame):,} rows)")

    predictions: dict[int, np.ndarray] = {}
    bands: dict[int, np.ndarray] = {}
    for lead, model in sorted(models.items()):
        mean, quantiles = rf.predict_quantiles(
            model, frame, features, log=rf.LOG_FORECAST,
            percentiles=(config.ALERT_TRIGGER_PERCENTILE,),
        )
        predictions[lead] = mean
        bands[lead] = quantiles[config.ALERT_TRIGGER_PERCENTILE]

    receptors = evaluate.distinct_receptors(frame)
    as_published = evaluate.alert_metrics(frame, predictions, trigger=bands)
    dedup = evaluate.alert_metrics(frame, predictions, trigger=bands, receptors=receptors)

    # Episode detection and its interval now come from `evaluate.alert_metrics`
    # itself (Phase 2B), so there is one implementation rather than two. The
    # local bootstrap is kept below only to record what it produced, since the
    # Phase 2A report quotes it.
    ci = {
        "n_episodes": dedup["distinct_episodes"],
        "point": dedup["episode_detection_rate"],
        "ci95_low": dedup["episode_detection_ci95"][0],
        "ci95_high": dedup["episode_detection_ci95"][1],
        "method": "wilson",
    }
    bootstrap = bootstrap_ci(
        [w for _, _, w in evaluate.episode_detection_flags(frame, bands, receptors)]
    )

    # Prevalence and the prevalence-free false-positive rate. FAR is 1-precision
    # and moves with the base rate on its own, which is exactly how the original
    # cross-year comparison went wrong; specificity does not.
    sub = frame[frame["institution_id"].isin(receptors)]
    target_cols = [f"target_{lead}h" for lead in ALL_HORIZONS if f"target_{lead}h" in sub]
    actual = (sub[target_cols].to_numpy(dtype=float) >= 35.5).any(axis=1)
    prevalence = float(actual.mean())
    hit, far = dedup["hit_rate"], dedup["false_alarm_rate"]
    tp = hit * prevalence
    fp = (far / (1 - far) * tp) if far < 1 else float("nan")
    fpr = fp / (1 - prevalence) if prevalence < 1 else float("nan")

    print(
        f"    as published : hit {as_published['hit_rate']:.1%}  "
        f"FAR {as_published['false_alarm_rate']:.1%}  "
        f"episodes {as_published['events_evaluated']}"
    )
    print(
        f"    deduplicated : hit {dedup['hit_rate']:.1%}  "
        f"FAR {dedup['false_alarm_rate']:.1%}  "
        f"episodes {dedup['events_evaluated']}"
    )
    print(
        f"    episode detection (distinct, not the hour-level hit rate): "
        f"{ci['point']:.1%} of {ci['n_episodes']}  "
        f"95% CI [{ci['ci95_low']:.1%}, {ci['ci95_high']:.1%}] (Wilson; "
        f"bootstrap gave [{bootstrap['ci95_low']:.1%}, {bootstrap['ci95_high']:.1%}])"
    )
    print(f"    prevalence {prevalence:.2%}   specificity {1 - fpr:.1%}  (FPR {fpr:.1%})")

    return {
        "as_published": as_published,
        "deduplicated": dedup,
        "receptors_scored": receptors,
        "episode_detection_rate": ci,
        "episode_detection_rate_bootstrap": bootstrap,
        "alertable_hour_prevalence": round(prevalence, 4),
        "false_positive_rate": round(float(fpr), 4),
        "specificity": round(float(1 - fpr), 4),
        "peak_observed_pm25": round(float(frame["pm25"].max()), 1),
    }


# --------------------------------------------------------------------------
def main() -> int:
    if not config.FEATURES_PARQUET.exists():
        print("No features found. Run scripts/02_build_features.py first.")
        return 1

    before = _checksums(SERVED_ARTIFACTS)

    df = pd.read_parquet(config.FEATURES_PARQUET)
    with config.FEATURE_SPEC.open() as fh:
        features = json.load(fh)["features"]

    receptors = evaluate.distinct_receptors(df)
    print(
        f"Distinct PM2.5 receptors: {len(receptors)} of "
        f"{df['institution_id'].nunique()} institutions -> {', '.join(receptors)}"
    )

    results: dict[str, dict] = {}

    # -- primary: the served model on its own held-out 2023 window ---------
    served_path = config.MODELS / "rf_forecast.joblib"
    if not served_path.exists():
        print(f"Missing {served_path} - run scripts/03_train.py first.")
        return 1

    print(f"\nLoading served model ({served_path.stat().st_size / 1e9:.1f} GB)...")
    bundle = joblib.load(served_path)
    served_train, _, test_2023 = evaluate.split(df)
    results["primary_served_2023"] = score_both_ways(
        bundle["models"], bundle["features"], served_train, test_2023,
        "primary / served model / 2023",
    )
    del bundle

    # -- validation model: both events withheld, exactly as published ------
    train, _, val_test_2023 = evaluate.split(
        df, extra_holdouts=[SECOND_EVENT], embargo_hours=EMBARGO_HOURS
    )
    start, end = SECOND_EVENT
    test_2024 = df[(df["time"] >= start) & (df["time"] <= end + " 23:59:59")].copy()

    print(
        f"\nRetraining the validation model ({len(ALL_HORIZONS)} forests, "
        f"{len(train):,} rows, both events withheld)..."
    )
    models = rf.train_forecast(train, features, ALL_HORIZONS)

    results["validation_2023"] = score_both_ways(
        models, features, train, val_test_2023, "validation model / 2023"
    )
    results["validation_2024"] = score_both_ways(
        models, features, train, test_2024, "validation model / 2024"
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "purpose": (
            "Phase 2A: rescore both validation runs on distinct PM2.5 receptors. "
            "The three Pontianak institutions share one CAMS series and the three "
            "Kuching institutions share another, so every published count is "
            "inflated threefold. Internal reporting - models/v1 is not modified."
        ),
        "root_cause": (
            "Upstream CAMS resolution (~0.4 deg native), not a join or broadcast "
            "defect. Six separate requests on six distinct cache keys snapped to "
            "five Open-Meteo grid cells and returned two distinct pm2_5 arrays."
        ),
        "distinct_receptors": receptors,
        "n_institutions": int(df["institution_id"].nunique()),
        "runs": results,
        "notes": [
            "as_published reproduces the figures in models/v1/metrics.json and "
            "metrics_by_event.json; deduplicated scores one institution per "
            "distinct observed PM2.5 series.",
            "episode_detection_rate is NOT the published hit_rate. hit_rate is "
            "hour-level (of issuance hours with a breach coming, how many carried "
            "a warning); episode_detection_rate is episode-level (of distinct "
            "observed episodes, how many were warned about before onset). Both "
            "are reported; they take different values.",
            "Only the episode-level rate carries a bootstrap interval, resampled "
            "over distinct episodes. Issuance hours within an episode are "
            "autocorrelated, so a naive interval on hit_rate would be far too "
            "narrow, and two receptors leave no honest way to widen it.",
            "specificity / false_positive_rate are prevalence-free and are the "
            "figures to compare across years; FAR is 1-precision and is not.",
            "models/v1 and data/replay are not written by this script.",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    print(f"\nWrote {OUT_JSON}")

    after = _checksums(SERVED_ARTIFACTS)
    moved = [p for p in before if before[p] != after.get(p)]
    if moved:
        print("\nFAILED: this script modified served artifacts:")
        for path in moved:
            print(f"  - {path}")
        return 1
    print(f"Served artifacts unchanged ({len(before)} checked): the demo is untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Freeze the demo scenario into data/replay/scenario_2023_sept.sqlite.

Runs offline from cached data and trained models. The output is the artifact the
recorded demo reads: no inference, no network, identical on every take.

    python scripts/04_precompute_scenario.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from haze import config  # noqa: E402
from haze.features import build as feature_build  # noqa: E402
from haze.institutions import INSTITUTIONS  # noqa: E402
from haze.models import evaluate, extrapolation, rf  # noqa: E402
from haze.pipeline import precompute  # noqa: E402


def main() -> int:
    for path, hint in (
        (config.FEATURES_PARQUET, "scripts/02_build_features.py"),
        (config.MODELS / "rf_forecast.joblib", "scripts/03_train.py"),
    ):
        if not path.exists():
            print(f"Missing {path}. Run {hint} first.")
            return 1

    features = pd.read_parquet(config.FEATURES_PARQUET)
    bundle = joblib.load(config.MODELS / "rf_forecast.joblib")
    models, model_features = bundle["models"], bundle["features"]
    log_space = bundle.get("log", False)

    # What the model was trained on, and where it structurally runs out of range.
    # Both are measured here rather than written down: the training split comes
    # from the same `evaluate.split` the training run used, so the held-out
    # episode cannot leak in and raise the ceiling it is judged against.
    train, _, _ = evaluate.split(features)
    training_ranges = extrapolation.training_ranges(train, model_features)
    training_ranges["model_ceiling"] = extrapolation.model_ceilings(
        models, config.ALERT_TRIGGER_PERCENTILE
    )
    extrapolation.write_training_ranges(training_ranges)

    ceiling = training_ranges["model_ceiling"]
    print(
        f"  training target max {training_ranges['target_max_pm25']} ug/m3; "
        f"forest can reach {ceiling['mean_upper']} at p{ceiling['upper_percentile']} "
        f"(range {ceiling['min_upper']}-{ceiling['max_upper']})"
    )

    metrics = {}
    if config.METRICS_JSON.exists():
        with config.METRICS_JSON.open() as fh:
            metrics = json.load(fh)
    top_features = metrics.get("top_features", [])
    model_name = metrics.get("model_name", "rf-forecast")

    baselines_by_lead = {}
    for row in metrics.get("horizons", []):
        if row["lead_hours"] == 24:
            baselines_by_lead = {
                "persistence_mae": row["persistence_mae"],
                "climatology_mae": row["climatology_mae"],
                "model_mae": row["model_mae"],
            }

    start = config.parse_ts(config.SCENARIO_START)
    end = config.parse_ts(config.SCENARIO_END)

    print(f"Precomputing {config.SCENARIO_NAME}")
    print(f"  window {config.SCENARIO_START} .. {config.SCENARIO_END}")

    # -- forecasts for every hour of the window ---------------------------
    forecasts: dict[str, dict] = {}
    for inst in INSTITUTIONS:
        site = features[
            (features["institution_id"] == inst.id)
            & (features["time"] >= start)
            & (features["time"] <= end)
        ].sort_values("time").reset_index(drop=True)

        if site.empty:
            print(f"  ! no rows for {inst.id}")
            continue

        # Predict every lead time for every issuance hour in one pass per lead.
        # The p50 rides along free: all three percentiles come off the same
        # per-tree matrix, so this costs no extra forest evaluations.
        lower_p = config.BAND_LOWER_PERCENTILE
        upper_p = config.ALERT_TRIGGER_PERCENTILE
        preds: dict[int, np.ndarray] = {}
        bands: dict[int, dict[int, np.ndarray]] = {}
        for lead, model in sorted(models.items()):
            mean, quantiles = rf.predict_quantiles(
                model,
                site,
                model_features,
                log=log_space,
                percentiles=(lower_p, 50, upper_p),
            )
            preds[lead], bands[lead] = mean, quantiles

        # Feature novelty is a property of the issuance row, not of a lead time:
        # one out-of-range input taints every forecast made from it.
        novel_by_row = [
            bool(extrapolation.out_of_range_features(row, training_ranges))
            for _, row in site.iterrows()
        ]

        by_issue: dict[str, list[dict]] = {}
        flagged_points = 0
        for i, issued in enumerate(site["time"]):
            points = []
            for lead in sorted(models):
                upper = bands[lead][upper_p][i]
                saturation = extrapolation.saturation_threshold(training_ranges, lead)
                saturated = saturation is not None and float(upper) >= saturation
                beyond, reason = extrapolation.combine(saturated, novel_by_row[i])
                flagged_points += bool(beyond)
                points.append(
                    precompute._point(
                        issued + pd.Timedelta(hours=lead),
                        lead,
                        preds[lead][i],
                        bands[lead][lower_p][i],
                        upper,
                        median=bands[lead][50][i],
                        beyond_training_range=beyond,
                        extrapolation_reason=reason,
                    )
                )
            by_issue[precompute._iso(issued)] = points
        forecasts[inst.id] = by_issue
        total = len(by_issue) * len(models)
        print(
            f"  {inst.id:20s} {len(by_issue):,} issuance hours   "
            f"{flagged_points:,}/{total:,} points beyond trained range "
            f"({100 * flagged_points / total:.1f}%)"
        )

    # -- hotspots ---------------------------------------------------------
    print("\nLoading hotspots for the window...")
    hotspots = feature_build.load_hotspots()

    print("\nWriting scenario database...")
    precompute.write_scenario(
        features=features,
        hotspots=hotspots,
        forecasts=forecasts,
        top_features=top_features,
        baselines_by_lead=baselines_by_lead,
        model_name=model_name,
        training_ranges=training_ranges,
    )

    print("\nDone. The API will now serve real precomputed data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

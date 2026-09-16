#!/usr/bin/env python3
"""Phase 2B/2C: the corrected metrics report, threshold recalibration, extremes.

`models/v1/metrics.json` is frozen for competition reproducibility, so it cannot
carry the co-primary metric set the review asked for. This produces the report
equivalent instead, plus the two experiments that need no model change.

    python scripts/10_metrics_and_calibration.py        (make report)

Outputs, all under `diagnostics/`:

    metrics_report.json / .md   corrected co-primary metrics + spatial disclosure
    calibration_2024.json       2C.1 threshold recalibration grid
    extremes_2023.json          2C.2 above-training-range behaviour

The validation model is retrained here because `06_validate_events.py`
deliberately never persists it. No model weights that anything serves are
touched: `models/v1/` and `data/replay/` are re-checksummed before exit.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from haze import config  # noqa: E402
from haze.alerts import thresholds  # noqa: E402
from haze.models import evaluate, rf  # noqa: E402

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

OUT = config.ROOT / "diagnostics"
ALERT_PM25 = thresholds.alert_threshold("school").pm25  # 35.5, the EPA floor
SWEEP_PERCENTILES = (75, 80, 85, 90, 95)
# Decision thresholds to sweep, in ug/m3. Spans well below and above the EPA
# floor so the shape of the trade-off is visible, not just its neighbourhood.
# The EPA floor itself is forced into the grid: it is the incumbent operating
# point, and a sweep that cannot price its own baseline is useless. It does not
# fall on a 2.5-wide lattice, which is exactly how it went missing the first time.
SWEEP_THRESHOLDS = tuple(
    sorted({float(t) for t in np.arange(15.0, 65.1, 2.5)} | {ALERT_PM25})
)

CACHE = OUT / "predictions_cache.npz"


def predict_all(models: dict, features: list[str], frame: pd.DataFrame) -> dict:
    """Point forecast and every sweep percentile, one pass over the trees."""
    means: dict[int, np.ndarray] = {}
    bands: dict[int, dict[int, np.ndarray]] = {}
    for lead, model in sorted(models.items()):
        mean, quantiles = rf.predict_quantiles(
            model, frame, features, log=rf.LOG_FORECAST, percentiles=SWEEP_PERCENTILES
        )
        means[lead], bands[lead] = mean, quantiles
    return {"mean": means, "bands": bands}


def cache_key(name: str, lead: int, pct: int | None = None) -> str:
    return f"{name}|mean|{lead}" if pct is None else f"{name}|p{pct}|{lead}"


def save_cache(preds: dict[str, dict]) -> None:
    """Persist predictions so re-analysis costs no retraining.

    Retraining the validation model is ~10 minutes, and every question asked of
    these numbers after the fact - a different threshold grid, a different
    stratification - needs the same arrays back. Caching them makes a second
    look cheap enough to actually take.
    """
    flat: dict[str, np.ndarray] = {}
    for name, pred in preds.items():
        for lead, arr in pred["mean"].items():
            flat[cache_key(name, lead)] = arr
            for pct, band in pred["bands"][lead].items():
                flat[cache_key(name, lead, pct)] = band
    np.savez_compressed(CACHE, **flat)
    (OUT / "predictions_cache.meta.json").write_text(
        json.dumps(
            {
                "model_version": config.MODEL_VERSION,
                "written_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "percentiles": list(SWEEP_PERCENTILES),
                "sets": sorted(preds),
                "note": (
                    "Predictions only - no model weights. Delete this pair to force "
                    "a retrain. Stale if features.parquet or the model changes."
                ),
            },
            indent=2,
        )
        + "\n"
    )


def load_cache(names: list[str]) -> dict[str, dict] | None:
    """Reload cached predictions, or None if absent or incomplete."""
    if not CACHE.exists():
        return None
    with np.load(CACHE) as data:
        keys = set(data.files)
        out: dict[str, dict] = {}
        for name in names:
            means, bands = {}, {}
            for lead in ALL_HORIZONS:
                if cache_key(name, lead) not in keys:
                    return None
                means[lead] = data[cache_key(name, lead)]
                bands[lead] = {
                    pct: data[cache_key(name, lead, pct)] for pct in SWEEP_PERCENTILES
                }
            out[name] = {"mean": means, "bands": bands}
    return out


def trigger_at(bands: dict, percentile: int, threshold: float) -> dict[int, np.ndarray]:
    """Trigger series for `band >= threshold`, expressed for `alert_metrics`.

    `alert_metrics` always compares against the EPA floor, which is correct - the
    alert means "forecast to reach the level EPA names for sensitive groups" and
    that meaning should not be a tunable. To sweep a different decision threshold
    without loosening that, rescale the trigger instead: comparing
    `band * (35.5 / T)` against 35.5 is exactly `band >= T`, and leaves the
    observed side of every comparison untouched.
    """
    scale = ALERT_PM25 / threshold
    return {lead: bands[lead][percentile] * scale for lead in bands}


def scored(frame: pd.DataFrame, pred: dict, receptors, percentile: int, threshold: float) -> dict:
    return evaluate.alert_metrics(
        frame,
        pred["mean"],
        trigger=trigger_at(pred["bands"], percentile, threshold),
        receptors=receptors,
    )


# --------------------------------------------------------------------------
def metrics_markdown(payload: dict) -> str:
    """The corrected model card, as prose a reviewer can read without jq."""
    sp = payload["spatial_resolution"]
    lines = [
        "# HazeWatch AI — corrected metrics report",
        "",
        f"Generated {payload['generated_at']}. Model version "
        f"`{payload['model_version']}`, unchanged by this report.",
        "",
        "> This supersedes the alert figures in `models/v1/metrics.json`, which is",
        "> left frozen for competition reproducibility and predates the receptor fix.",
        "> Episode counts there are inflated threefold; the counts below are distinct.",
        "",
        "## Spatial resolution — what the data can tell apart",
        "",
        f"**Source:** {sp['source']}, ~{sp['native_resolution_deg']}° native.  ",
        f"**{sp['institutions']} institutions resolve to {sp['distinct_receptors']} "
        f"receptors.**",
        "",
        "| Receptor | Institutions sharing this grid cell |",
        "|---|---|",
    ]
    for rep, members in sp["groups"].items():
        lines.append(f"| `{rep}` | {', '.join(f'`{m}`' for m in members)} |")
    lines += [
        "",
        sp["note"],
        "",
        "Forecasts and alerts are **per-locality, not per-institution**. Three Pontianak "
        "alerts agreeing is one forecast shown three times, not three confirmations.",
        "",
        "## Alert performance",
        "",
        "Two rates are co-primary. `hit rate` is hour-level; `episode detection` is the "
        "share of distinct observed episodes warned about before onset. "
        "`specificity` is prevalence-free and is the figure to compare across seasons — "
        "`false alarm rate` is 1−precision and moves with the base rate on its own.",
        "",
        "| Run | Hit rate (hourly) | Episode detection (95% CI) | Specificity | FAR | Prevalence | Distinct episodes |",
        "|---|---|---|---|---|---|---|",
    ]
    for key, run in payload["runs"].items():
        a = run["alerts"]
        ci = a["episode_detection_ci95"]
        lines.append(
            f"| {run['label']} | {a['hit_rate']:.1%} | "
            f"{a['episode_detection_rate']:.1%} [{ci[0]:.1%}, {ci[1]:.1%}] | "
            f"{a['specificity']:.1%} | {a['false_alarm_rate']:.1%} | "
            f"{a['alertable_hour_prevalence']:.1%} | {a['distinct_episodes']} |"
        )
    lines += [
        "",
        f"Alerts fire on the p{config.ALERT_TRIGGER_PERCENTILE} band at the EPA "
        f"`UNHEALTHY_SENSITIVE` floor of {ALERT_PM25} µg/m³.",
        "",
        "## Notes",
        "",
    ]
    lines += [f"- {n}" for n in payload["notes"]]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
def calibration(frame: pd.DataFrame, pred: dict, receptors) -> dict:
    """2C.1 - does a 2024-tuned decision threshold beat the primary-tuned one?"""
    grid = []
    for pct in SWEEP_PERCENTILES:
        for t in SWEEP_THRESHOLDS:
            m = scored(frame, pred, receptors, pct, t)
            grid.append(
                {
                    "percentile": pct,
                    "threshold_pm25": round(t, 2),
                    "hit_rate": m["hit_rate"],
                    "false_alarm_rate": m["false_alarm_rate"],
                    "specificity": m["specificity"],
                    "episode_detection_rate": m["episode_detection_rate"],
                    "median_lead_time_hours": m["median_lead_time_hours"],
                }
            )

    current = next(
        r for r in grid
        if r["percentile"] == config.ALERT_TRIGGER_PERCENTILE
        and abs(r["threshold_pm25"] - ALERT_PM25) < 1e-6
    )
    # Best hit rate among points whose false alarm rate matches the primary run's
    # published 25.4%, and best Youden's J anywhere on the grid.
    matched = [r for r in grid if r["false_alarm_rate"] <= 0.254]
    best_matched = max(matched, key=lambda r: r["hit_rate"]) if matched else None
    best_j = max(grid, key=lambda r: r["hit_rate"] + r["specificity"] - 1)
    return {
        "grid": grid,
        "current_operating_point": current,
        "best_at_primary_false_alarm_rate": best_matched,
        "best_youden_j": best_j,
        "caveat": (
            f"{ALERT_PM25} ug/m3 is the EPA UNHEALTHY_SENSITIVE floor, not a tuned "
            "number. Moving it means the alert stops meaning 'forecast to reach the "
            "level EPA names for sensitive groups', which is a change to what the "
            "product claims, not a calibration. Reported as measurement; the "
            "recommendation is stated separately."
        ),
    }


def extremes(frame: pd.DataFrame, pred: dict, train_max: float) -> dict:
    """2C.2 - behaviour above the training range. A 2023 issue, not a 2024 one."""
    leads = sorted(pred["mean"])
    obs = np.column_stack([frame[f"target_{lead}h"].to_numpy(dtype=float) for lead in leads])
    fc = np.column_stack([pred["mean"][lead] for lead in leads])
    band = np.column_stack([pred["bands"][lead][config.ALERT_TRIGGER_PERCENTILE] for lead in leads])

    valid = ~np.isnan(obs)
    alertable = valid & (obs >= ALERT_PM25)
    beyond = valid & (obs > train_max)

    # Per issuance hour: was a warning raised for any lead, and did any lead's
    # observation go beyond the training range?
    hour_beyond = beyond.any(axis=1)
    hour_alertable = alertable.any(axis=1)
    hour_warned = (band >= ALERT_PM25).any(axis=1)

    cat_obs = [thresholds.categorise(v) for v in obs[beyond]]
    cat_fc = [thresholds.categorise(v) for v in fc[beyond]]
    understated = sum(
        thresholds.CATEGORY_RANK[f] < thresholds.CATEGORY_RANK[o]
        for f, o in zip(cat_fc, cat_obs)
    )

    return {
        "training_target_max_pm25": train_max,
        "forecast_pairs_evaluated": int(valid.sum()),
        "alertable_pairs": int(alertable.sum()),
        "pairs_beyond_training_range": int(beyond.sum()),
        "share_of_alertable_beyond_range": (
            round(float(beyond.sum() / alertable.sum()), 4) if alertable.sum() else 0.0
        ),
        "observed_on_those_pairs": {
            "min": round(float(obs[beyond].min()), 1) if beyond.any() else None,
            "median": round(float(np.median(obs[beyond])), 1) if beyond.any() else None,
            "max": round(float(obs[beyond].max()), 1) if beyond.any() else None,
        },
        "forecast_on_those_pairs": {
            "min": round(float(fc[beyond].min()), 1) if beyond.any() else None,
            "median": round(float(np.median(fc[beyond])), 1) if beyond.any() else None,
            "max": round(float(fc[beyond].max()), 1) if beyond.any() else None,
        },
        "median_shortfall_pm25": (
            round(float(np.median(obs[beyond] - fc[beyond])), 1) if beyond.any() else None
        ),
        "alert_still_fired_on_beyond_range_hours": (
            round(float(hour_warned[hour_beyond].mean()), 4) if hour_beyond.any() else None
        ),
        "alert_fired_on_all_alertable_hours": (
            round(float(hour_warned[hour_alertable].mean()), 4) if hour_alertable.any() else None
        ),
        "severity_category_understated": understated,
        "severity_category_understated_share": (
            round(understated / int(beyond.sum()), 4) if beyond.any() else None
        ),
        "interpretation": (
            "The ceiling costs severity accuracy, not detection: the alert threshold "
            "is 35.5 ug/m3 and these hours observe far above it, so a forecast capped "
            "near the training maximum still crosses the threshold and still fires. "
            "What the user loses is the size of the number and the category attached "
            "to it. This is a primary-validation (2023) issue only - the 2024 window "
            "peaks at 66.4 ug/m3 and never approaches the ceiling."
        ),
    }


# --------------------------------------------------------------------------
def main() -> int:
    if not config.FEATURES_PARQUET.exists():
        print("No features found. Run scripts/02_build_features.py first.")
        return 1

    before = _checksums(SERVED_ARTIFACTS)
    OUT.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(config.FEATURES_PARQUET)
    with config.FEATURE_SPEC.open() as fh:
        features = json.load(fh)["features"]

    spatial = evaluate.spatial_resolution(df)
    receptors = list(spatial["groups"])
    print(
        f"Spatial resolution: {spatial['institutions']} institutions -> "
        f"{spatial['distinct_receptors']} receptors {receptors}"
    )

    runs: dict[str, dict] = {}

    _, _, test_2023 = evaluate.split(df)
    train, _, val_2023 = evaluate.split(
        df, extra_holdouts=[SECOND_EVENT], embargo_hours=EMBARGO_HOURS
    )
    start, end = SECOND_EVENT
    test_2024 = df[(df["time"] >= start) & (df["time"] <= end + " 23:59:59")].copy()

    names = ["served_2023", "validation_2023", "validation_2024"]
    cached = load_cache(names)
    if cached is not None:
        print("\nReusing cached predictions (delete diagnostics/predictions_cache.npz "
              "to force a retrain).")
        preds = cached
    else:
        print("\nLoading served model...")
        bundle = joblib.load(config.MODELS / "rf_forecast.joblib")
        preds = {"served_2023": predict_all(bundle["models"], bundle["features"], test_2023)}
        del bundle

        print(f"Retraining the validation model ({len(train):,} rows)...")
        models = rf.train_forecast(train, features, ALL_HORIZONS)
        preds["validation_2023"] = predict_all(models, features, val_2023)
        preds["validation_2024"] = predict_all(models, features, test_2024)
        save_cache(preds)
        print(f"  cached predictions to {CACHE.name}")

    pred_served = preds["served_2023"]
    pred_val_2023 = preds["validation_2023"]
    pred_2024 = preds["validation_2024"]

    runs["primary_served_2023"] = {
        "label": "Primary — served model, Aug–Oct 2023",
        "alerts": scored(test_2023, pred_served, receptors,
                         config.ALERT_TRIGGER_PERCENTILE, ALERT_PM25),
    }

    runs["validation_2023"] = {
        "label": "Validation model, Aug–Oct 2023",
        "alerts": scored(val_2023, pred_val_2023, receptors,
                         config.ALERT_TRIGGER_PERCENTILE, ALERT_PM25),
    }
    runs["validation_2024"] = {
        "label": "Validation model, Aug–Oct 2024",
        "alerts": scored(test_2024, pred_2024, receptors,
                         config.ALERT_TRIGGER_PERCENTILE, ALERT_PM25),
    }

    for key, run in runs.items():
        a = run["alerts"]
        ci = a["episode_detection_ci95"]
        print(
            f"\n  {run['label']}\n"
            f"    hit {a['hit_rate']:.1%} (hourly)   episode detection "
            f"{a['episode_detection_rate']:.1%} of {a['distinct_episodes']} "
            f"[{ci[0]:.1%}, {ci[1]:.1%}]\n"
            f"    specificity {a['specificity']:.1%}   FAR {a['false_alarm_rate']:.1%}"
            f"   prevalence {a['alertable_hour_prevalence']:.1%}"
        )

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_version": config.MODEL_VERSION,
        "supersedes": "models/v1/metrics.json alert figures (frozen, pre-deduplication)",
        "spatial_resolution": spatial,
        "runs": runs,
        "notes": [
            "PM2.5 targets are ECMWF CAMS reanalysis, not ground-station measurements.",
            "Hotspots are NASA FIRMS detections; this system does not detect fires itself.",
            "Episode counts are distinct counts. The events_evaluated field in "
            "models/v1/metrics.json counts every institution and reports 99 where "
            "there are 33; it is superseded, not corrected in place.",
            "hit_rate is hour-level; episode_detection_rate is episode-level. Both are "
            "reported because they answer different questions and differ materially.",
            "specificity is prevalence-free. false_alarm_rate is 1-precision and is not "
            "comparable across seasons with different base rates.",
        ],
    }
    (OUT / "metrics_report.json").write_text(json.dumps(report, indent=2) + "\n")
    (OUT / "metrics_report.md").write_text(metrics_markdown(report))
    print(f"\nWrote {OUT / 'metrics_report.json'} and .md")

    # -- 2C.1 -------------------------------------------------------------
    print("\nSweeping decision thresholds on 2024...")
    calib = calibration(test_2024, pred_2024, receptors)
    calib["primary_reference"] = {
        "note": "The operating point p90 / 35.5 was selected on 2023 alone.",
        "primary_2023": runs["primary_served_2023"]["alerts"],
    }
    (OUT / "calibration_2024.json").write_text(json.dumps(calib, indent=2) + "\n")
    cur, bm, bj = (calib["current_operating_point"],
                   calib["best_at_primary_false_alarm_rate"], calib["best_youden_j"])
    print(
        f"  current  p{cur['percentile']} / {cur['threshold_pm25']}: "
        f"hit {cur['hit_rate']:.1%}  FAR {cur['false_alarm_rate']:.1%}  "
        f"episode {cur['episode_detection_rate']:.1%}"
    )
    if bm:
        print(
            f"  FAR<=25.4% p{bm['percentile']} / {bm['threshold_pm25']}: "
            f"hit {bm['hit_rate']:.1%}  FAR {bm['false_alarm_rate']:.1%}  "
            f"episode {bm['episode_detection_rate']:.1%}"
        )
    print(
        f"  best J   p{bj['percentile']} / {bj['threshold_pm25']}: "
        f"hit {bj['hit_rate']:.1%}  FAR {bj['false_alarm_rate']:.1%}  "
        f"specificity {bj['specificity']:.1%}  episode {bj['episode_detection_rate']:.1%}"
    )

    # -- 2C.2 -------------------------------------------------------------
    print("\nAnalysing behaviour above the training range (2023)...")
    ranges = json.loads((config.MODELS / "training_ranges.json").read_text())
    ext = extremes(test_2023, pred_served, float(ranges["target_max_pm25"]))
    (OUT / "extremes_2023.json").write_text(json.dumps(ext, indent=2) + "\n")
    print(
        f"  {ext['pairs_beyond_training_range']:,} of {ext['alertable_pairs']:,} "
        f"alertable forecast pairs observe above the {ext['training_target_max_pm25']} "
        f"ug/m3 training max ({ext['share_of_alertable_beyond_range']:.1%})"
    )
    print(
        f"  median observed {ext['observed_on_those_pairs']['median']} vs forecast "
        f"{ext['forecast_on_those_pairs']['median']} "
        f"(shortfall {ext['median_shortfall_pm25']} ug/m3)"
    )
    print(
        f"  alert still fired on {ext['alert_still_fired_on_beyond_range_hours']:.1%} of "
        f"those hours; severity understated on "
        f"{ext['severity_category_understated_share']:.1%} of pairs"
    )

    after = _checksums(SERVED_ARTIFACTS)
    moved = [p for p in before if before[p] != after.get(p)]
    if moved:
        print("\nFAILED: served artifacts modified:")
        for path in moved:
            print(f"  - {path}")
        return 1
    print(f"\nServed artifacts unchanged ({len(before)} checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

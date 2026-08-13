#!/usr/bin/env python3
"""Train models and write honest held-out metrics. Runs offline.

    python scripts/03_train.py            # Random Forest only
    python scripts/03_train.py --gru      # also train the GRU (needs torch)
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
from haze.models import baselines, evaluate, extrapolation, rf  # noqa: E402

# Every lead time is trained, so the demo can draw a smooth hourly curve.
# Metrics are reported at the three headline horizons.
ALL_HORIZONS = tuple(range(1, config.FORECAST_HORIZON_HOURS + 1))
REPORT_HORIZONS = (6, 12, 24)


def main() -> int:
    want_gru = "--gru" in sys.argv

    if not config.FEATURES_PARQUET.exists():
        print("No features found. Run scripts/02_build_features.py first.")
        return 1

    df = pd.read_parquet(config.FEATURES_PARQUET)
    with config.FEATURE_SPEC.open() as fh:
        features = json.load(fh)["features"]

    train, val, test = evaluate.split(df)
    print(f"Split: train={len(train):,}  val={len(val):,}  test={len(test):,}")
    print(f"  test window {config.TEST_START} .. {config.TEST_END} (held out entirely)")

    # -- attribution model ------------------------------------------------
    print("\nTraining RF-attribution (fire and weather only)...")
    attr_model, attr_cols = rf.train_attribution(train, features)
    attr_pred = rf.predict(attr_model, test, attr_cols, log=rf.LOG_ATTRIBUTION)

    truth = test["pm25"].to_numpy(dtype=float)
    attr_r2 = baselines.r2(truth, attr_pred)
    # Raw-space R2 is structurally unflattering here: the held-out episode peaks
    # far above anything in the training window, and a tree ensemble cannot
    # predict beyond its training range. Log-space R2 measures whether the model
    # tracks the shape of an episode, which is what drives alert timing.
    attr_r2_log = baselines.r2(
        np.log1p(np.clip(truth, 0, None)), np.log1p(np.clip(attr_pred, 0, None))
    )
    print(f"  held-out R2 (log space) = {attr_r2_log:.3f}   <- primary")
    print(f"  held-out R2 (raw)       = {attr_r2:.3f}")
    print(f"  {len(attr_cols)} features: no PM2.5 lags, no day-of-year")

    top_features = rf.importances(attr_model, attr_cols, top=12)
    print("  top drivers:")
    for row in top_features[:6]:
        print(f"    {row['feature']:24s} {row['contribution']:.3f}")

    # -- forecast model ---------------------------------------------------
    print(f"\nTraining RF-forecast ({len(ALL_HORIZONS)} lead times)...")
    fc_models = rf.train_forecast(train, features, ALL_HORIZONS)
    predictions = {
        lead: rf.predict(m, test, features, log=rf.LOG_FORECAST)
        for lead, m in fc_models.items()
    }

    # Alerts fire on the upper prediction band, not the point forecast: a missed
    # episode and a false alarm carry very different costs.
    def band(percentile: int) -> dict:
        return {
            lead: rf.predict_with_spread(
                m, test, features, log=rf.LOG_FORECAST, upper=percentile
            )[2]
            for lead, m in fc_models.items()
        }

    upper = band(config.ALERT_TRIGGER_PERCENTILE)

    reported = {k: v for k, v in predictions.items() if k in REPORT_HORIZONS}
    horizons = evaluate.horizon_metrics(test, train, reported)
    print(f"\n  {'lead':>5}  {'model':>7}  {'persist':>8}  {'clim':>7}   skill")
    for row in horizons:
        print(
            f"  {row['lead_hours']:>4}h  {row['model_mae']:>7.2f}  "
            f"{row['persistence_mae']:>8.2f}  {row['climatology_mae']:>7.2f}   "
            f"{row['improvement_vs_persistence']:+.1%}"
        )

    alerts = evaluate.alert_metrics(test, predictions, trigger=upper)

    # Record the whole trade-off curve, so the chosen operating point is a
    # visible decision rather than a tuned number.
    trigger_sweep = []
    for pct in (75, 80, 85, 90, 95):
        row = evaluate.alert_metrics(test, predictions, trigger=band(pct))
        trigger_sweep.append(
            {
                "percentile": pct,
                "hit_rate": row["hit_rate"],
                "false_alarm_rate": row["false_alarm_rate"],
                "median_lead_time_hours": row["median_lead_time_hours"],
            }
        )
    point_only = evaluate.alert_metrics(test, predictions)
    print(
        f"\n  Alerting on the point forecast alone would give "
        f"hit {point_only['hit_rate']:.1%} / false alarm {point_only['false_alarm_rate']:.1%}"
    )
    print(
        f"\n  Alert performance (triggered on p{config.ALERT_TRIGGER_PERCENTILE} band):"
    )
    print(f"    hit rate           {alerts['hit_rate']:.1%}")
    print(f"    false alarm rate   {alerts['false_alarm_rate']:.1%}")
    print(f"    median lead time   {alerts['median_lead_time_hours']:.0f} h")
    print(f"    episodes evaluated {alerts['events_evaluated']}")

    model_name = "rf-forecast"
    notes = [
        "PM2.5 targets are ECMWF CAMS reanalysis, not ground-station measurements.",
        "Hotspots are NASA FIRMS detections; this system does not detect fires itself.",
        "The held-out episode peaks above the training maximum (307 vs 113 ug/m3), "
        "which a tree ensemble cannot extrapolate past; the model therefore "
        "under-predicts the most extreme hours. r2_attribution is reported in log "
        "space for that reason, and the forecast is trained in raw space.",
        "Alerts trigger on the upper prediction band rather than the point forecast: "
        "a missed episode and a false alarm carry very different costs. Both rates "
        "are reported.",
        f"Test window {config.TEST_START}..{config.TEST_END} excluded from training.",
    ]

    # -- optional GRU -----------------------------------------------------
    if want_gru:
        try:
            from haze.models import gru

            print("\nTraining GRU...")
            gru_result = gru.train_and_evaluate(df, features, train, val, test)

            # Promotion is decided against the Random Forest, not against
            # persistence: beating a trivial baseline is the entry requirement,
            # not a reason to replace a model that already works.
            rf_24 = next(h["model_mae"] for h in horizons if h["lead_hours"] == 24)
            gru_24 = (
                next(
                    h["model_mae"]
                    for h in gru_result["horizons"]
                    if h["lead_hours"] == 24
                )
                if gru_result
                else None
            )

            if gru_result and gru_24 is not None and gru_24 < rf_24:
                horizons = gru_result["horizons"]
                alerts = gru_result["alerts"]
                model_name = "gru-multisite"
                print(
                    f"  GRU +24h MAE {gru_24:.2f} beats RF {rf_24:.2f} - promoted."
                )
                notes.append(
                    f"A GRU was promoted over the Random Forest on held-out data "
                    f"(+24h MAE {gru_24:.2f} vs {rf_24:.2f} ug/m3)."
                )
            else:
                shown = f"{gru_24:.2f}" if gru_24 is not None else "n/a"
                notes.append(
                    f"A GRU was trained but did not beat the Random Forest on "
                    f"held-out data (+24h MAE {shown} vs {rf_24:.2f} ug/m3); the "
                    f"Random Forest is served instead."
                )
                print(f"  GRU +24h MAE {shown} vs RF {rf_24:.2f} - keeping the RF.")
        except ImportError:
            print("\n  torch not installed - skipping GRU. (pip install torch)")

    # -- persist ----------------------------------------------------------
    config.MODELS.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": attr_model, "features": attr_cols, "log": rf.LOG_ATTRIBUTION},
        config.MODELS / "rf_attribution.joblib"
    )
    joblib.dump(
        {
            "models": fc_models,
            "features": features,
            "horizons": list(ALL_HORIZONS),
            "log": rf.LOG_FORECAST,
        },
        config.MODELS / "rf_forecast.joblib",
    )

    # What the model saw, and where it structurally runs out of range. Refreshed
    # on every retrain so the ceiling the API publishes can never describe a
    # model that is no longer being served.
    ranges = extrapolation.training_ranges(train, features)
    ranges["model_ceiling"] = extrapolation.model_ceilings(
        fc_models, config.ALERT_TRIGGER_PERCENTILE
    )
    extrapolation.write_training_ranges(ranges)
    print(
        f"\n  training target max {ranges['target_max_pm25']} ug/m3; forest reaches "
        f"{ranges['model_ceiling']['mean_upper']} at p{config.ALERT_TRIGGER_PERCENTILE}"
    )

    metrics = {
        "model_name": model_name,
        "model_version": config.MODEL_VERSION,
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "train_period": f"{config.HISTORY_START}..{config.HISTORY_END} minus val and test",
        "test_period": f"{config.TEST_START}..{config.TEST_END}",
        "test_period_held_out": True,
        "r2_attribution": round(attr_r2_log, 4),
        "r2_attribution_raw": round(attr_r2, 4),
        "horizons": horizons,
        "alerts": alerts,
        "top_features": top_features,
        "alert_trigger_percentile": config.ALERT_TRIGGER_PERCENTILE,
        "trigger_sweep": trigger_sweep,
        "notes": notes,
    }
    with config.METRICS_JSON.open("w") as fh:
        json.dump(metrics, fh, indent=2)

    print(f"\nWrote {config.METRICS_JSON}")
    print(f"Wrote models to {config.MODELS}")

    at24 = next((h for h in horizons if h["lead_hours"] == 24), None)
    if at24 and at24["improvement_vs_persistence"] < 0.15:
        print(
            f"\n  WARNING: +24h skill is {at24['improvement_vs_persistence']:+.1%}, "
            "below the 15% bar set in the plan."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

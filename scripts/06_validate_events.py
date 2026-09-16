#!/usr/bin/env python3
"""Score the model on two independent held-out events, to show it generalises.

One held-out episode proves the model was not fitted to its own test set. It does
not prove the result survives a different year, a different fire season, or a
different balance between the two receptors - and a reviewer is entitled to
suspect a single validation event of being the flattering one.

So this trains a *second* model with **both** events withheld and scores each of
them with the same metrics the served model publishes. The point of comparison is
not "is this model better" but "does the same pipeline reach the same conclusion
on data it has never seen twice over".

    python scripts/06_validate_events.py        (make validate)

Two things this script must never do, because the demo depends on them:

* **It never writes to `models/v1/*.joblib`.** The forests it trains are held in
  memory and discarded. Training is deterministic (`random_state=42`), so the run
  reproduces on demand and there is no reason to persist 1.9 GB of forests that
  are not served. The served model keeps 2024 in its training set and is
  unchanged by anything here.
* **It never touches `data/replay/`.** The Sept 2023 demo scenario must return
  byte-identical payloads afterwards. The script re-checksums the served
  artifacts before exiting and fails loudly if any of them moved.

Output: `models/v1/metrics_by_event.json`. Internal reporting only - nothing here
reaches the frozen API contract.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from haze import config  # noqa: E402
from haze.alerts import thresholds  # noqa: E402
from haze.institutions import INSTITUTIONS  # noqa: E402
from haze.models import evaluate, rf  # noqa: E402

ALL_HORIZONS = tuple(range(1, config.FORECAST_HORIZON_HOURS + 1))
REPORT_HORIZONS = (6, 12, 24)
SWEEP_PERCENTILES = (75, 80, 85, 90, 95)

# Targets reaching into a held-out window are dropped from training. See
# `evaluate.embargo_mask` for why this is worth 0.13% of the training rows.
EMBARGO_HOURS = 24

# The second event. Deliberately the *same calendar window* as the 2023 holdout
# in a different year, so the choice of dates involves no selection at all - a
# window tuned around the episode would be exactly the cherry-picking this script
# exists to rule out.
SECOND_EVENT = ("2024-08-16", "2024-10-15")

EVENTS = [
    {
        "key": "sept_2023",
        "label": "Pontianak / Kuching, Aug-Oct 2023",
        "window": (config.TEST_START, config.TEST_END),
        "role": "original held-out event (also the demo scenario)",
    },
    {
        "key": "sept_2024",
        "label": "Kuching-dominant transboundary episode, Aug-Oct 2024",
        "window": SECOND_EVENT,
        "role": "second held-out event, added to test generalisation",
    },
]

# Scanned and rejected. Reported rather than quietly dropped: "why not 2022?" is
# the first question a reviewer asks, and the evidence is computed below rather
# than asserted, so the answer cannot go stale.
REJECTED = [
    {
        "key": "sept_2022",
        "window": ("2022-08-16", "2022-10-15"),
        "reason": (
            "Kuching never crosses the 35.5 ug/m3 alert threshold in this window, so "
            "two of the three Sarawak institutions record zero alertable events and "
            "the transboundary claim - the product's headline - cannot be tested. "
            "Upwind fire activity is roughly a sixth of 2024's, consistent with the "
            "third year of a triple-dip La Nina suppressing Indonesian burning."
        ),
    }
]


# --------------------------------------------------------------------------
# Reconnaissance - how a candidate window was judged
# --------------------------------------------------------------------------
def reconnaissance(df: pd.DataFrame, start: str, end: str) -> dict:
    """The season statistics used to accept or reject a candidate event.

    Computed from the data every run. The 2022 rejection in particular is an
    argument made to a reviewer, and an argument backed by a hardcoded number is
    worth very little.
    """
    window = df[(df["time"] >= start) & (df["time"] <= end + " 23:59:59")]
    target_cols = [f"target_{lead}h" for lead in ALL_HORIZONS]

    per_city: dict[str, dict] = {}
    for label, country in (("pontianak", "ID"), ("kuching", "MY")):
        ids = [i.id for i in INSTITUTIONS if i.country == country]
        site = window[window["institution_id"] == ids[0]]
        per_city[label] = {
            "peak_pm25": round(float(site["pm25"].max()), 1),
            "hours_above_alert_threshold": int((site["pm25"] >= 35.5).sum()),
        }

    per_institution = []
    for inst in INSTITUTIONS:
        site = window[window["institution_id"] == inst.id].sort_values("time")
        threshold = thresholds.alert_threshold(inst.type).pm25
        breaches = (site[target_cols].to_numpy(dtype=float) >= threshold).any(axis=1)
        observed = site["pm25"].to_numpy(dtype=float) >= threshold
        episodes = int(np.sum(observed[1:] & ~observed[:-1]) + observed[:1].sum())
        per_institution.append(
            {
                "institution_id": inst.id,
                "country": inst.country,
                "threshold_pm25": threshold,
                "alertable_event_hours": int(breaches.sum()),
                "observed_episodes": episodes,
            }
        )

    kuching = window[window["institution_id"].str.startswith("my-")]
    from_id = float(kuching["ufei_from_ID"].sum())
    from_my = float(kuching["ufei_from_MY"].sum())
    total = from_id + from_my

    return {
        "window": f"{start}..{end}",
        "cities": per_city,
        "institutions": per_institution,
        "total_alertable_event_hours": sum(
            r["alertable_event_hours"] for r in per_institution
        ),
        "total_observed_episodes": sum(r["observed_episodes"] for r in per_institution),
        "indonesian_share_of_upwind_exposure_at_kuching": (
            round(from_id / total, 4) if total > 0 else None
        ),
        "max_upwind_hotspots_150_400km": int(kuching["hotspots_150_400km"].max()),
    }


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
def score_event(models, features, train, frame, label: str) -> dict:
    """Horizon skill and alert performance for one held-out window.

    Uses exactly the metric functions the served model publishes, so the numbers
    in the two artifacts are directly comparable rather than merely similar.
    """
    print(f"\n  scoring {label} ({len(frame):,} rows)")

    # One pass over the trees per lead time yields the mean and every percentile
    # the sweep needs - the trigger sweep is otherwise five redundant passes.
    predictions: dict[int, np.ndarray] = {}
    bands: dict[int, dict[int, np.ndarray]] = {}
    for lead, model in sorted(models.items()):
        mean, quantiles = rf.predict_quantiles(
            model, frame, features, log=rf.LOG_FORECAST, percentiles=SWEEP_PERCENTILES
        )
        predictions[lead], bands[lead] = mean, quantiles

    def trigger(percentile: int) -> dict[int, np.ndarray]:
        return {lead: bands[lead][percentile] for lead in bands}

    reported = {k: v for k, v in predictions.items() if k in REPORT_HORIZONS}
    horizons = evaluate.horizon_metrics(frame, train, reported)
    alerts = evaluate.alert_metrics(
        frame, predictions, trigger=trigger(config.ALERT_TRIGGER_PERCENTILE)
    )

    for row in horizons:
        print(
            f"    {row['lead_hours']:>3}h  MAE {row['model_mae']:>6.2f}  "
            f"persistence {row['persistence_mae']:>6.2f}  "
            f"skill {row['improvement_vs_persistence']:+.1%}"
        )
    print(
        f"    alerts: hit {alerts['hit_rate']:.1%}  "
        f"false alarm {alerts['false_alarm_rate']:.1%}  "
        f"median lead {alerts['median_lead_time_hours']:.0f}h  "
        f"episodes {alerts['events_evaluated']}"
    )

    # Per country. The Sarawak column is the transboundary claim: if it holds on
    # a second event, smoke crossing the border is being predicted, not memorised.
    by_country = {}
    ids = frame["institution_id"].to_numpy()
    for country in ("ID", "MY"):
        keep = np.isin(ids, [i.id for i in INSTITUTIONS if i.country == country])
        if not keep.any():
            continue
        by_country[country] = evaluate.alert_metrics(
            frame[keep],
            {lead: v[keep] for lead, v in predictions.items()},
            trigger={lead: v[keep] for lead, v in trigger(
                config.ALERT_TRIGGER_PERCENTILE).items()},
        )
        print(
            f"      {country}: hit {by_country[country]['hit_rate']:.1%}  "
            f"far {by_country[country]['false_alarm_rate']:.1%}  "
            f"episodes {by_country[country]['events_evaluated']}"
        )

    sweep = []
    for pct in SWEEP_PERCENTILES:
        row = evaluate.alert_metrics(frame, predictions, trigger=trigger(pct))
        sweep.append(
            {
                "percentile": pct,
                "hit_rate": row["hit_rate"],
                "false_alarm_rate": row["false_alarm_rate"],
                "median_lead_time_hours": row["median_lead_time_hours"],
            }
        )

    return {
        "horizons": horizons,
        "alerts": alerts,
        "alerts_by_country": by_country,
        "trigger_sweep": sweep,
        "peak_observed_pm25": round(float(frame["pm25"].max()), 1),
        "rows_evaluated": int(len(frame)),
    }


# --------------------------------------------------------------------------
def _checksums(paths) -> dict[str, str]:
    out = {}
    for path in paths:
        if path.exists():
            out[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


SERVED_ARTIFACTS = [
    config.MODELS / "rf_forecast.joblib",
    config.MODELS / "rf_attribution.joblib",
    config.METRICS_JSON,
    config.SCENARIO_DB,
]


def main() -> int:
    if not config.FEATURES_PARQUET.exists():
        print("No features found. Run scripts/02_build_features.py first.")
        return 1

    before = _checksums(SERVED_ARTIFACTS)

    df = pd.read_parquet(config.FEATURES_PARQUET)
    with config.FEATURE_SPEC.open() as fh:
        features = json.load(fh)["features"]

    # -- reconnaissance ---------------------------------------------------
    print("Candidate windows (identical calendar span, different years):")
    recon = {}
    for label, (start, end) in [
        ("sept_2022", REJECTED[0]["window"]),
        ("sept_2023", EVENTS[0]["window"]),
        ("sept_2024", EVENTS[1]["window"]),
    ]:
        recon[label] = reconnaissance(df, start, end)
        r = recon[label]
        print(
            f"  {label}  PTK peak {r['cities']['pontianak']['peak_pm25']:>6.1f}  "
            f"KCH peak {r['cities']['kuching']['peak_pm25']:>5.1f}  "
            f"KCH hrs>=35.5 {r['cities']['kuching']['hours_above_alert_threshold']:>3d}  "
            f"event-hours {r['total_alertable_event_hours']:>5,}  "
            f"episodes {r['total_observed_episodes']:>3d}"
        )

    # -- the doubly-held-out split ----------------------------------------
    train, _, test_2023 = evaluate.split(
        df, extra_holdouts=[SECOND_EVENT], embargo_hours=EMBARGO_HOURS
    )
    baseline_train, _, _ = evaluate.split(df)
    start, end = SECOND_EVENT
    test_2024 = df[(df["time"] >= start) & (df["time"] <= end + " 23:59:59")].copy()

    print(
        f"\nValidation split: train {len(train):,} rows "
        f"({len(baseline_train) - len(train):,} fewer than the served model), "
        f"holding out both events with a {EMBARGO_HOURS}h embargo."
    )

    # A held-out claim is only worth the check that backs it.
    for label, (a, b) in (("2023", EVENTS[0]["window"]), ("2024", SECOND_EVENT)):
        leaked = ((train["time"] >= a) & (train["time"] <= b + " 23:59:59")).sum()
        if leaked:
            print(f"  ABORT: {leaked} training rows inside the {label} window.")
            return 1
    print("  verified: no training row falls inside either held-out window.")

    # -- train ------------------------------------------------------------
    print(f"\nTraining {len(ALL_HORIZONS)} forests (same hyperparameters as served)...")
    models = rf.train_forecast(train, features, ALL_HORIZONS)

    # -- score ------------------------------------------------------------
    results = []
    frames = {"sept_2023": test_2023, "sept_2024": test_2024}
    for event in EVENTS:
        scored = score_event(models, features, train, frames[event["key"]], event["key"])
        results.append({**{k: v for k, v in event.items() if k != "window"},
                        "window": f"{event['window'][0]}..{event['window'][1]}",
                        **scored})

    # -- the served model's published numbers, for comparison -------------
    served_reference = None
    if config.METRICS_JSON.exists():
        with config.METRICS_JSON.open() as fh:
            served = json.load(fh)
        served_reference = {
            "event": "sept_2023",
            "note": (
                "The served model, whose training set still contains the 2024 season. "
                "Any gap against the validation model's sept_2023 row is the measured "
                "cost of withholding a second haze season, not a regression."
            ),
            "horizons": served.get("horizons"),
            "alerts": served.get("alerts"),
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "purpose": (
            "Generalisation evidence: one pipeline, two independent held-out events, "
            "identical metrics. Internal reporting - not served by the API."
        ),
        "validation_model": {
            "holdouts": [f"{a}..{b}" for a, b in
                         [EVENTS[0]["window"], SECOND_EVENT]],
            "embargo_hours": EMBARGO_HOURS,
            "n_train_rows": int(len(train)),
            "n_train_rows_served_model": int(len(baseline_train)),
            "hyperparameters": {k: v for k, v in rf.RF_PARAMS.items() if k != "n_jobs"},
            "identical_to_served_pipeline": True,
            "persisted": False,
        },
        "events": results,
        "served_model_reference": served_reference,
        "rejected_candidates": [
            {**r, "window": f"{r['window'][0]}..{r['window'][1]}",
             "evidence": recon[r["key"]]}
            for r in REJECTED
        ],
        "reconnaissance": recon,
        "notes": [
            "Both events are withheld from this model's training set, so each is scored "
            "genuinely out of sample. The served model is a different artifact and is "
            "not modified by this script.",
            f"Training rows in the {EMBARGO_HOURS}h before each held-out window are also "
            "dropped: their forecast targets reach inside the window. This makes the "
            "validation holdout marginally stricter than the served model's.",
            "The served model's training set contains the 2024 season, which is why a "
            "second model is trained here rather than scoring 2024 on the served one - "
            "that would be evaluating on seen data.",
            "Alert metrics trigger on the p"
            f"{config.ALERT_TRIGGER_PERCENTILE} prediction band, matching the served "
            "configuration. The full sweep is reported per event.",
            "PM2.5 targets are ECMWF CAMS reanalysis, not ground-station measurements.",
        ],
    }

    config.METRICS_BY_EVENT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with config.METRICS_BY_EVENT_JSON.open("w") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    print(f"\nWrote {config.METRICS_BY_EVENT_JSON}")

    # -- the demo must be exactly where we left it ------------------------
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

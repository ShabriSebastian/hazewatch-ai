#!/usr/bin/env python3
"""Candidate features, added one at a time, never stacked.

2C.2 ruled out model capacity as the reason the forecast underpredicts extreme
episodes, and 2D.0 ruled out fire-feature saturation. What is left is missing
signal: the forecast model has no way to tell one fire season from another,
because `doy_sin`/`doy_cos` take identical values on the same calendar day of
every year.

Arms: `dryness` and `enso` (2D), then `upwind_dryness` (2E), which measures the
dry-day index over the fire source region after the receptor-level version came
back null - the archive had already hinted the location was wrong, since 2024 was
drier at the receptor than 2023 while recording a quarter of the peak PM2.5.

    python scripts/13_ablations.py                          # every arm
    python scripts/13_ablations.py --arms=upwind_dryness    # control + one arm

Design constraints, each with a reason:

* **One feature at a time.** Stacking them would make an improvement
  unattributable, and with a sample this small an unattributable improvement is
  indistinguishable from noise.
* **A control retrain runs first**, on the baseline feature set, through the
  identical code path. If it does not reproduce the published validation figures
  the harness itself is shifting results and no delta below can be trusted.
* **Paired episode outcomes** are recorded against the control, because two
  independent confidence intervals over 21 episodes can barely distinguish
  anything from anything.
* **Nothing on disk changes.** The features are added in memory;
  `data/processed/features.parquet` and `models/v1/` are untouched and
  re-checksummed.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from haze import config  # noqa: E402
from haze.features import regime  # noqa: E402
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

# The published baseline this phase is measured against, from
# diagnostics/metrics_report.json (validation model, both events withheld).
BASELINE_2023 = {"hit_rate": 0.7632, "episode_detection_rate": 0.9394}
BASELINE_2024 = {"hit_rate": 0.5385, "episode_detection_rate": 0.8095}

# The stop condition, set at the checkpoint: an improvement in 2024 episode
# detection counts as signal only if it clears the baseline Wilson upper bound.
STOP_CONDITION_UPPER = 0.923

ARMS = {
    "control": (lambda df: df, []),
    "dryness": (regime.add_dryness, ["consecutive_dry_days"]),
    "enso": (regime.add_enso, ["enso_regime"]),
    # 2E: the same index measured where the fuel is rather than where the people
    # are, repairing the flaw 2D.1's null exposed.
    "upwind_dryness": (regime.add_upwind_dryness, ["upwind_dry_days"]),
}


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant pair counts.

    b = episodes the control caught and the ablation missed, c = the reverse.
    Concordant pairs carry no information about a difference and drop out, which
    is exactly why the paired test sees what an unpaired one cannot.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def score(models, features, frame, receptors) -> tuple[dict, list]:
    bands: dict[int, np.ndarray] = {}
    means: dict[int, np.ndarray] = {}
    for lead, model in sorted(models.items()):
        mean, quantiles = rf.predict_quantiles(
            model, frame, features, log=rf.LOG_FORECAST,
            percentiles=(config.ALERT_TRIGGER_PERCENTILE,),
        )
        means[lead] = mean
        bands[lead] = quantiles[config.ALERT_TRIGGER_PERCENTILE]
    metrics = evaluate.alert_metrics(frame, means, trigger=bands, receptors=receptors)
    flags = evaluate.episode_detection_flags(frame, bands, receptors)
    return metrics, flags


def run_arm(name: str, df: pd.DataFrame, base_features: list[str]) -> dict:
    transform, extra = ARMS[name]
    frame = transform(df)
    features = base_features + extra

    train, _, test_2023 = evaluate.split(
        frame, extra_holdouts=[SECOND_EVENT], embargo_hours=EMBARGO_HOURS
    )
    start, end = SECOND_EVENT
    test_2024 = frame[
        (frame["time"] >= start) & (frame["time"] <= end + " 23:59:59")
    ].copy()
    receptors = evaluate.distinct_receptors(frame)

    label = "baseline" if not extra else f"baseline + {', '.join(extra)}"
    print(f"\n=== {name} ({label}; {len(features)} features) ===")
    print(f"  training {len(ALL_HORIZONS)} forests on {len(train):,} rows...")
    models = rf.train_forecast(train, features, ALL_HORIZONS)

    out: dict = {"label": label, "n_features": len(features), "added": extra, "windows": {}}
    for window_label, window in (("2023", test_2023), ("2024", test_2024)):
        metrics, flags = score(models, features, window, receptors)
        ci = metrics["episode_detection_ci95"]
        out["windows"][window_label] = {
            "metrics": metrics,
            "episode_flags": [
                {"institution_id": i, "onset": str(o), "warned": w} for i, o, w in flags
            ],
        }
        print(
            f"  {window_label}: hit {metrics['hit_rate']:.1%}  "
            f"FAR {metrics['false_alarm_rate']:.1%}  "
            f"spec {metrics['specificity']:.1%}  "
            f"episode {metrics['episode_detection_rate']:.1%} of "
            f"{metrics['distinct_episodes']} [{ci[0]:.1%}, {ci[1]:.1%}]"
        )

    # What the forest actually leaned on, for the added feature.
    if extra:
        importances = dict(
            zip(features, models[24].feature_importances_)
        )
        out["added_feature_importance_at_24h"] = {
            f: round(float(importances[f]), 5) for f in extra
        }
        ranked = sorted(importances.items(), key=lambda kv: -kv[1])
        out["added_feature_rank_at_24h"] = {
            f: 1 + [n for n, _ in ranked].index(f) for f in extra
        }
        for f in extra:
            print(
                f"  {f}: importance {importances[f]:.5f} at +24h, "
                f"rank {out['added_feature_rank_at_24h'][f]} of {len(features)}"
            )
    return out


def pair_against_control(control: dict, arm: dict, window: str) -> dict:
    """Discordant pairs on the same episodes, plus an exact McNemar p-value."""
    key = lambda r: (r["institution_id"], r["onset"])  # noqa: E731
    base = {key(r): r["warned"] for r in control["windows"][window]["episode_flags"]}
    test = {key(r): r["warned"] for r in arm["windows"][window]["episode_flags"]}
    shared = sorted(set(base) & set(test))
    b = sum(1 for k in shared if base[k] == 1 and test[k] == 0)
    c = sum(1 for k in shared if base[k] == 0 and test[k] == 1)
    return {
        "episodes_compared": len(shared),
        "control_caught_ablation_missed": b,
        "ablation_caught_control_missed": c,
        "net_episodes_gained": c - b,
        "mcnemar_exact_p": round(mcnemar_exact(b, c), 4),
    }


def main() -> int:
    before = _checksums(SERVED_ARTIFACTS)
    features_hash = _checksums([config.FEATURES_PARQUET])

    # `--arms a,b` runs a subset. Control is always included: it is the paired
    # baseline every McNemar comparison is taken against, and it is re-run rather
    # than read back from a previous ablations.json, which records per-window
    # metrics but not the per-episode outcomes the pairing needs.
    selected = ["control"]
    for arg in sys.argv[1:]:
        if arg.startswith("--arms="):
            selected += [a for a in arg.split("=", 1)[1].split(",") if a != "control"]
    if len(selected) == 1:
        selected = list(ARMS)
    unknown = [a for a in selected if a not in ARMS]
    if unknown:
        print(f"Unknown arm(s): {unknown}. Available: {list(ARMS)}")
        return 1

    df = pd.read_parquet(config.FEATURES_PARQUET)
    with config.FEATURE_SPEC.open() as fh:
        base_features = json.load(fh)["features"]

    results = {name: run_arm(name, df, base_features) for name in selected}

    # -- control must reproduce the published baseline ---------------------
    ctrl_2023 = results["control"]["windows"]["2023"]["metrics"]
    ctrl_2024 = results["control"]["windows"]["2024"]["metrics"]
    drift = max(
        abs(ctrl_2023["hit_rate"] - BASELINE_2023["hit_rate"]),
        abs(ctrl_2023["episode_detection_rate"] - BASELINE_2023["episode_detection_rate"]),
        abs(ctrl_2024["hit_rate"] - BASELINE_2024["hit_rate"]),
        abs(ctrl_2024["episode_detection_rate"] - BASELINE_2024["episode_detection_rate"]),
    )
    control_ok = drift < 1e-4
    print(
        f"\nControl reproduces the published baseline: {control_ok} "
        f"(max drift {drift:.5f})"
    )
    if not control_ok:
        print(
            "  ABORT: the harness does not reproduce the published figures, so no "
            "ablation delta below can be trusted. Reporting this instead of results."
        )

    # -- paired comparisons ------------------------------------------------
    arms_tested = [n for n in selected if n != "control"]
    comparisons: dict[str, dict] = {}
    for name in arms_tested:
        comparisons[name] = {
            w: pair_against_control(results["control"], results[name], w)
            for w in ("2023", "2024")
        }
        d = comparisons[name]["2024"]
        det = results[name]["windows"]["2024"]["metrics"]["episode_detection_rate"]
        print(
            f"\n{name} vs control on 2024: episode detection "
            f"{ctrl_2024['episode_detection_rate']:.1%} -> {det:.1%}; "
            f"net episodes {d['net_episodes_gained']:+d} "
            f"(+{d['ablation_caught_control_missed']}/-{d['control_caught_ablation_missed']}), "
            f"exact McNemar p = {d['mcnemar_exact_p']:.3f}"
        )

    passed = {
        name: bool(
            results[name]["windows"]["2024"]["metrics"]["episode_detection_rate"]
            > STOP_CONDITION_UPPER
        )
        for name in arms_tested
    }
    verdict = {
        "stop_condition": (
            "2024 episode detection must exceed the baseline Wilson upper bound of "
            f"{STOP_CONDITION_UPPER:.1%} to count as signal."
        ),
        "passed": passed,
        "any_passed": any(passed.values()),
        "power_note": (
            "With 21 distinct episodes the only outcomes above 92.3% are 20/21 "
            "(95.2%) and 21/21 (100%); 19/21 is 90.5% and fails. The criterion "
            "therefore admits exactly two passing results and cannot detect a real "
            "but modest improvement. The paired McNemar figures are reported "
            "alongside because they retain the pairing and have more power, but "
            "the stated criterion is what decides the stop."
        ),
    }
    print(
        f"\nStop condition ({STOP_CONDITION_UPPER:.1%} on 2024 episode detection): "
        f"{'PASSED by ' + ', '.join(k for k, v in passed.items() if v) if any(passed.values()) else 'NOT met by either arm'}"
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "purpose": "Phase 2D isolated ablations: dryness and ENSO regime, never stacked.",
        "protocol": {
            "split": "validation model - both fire seasons withheld",
            "embargo_hours": EMBARGO_HOURS,
            "hyperparameters": {k: v for k, v in rf.RF_PARAMS.items() if k != "n_jobs"},
            "trigger": f"p{config.ALERT_TRIGGER_PERCENTILE} band at 35.5 ug/m3",
        },
        "control_reproduces_published_baseline": control_ok,
        "control_max_drift": round(drift, 6),
        "arms": {
            name: {
                k: v for k, v in arm.items() if k != "windows"
            } | {
                # Per-episode outcomes are kept, not just the rates. Without them
                # a later run cannot pair against this one, and cannot ask which
                # episodes were missed - a question 2E wanted and could not answer
                # from the 2D artifact.
                "windows": {
                    w: data["metrics"] | {"episode_flags": data["episode_flags"]}
                    for w, data in arm["windows"].items()
                }
            }
            for name, arm in results.items()
        },
        "paired_vs_control": comparisons,
        "verdict": verdict,
        "caveats": [
            "ENSO: across the whole archive there is one fire season per regime "
            "(2022 La Nina, 2023 El Nino, 2024 neutral). The validation protocol "
            "withholds 2023 and 2024, so training contains exactly ONE labelled "
            "fire season. The 2024 window it must predict is a regime x season "
            "combination never seen in training. Read any effect as an upper bound "
            "on harm, not as evidence about the feature.",
            "ENSO: ONI values are recalled, not fetched - see the provenance "
            "warning in src/haze/features/regime.py. The categorical encoding is "
            "robust to decimal error; the phase assignment per fire season is not "
            "in doubt.",
            "Dryness: precipitation is measured at the receptor, but the fires "
            "driving these episodes are 150-400 km upwind. BMKG applies HTH over "
            "the fire region. A receptor-level dry-day count may therefore be "
            "measuring the wrong place; gridded precipitation over the fire domain "
            "is already cached and is the obvious follow-up.",
            "Dryness has limited dynamic range here: the archive maximum is 12 "
            "consecutive dry days and the 90th percentile is 1.",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    # A subset run writes its own file rather than overwriting the full 2D table.
    out_name = (
        "ablations.json"
        if len(selected) == len(ARMS)
        else "ablations_" + "_".join(arms_tested) + ".json"
    )
    (OUT / out_name).write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nWrote {OUT / out_name}")

    after = _checksums(SERVED_ARTIFACTS)
    moved = [p for p in before if before[p] != after.get(p)]
    if _checksums([config.FEATURES_PARQUET]) != features_hash:
        moved.append(str(config.FEATURES_PARQUET))
    if moved:
        print("\nFAILED: this script modified protected artifacts:")
        for path in moved:
            print(f"  - {path}")
        return 1
    print(f"Protected artifacts unchanged ({len(before) + 1} checked).")
    return 0 if control_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""2D.0 - is fire-feature saturation actually present in the 2023 underpredictions?

2C.2 established that the tree-ensemble ceiling is not the active constraint: on
the 6,192 forecast pairs whose observation exceeds the 112.9 ug/m3 training max,
the model's highest point forecast is 67.8, well below its ~97 structural
capability. Something else is stopping it, and one candidate is that the fire
features themselves are pinned at the top of their trained range during those
hours, leaving the forest with no way to distinguish "very bad" from
"catastrophic".

This tests that candidate before any retrain is spent on it. A feature counts as
*pinned* at >= 85% of its training maximum, reusing
`config.EXTRAPOLATION_SATURATION_FRACTION` rather than inventing a threshold -
the same fraction the served API already uses to tell a user their forecast has
left the trained range.

Read-only. Touches no model and no cached artifact.

    python scripts/12_saturation_diagnostic.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from haze import config  # noqa: E402
from haze.alerts import thresholds  # noqa: E402
from haze.models import evaluate  # noqa: E402

OUT = config.ROOT / "diagnostics"
ALERT_PM25 = thresholds.alert_threshold("school").pm25

FIRE_FEATURES = (
    "ufei_24h",
    "ufei_48h",
    "ufei_72h",
    "ufei_from_ID",
    "hotspots_0_50km",
    "hotspots_50_150km",
    "hotspots_150_400km",
    "frp_0_50km",
    "frp_50_150km",
    "frp_150_400km",
)


def phi(a: np.ndarray, b: np.ndarray) -> float:
    """Correlation between two binary vectors (point-biserial = Pearson here)."""
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a.astype(float), b.astype(float))[0, 1])


def main() -> int:
    df = pd.read_parquet(config.FEATURES_PARQUET)
    ranges = json.loads((config.MODELS / "training_ranges.json").read_text())
    frac = float(ranges.get("saturation_fraction", config.EXTRAPOLATION_SATURATION_FRACTION))
    train_max = float(ranges["target_max_pm25"])
    leads = list(range(1, config.FORECAST_HORIZON_HOURS + 1))

    report: dict = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "question": (
            "Are fire features pinned near their trained maximum during the hours "
            "whose observations exceed the training range?"
        ),
        "pinned_definition": f"feature >= {frac:.0%} of its training maximum",
        "training_target_max_pm25": train_max,
        "windows": {},
    }

    for label, (start, end) in [
        ("2023", (config.TEST_START, config.TEST_END)),
        ("2024", ("2024-08-16", "2024-10-15")),
    ]:
        t = df["time"]
        frame = df[(t >= start) & (t <= end + " 23:59:59")].copy()
        obs = np.column_stack(
            [frame[f"target_{lead}h"].to_numpy(dtype=float) for lead in leads]
        )
        valid = ~np.isnan(obs)
        beyond = valid & (obs > train_max)
        alertable = valid & (obs >= ALERT_PM25)

        window: dict = {
            "window": f"{start}..{end}",
            "pairs_total": int(valid.sum()),
            "pairs_alertable": int(alertable.sum()),
            "pairs_beyond_range": int(beyond.sum()),
            "features": {},
        }

        if not beyond.any():
            window["note"] = (
                f"No pair in this window observes above the {train_max} ug/m3 "
                f"training max (window maximum {np.nanmax(obs):.1f}). There is no "
                "beyond-range set to diagnose here; saturation cannot be assessed "
                "and this window is not evidence either way."
            )
            report["windows"][label] = window
            print(f"\n{label}: {window['note']}")
            continue

        print(f"\n{label}: pinned rate by stratum (pinned = >= {frac:.0%} of training max)")
        print(f"  {'feature':22s} {'beyond':>9} {'alertable':>10} {'all':>9} {'lift':>7} {'phi':>7}")

        for feat in FIRE_FEATURES:
            hi = ranges["features"].get(feat, {}).get("hi")
            if hi is None or hi <= 0:
                continue
            # Feature values belong to the issuance hour, and already summarise the
            # trailing window (UFEI over 24/48/72h, rings over 24h). Broadcast the
            # hour's value across that hour's 24 forecast pairs.
            pinned_hour = frame[feat].to_numpy(dtype=float) >= frac * float(hi)
            pinned = np.repeat(pinned_hour[:, None], len(leads), axis=1)

            r_beyond = float(pinned[beyond].mean())
            r_alert = float(pinned[alertable].mean())
            r_all = float(pinned[valid].mean())
            lift = (r_beyond / r_all) if r_all > 0 else float("nan")
            corr = phi(pinned[valid], beyond[valid])

            window["features"][feat] = {
                "training_max": float(hi),
                "pinned_rate_beyond_range": round(r_beyond, 4),
                "pinned_rate_alertable": round(r_alert, 4),
                "pinned_rate_all": round(r_all, 4),
                "lift_vs_all": None if np.isnan(lift) else round(lift, 2),
                "phi_with_beyond_range": None if np.isnan(corr) else round(corr, 4),
            }
            print(
                f"  {feat:22s} {r_beyond:>8.1%} {r_alert:>10.1%} {r_all:>9.1%} "
                f"{lift:>7.2f} {corr:>7.3f}"
            )

        report["windows"][label] = window

    # -- verdict ----------------------------------------------------------
    feats = report["windows"]["2023"]["features"]
    any_pinned = max((f["pinned_rate_beyond_range"] for f in feats.values()), default=0.0)
    max_phi = max(
        (abs(f["phi_with_beyond_range"] or 0.0) for f in feats.values()), default=0.0
    )
    saturated = any_pinned >= 0.20 and max_phi >= 0.20
    report["verdict"] = {
        "saturation_present": bool(saturated),
        "max_pinned_rate_on_beyond_range_pairs": round(any_pinned, 4),
        "max_abs_phi": round(max_phi, 4),
        "statement": (
            "Fire features are pinned near their trained maximum during the "
            "beyond-range hours; a saturation-motivated remedy is justified."
            if saturated
            else "Fire features are NOT pinned near their trained maximum during the "
            "beyond-range hours. Saturation is not the mechanism behind the "
            "underprediction, and no saturation-motivated remedy should be "
            "proposed on this evidence. The missing-signal hypothesis (2D.1, "
            "2D.2) is unaffected - it does not depend on saturation."
        ),
    }
    print(f"\nVerdict: {report['verdict']['statement']}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "saturation_diagnostic.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nWrote {OUT / 'saturation_diagnostic.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

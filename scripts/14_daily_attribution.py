#!/usr/bin/env python3
"""Where the fire-to-haze signal actually lives: hourly or daily.

The README has long carried two numbers side by side - attribution R2 = 0.03 on
held-out hourly data, and r = +0.52 between West Kalimantan hotspot counts and
Kuching PM2.5 at a one-day lag - and invited the reader to conclude that the
relationship is real but lives at daily resolution.

That juxtaposition was never a tested claim. Worse, **the +0.52 was not computed
anywhere in this repository**: it existed only as prose. A published number with
no code behind it is exactly what the rest of this project refuses to ship, so
this script computes it, publishes the whole lag profile rather than its peak,
and fits the attribution model at daily resolution to see whether the signal
really is stronger there.

    python scripts/14_daily_attribution.py        (make attribution)

Two claims are under test, and either can come back null:

1. **The lag profile.** "Kuching's correlation peaks at 1 day, Pontianak's at 3,
   consistent with transport distance." That is a claim about the *shape* of the
   profile, so the whole profile is published and the peak is read off it rather
   than asserted.
2. **The resolution claim.** Daily attribution should beat hourly attribution
   after both are measured against their own baselines. An R2 that rises simply
   because averaging removed variance is not evidence of anything - daily
   persistence and daily climatology rise too. Only the margin over those
   baselines is meaningful, so that is what decides it.

Nothing on disk changes except `diagnostics/daily_attribution.json`. The served
artifacts and the feature matrix are re-checksummed before exit.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import RandomForestRegressor  # noqa: E402

from haze import config  # noqa: E402
from haze.features import build  # noqa: E402
from haze.models import baselines, evaluate, rf  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_validate_events", Path(__file__).resolve().parent / "06_validate_events.py"
)
_validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_validate)

SECOND_EVENT = _validate.SECOND_EVENT
EMBARGO_HOURS = _validate.EMBARGO_HOURS
SERVED_ARTIFACTS = _validate.SERVED_ARTIFACTS
_checksums = _validate._checksums

OUT = config.ROOT / "diagnostics"

# Lags in days. Stops at 5 because transport from Kalimantan to Sarawak is a
# matter of a day or three; a profile that had to run to a fortnight to find a
# peak would be describing a season, not a plume.
MAX_LAG_DAYS = 5

# The two cities the README names, mapped to the distinct receptors that carry
# their PM2.5 series. Not all six institutions: the trios share a CAMS cell.
CITIES = {"kuching": "my-kch-greenroad", "pontianak": "id-ptk-bpbd"}


# --------------------------------------------------------------------------
# Daily aggregation
# --------------------------------------------------------------------------
def west_kalimantan_daily_hotspots() -> pd.DataFrame:
    """Detections per UTC day inside the source region the system attributes to.

    Counted from the FIRMS archive over `config.WEST_KALIMANTAN_BBOX`, not from
    the per-receptor ring columns in the feature matrix. The README's claim is
    about *West Kalimantan* hotspot counts - a property of the source region,
    identical for both receptors - while `hotspots_150_400km` is a property of
    one receptor's geometry. Using the ring counts would answer a different
    question and would give Kuching and Pontianak different predictors.
    """
    hotspots = build.load_hotspots()
    lon_min, lat_min, lon_max, lat_max = config.WEST_KALIMANTAN_BBOX
    inside = hotspots[
        hotspots["longitude"].between(lon_min, lon_max)
        & hotspots["latitude"].between(lat_min, lat_max)
    ]
    daily = (
        inside.assign(date=inside["acq_time_utc"].dt.floor("D"))
        .groupby("date")
        .agg(wk_hotspots=("frp", "size"), wk_frp=("frp", "sum"))
        .reset_index()
    )
    return daily


def daily_frame(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """One row per receptor-day: mean PM2.5 and mean of every daily predictor."""
    sub = df[df["institution_id"].isin(CITIES.values())].copy()
    sub["date"] = sub["time"].dt.floor("D")
    agg = {c: "mean" for c in feature_cols}
    agg["pm25"] = "mean"
    daily = sub.groupby(["institution_id", "date"], as_index=False).agg(agg)
    return daily.sort_values(["institution_id", "date"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# Claim 1 - the lag profile
# --------------------------------------------------------------------------
def lag_profile(daily: pd.DataFrame, hotspots: pd.DataFrame, window: tuple | None) -> dict:
    """Pearson r at every lag 0..MAX_LAG_DAYS, per city.

    The whole profile is returned, not the maximum. A peak reported on its own
    cannot be distinguished from the largest of six noisy numbers, and the claim
    being tested is about the shape: nearer receptor peaks sooner.
    """
    out: dict = {}
    for city, inst_id in CITIES.items():
        site = daily[daily["institution_id"] == inst_id].merge(
            hotspots, on="date", how="left"
        )
        site["wk_hotspots"] = site["wk_hotspots"].fillna(0.0)
        if window is not None:
            start, end = window
            site = site[(site["date"] >= start) & (site["date"] <= end + " 23:59:59")]

        by_lag = {}
        for lag in range(MAX_LAG_DAYS + 1):
            fires = site["wk_hotspots"].shift(lag)
            pair = pd.DataFrame({"f": fires, "p": site["pm25"]}).dropna()
            by_lag[lag] = (
                round(float(pair["f"].corr(pair["p"])), 4) if len(pair) > 2 else None
            )

        scored = {k: v for k, v in by_lag.items() if v is not None}
        peak = max(scored, key=lambda k: scored[k]) if scored else None
        out[city] = {
            "institution_id": inst_id,
            "n_days": int(len(site)),
            "r_by_lag_days": by_lag,
            "peak_lag_days": peak,
            "peak_r": by_lag.get(peak),
        }
    return out


# --------------------------------------------------------------------------
# Claim 2 - does attribution do better at daily resolution
# --------------------------------------------------------------------------
def daily_climatology(train: pd.DataFrame, target: pd.DataFrame) -> np.ndarray:
    """Day-of-year mean per receptor, learned on the training split only."""
    tr = train.copy()
    tr["_doy"] = tr["date"].dt.dayofyear
    lookup = tr.groupby(["institution_id", "_doy"])["pm25"].mean()
    site_mean = tr.groupby("institution_id")["pm25"].mean()
    global_mean = float(tr["pm25"].mean())

    tg = target.copy()
    tg["_doy"] = tg["date"].dt.dayofyear
    idx = pd.MultiIndex.from_frame(tg[["institution_id", "_doy"]])
    values = lookup.reindex(idx).to_numpy(dtype=float)
    fallback = tg["institution_id"].map(site_mean).to_numpy(dtype=float)
    values = np.where(np.isnan(values), fallback, values)
    return np.where(np.isnan(values), global_mean, values)


# Daily aggregation collapses ~127k hourly rows to ~1.8k receptor-days. The
# served RF_PARAMS were chosen for the former, and `min_samples_leaf=20` on a
# training set 72x smaller smooths away most of what is left. A null measured at
# that setting alone would confound "daily resolution is worse" with "daily has
# far less data", so every fit is repeated at a leaf size appropriate to the
# smaller sample and both are published.
LEAF_SIZES = (20, 5)


def fit_daily_attribution(daily: pd.DataFrame, attr_cols: list[str], leaf: int) -> dict:
    """Fire and weather only, at daily resolution, on the same held-out split.

    Deliberately the same restriction the hourly attribution model uses: no
    PM2.5 lags, no day-of-year. With lags in it the model would lean on
    persistence, and with seasonality it would learn "September is smoky" -
    climatology dressed as attribution.
    """
    # Days with no PM2.5 at all are dropped up front, and persistence is taken
    # within each receptor, so "yesterday" never steps across a site boundary.
    daily = (
        daily.dropna(subset=["pm25"])
        .sort_values(["institution_id", "date"])
        .reset_index(drop=True)
    )
    daily["pm25_prev"] = daily.groupby("institution_id")["pm25"].shift(1)

    t = daily["date"]
    test_mask = evaluate.window_mask(t, config.TEST_START, config.TEST_END)
    second_mask = evaluate.window_mask(t, *SECOND_EVENT)
    val_mask = evaluate.window_mask(t, config.VAL_START, config.VAL_END)
    train = daily[~(test_mask | second_mask | val_mask)].copy()

    def matrix(frame: pd.DataFrame) -> np.ndarray:
        return (
            frame[attr_cols]
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
            .to_numpy(dtype=float)
        )

    params = {**rf.RF_PARAMS, "min_samples_leaf": leaf}
    model = RandomForestRegressor(**params)
    model.fit(matrix(train), np.log1p(np.clip(train["pm25"].to_numpy(float), 0, None)))

    def log(v: np.ndarray) -> np.ndarray:
        return np.log1p(np.clip(v, 0, None))

    results = {}
    for label, mask in (("2023", test_mask), ("2024", second_mask)):
        test = daily[mask]
        truth = test["pm25"].to_numpy(dtype=float)
        pred = np.expm1(model.predict(matrix(test)))
        pers = test["pm25_prev"].to_numpy(dtype=float)
        clim = daily_climatology(train, test)

        results[label] = {
            "n_days": int(len(test)),
            "model_r2_log": round(baselines.r2(log(truth), log(pred)), 4),
            "model_r2_raw": round(baselines.r2(truth, pred), 4),
            "persistence_r2_log": round(baselines.r2(log(truth), log(pers)), 4),
            "climatology_r2_log": round(baselines.r2(log(truth), log(clim)), 4),
            "model_mae": round(baselines.mae(truth, pred), 2),
            "persistence_mae": round(baselines.mae(truth, pers), 2),
            "climatology_mae": round(baselines.mae(truth, clim), 2),
        }
    return {
        "min_samples_leaf": leaf,
        "n_train_days": int(len(train)),
        "windows": results,
    }


# --------------------------------------------------------------------------
def main() -> int:
    if not config.FEATURES_PARQUET.exists():
        print("No features found. Run scripts/02_build_features.py first.")
        return 1

    before = _checksums([*SERVED_ARTIFACTS, config.FEATURES_PARQUET])
    OUT.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(config.FEATURES_PARQUET)
    with config.FEATURE_SPEC.open() as fh:
        features = json.load(fh)["features"]
    attr_cols = rf.attribution_features(features)

    print("Counting West Kalimantan detections per day...")
    hotspots = west_kalimantan_daily_hotspots()
    print(f"  {len(hotspots):,} days, {int(hotspots['wk_hotspots'].sum()):,} detections")

    daily = daily_frame(df, features)
    print(f"  {len(daily):,} receptor-days over {daily['date'].nunique():,} days")

    # -- claim 1 ----------------------------------------------------------
    print(f"\nLag profile (r, West Kalimantan detections vs daily PM2.5):")
    profiles = {
        "full_archive": lag_profile(daily, hotspots, None),
        "held_out_2023": lag_profile(daily, hotspots, (config.TEST_START, config.TEST_END)),
        "held_out_2024": lag_profile(daily, hotspots, SECOND_EVENT),
    }
    for scope, cities in profiles.items():
        print(f"  {scope}")
        for city, row in cities.items():
            cells = "  ".join(
                f"{lag}d {r:+.2f}" if r is not None else f"{lag}d   --"
                for lag, r in row["r_by_lag_days"].items()
            )
            print(f"    {city:10s} {cells}   peak {row['peak_lag_days']}d")

    # -- claim 2 ----------------------------------------------------------
    print("\nFitting attribution at daily resolution (fire + weather only)...")
    fits = {}
    for leaf in LEAF_SIZES:
        fit = fit_daily_attribution(daily, attr_cols, leaf)
        fits[f"min_samples_leaf_{leaf}"] = fit
        print(f"  min_samples_leaf={leaf} ({fit['n_train_days']:,} training days)")
        for label, row in fit["windows"].items():
            print(
                f"    {label}: daily R2(log) {row['model_r2_log']:+.4f}   "
                f"persistence {row['persistence_r2_log']:+.4f}   "
                f"climatology {row['climatology_r2_log']:+.4f}"
            )

    hourly_r2_log = None
    if config.METRICS_JSON.exists():
        with config.METRICS_JSON.open() as fh:
            hourly_r2_log = json.load(fh).get("r2_attribution")
    print(f"  hourly R2(log), held-out 2023, for comparison: {hourly_r2_log:+.4f}")

    # The claim gets its best shot: the most favourable leaf size counts. If it
    # still loses, the null is not an artifact of a hyperparameter.
    best_key = max(fits, key=lambda k: fits[k]["windows"]["2023"]["model_r2_log"])
    fit = fits[best_key]
    d23 = fit["windows"]["2023"]
    beats_baselines = (
        d23["model_r2_log"] > d23["persistence_r2_log"]
        and d23["model_r2_log"] > d23["climatology_r2_log"]
    )
    beats_hourly = (
        hourly_r2_log is not None and d23["model_r2_log"] > hourly_r2_log
    )
    print(
        f"\n  best of {len(fits)} leaf settings on 2023: {best_key} "
        f"(R2 {d23['model_r2_log']:+.4f}); beats its baselines: {beats_baselines}; "
        f"beats hourly: {beats_hourly}"
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "purpose": (
            "Put a computation behind the r = +0.52 daily correlation the README "
            "quotes, and test whether attribution really is stronger at daily "
            "resolution than hourly."
        ),
        "protocol": {
            "source_region": "config.WEST_KALIMANTAN_BBOX",
            "hotspot_counting": (
                "FIRMS detections inside the source bbox per UTC day, deduplicated "
                "across sensors by features.build.load_hotspots."
            ),
            "receptors": CITIES,
            "max_lag_days": MAX_LAG_DAYS,
            "attribution_features": (
                "fire and weather only - no PM2.5 lags, no day-of-year, matching "
                "haze.models.rf.attribution_features"
            ),
            "holdouts": [
                f"{config.TEST_START}..{config.TEST_END}",
                f"{SECOND_EVENT[0]}..{SECOND_EVENT[1]}",
            ],
            "hyperparameters": {k: v for k, v in rf.RF_PARAMS.items() if k != "n_jobs"},
        },
        "correlation_profile": profiles,
        "daily_attribution": fits,
        "daily_attribution_best_on_2023": best_key,
        "hourly_attribution_r2_log": hourly_r2_log,
        "daily_vs_hourly": {
            "leaf_setting_used": best_key,
            "daily_r2_log_2023": d23["model_r2_log"],
            "daily_persistence_r2_log_2023": d23["persistence_r2_log"],
            "hourly_r2_log_2023": hourly_r2_log,
            "daily_beats_its_own_baselines": bool(beats_baselines),
            "daily_beats_hourly_r2": bool(beats_hourly),
            "signal_lives_at_daily_resolution": bool(beats_baselines and beats_hourly),
        },
        "caveats": [
            "Daily aggregation leaves ~1.8k receptor-days against ~127k hourly "
            "rows, so a daily model is fighting a 72x smaller training set as well "
            "as a different resolution. Both leaf settings are reported and the "
            "more favourable one decides the verdict, so the result is not an "
            "artifact of hyperparameters tuned for the hourly problem.",
            "An R2 that rises with aggregation is not by itself evidence: averaging "
            "removes variance, and daily persistence and climatology rise too. Only "
            "the margin over those baselines supports the claim, which is why both "
            "are reported beside the model.",
            "Correlation over the full archive mixes fire seasons with the wet "
            "season, when neither series moves. The per-window profiles are "
            "reported alongside so the figure is not read as a single constant.",
            "The lag profile is a correlation, not a transport model. It cannot "
            "separate transport time from the fact that fires and haze are both "
            "driven by the same dry spell.",
            "PM2.5 is ECMWF CAMS reanalysis, not ground-station measurement, at "
            "daily resolution exactly as it is hourly.",
            "Two receptors is a small sample for a claim about how peak lag varies "
            "with distance. The profile is published so the reader can see how "
            "thin the evidence for that ordering is.",
        ],
    }

    (OUT / "daily_attribution.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nWrote {OUT / 'daily_attribution.json'}")

    after = _checksums([*SERVED_ARTIFACTS, config.FEATURES_PARQUET])
    moved = [p for p in before if before[p] != after.get(p)]
    if moved:
        print("\nFAILED: this script modified protected artifacts:")
        for path in moved:
            print(f"  - {path}")
        return 1
    print(f"Protected artifacts unchanged ({len(before)} checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

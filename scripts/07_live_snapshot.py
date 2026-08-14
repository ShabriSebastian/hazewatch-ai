"""Run the served model against LIVE conditions and write one snapshot.

This is a proof of capability, not a service. It is deliberately a standalone
script rather than a mode inside the API:

  * Nothing under `src/haze/api/` imports it, so the served path stays offline
    by construction and `make offline` keeps passing with sockets blocked.
  * It reads the *served* forest and the *served* training ranges. It trains
    nothing, writes no model artifact, and never touches the replay scenario.
  * It can be deleted the morning of a demo without affecting anything.

    python scripts/07_live_snapshot.py
    python scripts/07_live_snapshot.py --lag-hours 6 --window 48h

What it does NOT do: validate the model on live data. Nothing here can, because
the hours being forecast have not happened yet. The honest claim is "the served
model, given live inputs, produced this" - never "the model was accurate today".
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haze import config  # noqa: E402
from haze.alerts import rules, thresholds  # noqa: E402
from haze.features import build as feature_build  # noqa: E402
from haze.ingest import firms_nrt  # noqa: E402
from haze.institutions import INSTITUTIONS  # noqa: E402
from haze.models import extrapolation, rf  # noqa: E402
from haze.pipeline import precompute  # noqa: E402

# Enough history to warm up the longest trailing window the features need:
# ufei_72h plus pm25_roll_24h. Seven days is the FIRMS NRT file length anyway.
WARMUP_DAYS = 7


def _iso(ts) -> str:
    return pd.Timestamp(ts).tz_localize(None).strftime("%Y-%m-%dT%H:%M:%SZ")


def force_ipv4() -> None:
    """Resolve only A records for the rest of this process.

    All three upstreams - FIRMS, and both Open-Meteo endpoints - publish AAAA
    records, but GitHub Actions runners have no working IPv6 egress. Python's
    `urlopen` tries the AAAA first and gets `[Errno 101] Network is unreachable`,
    once per host, each waiting out the full connect timeout. The first CI run
    failed exactly this way after burning six minutes on three timeouts.

    Filtering `getaddrinfo` to IPv4 is a property of the network environment,
    not of the ingest logic, so it is patched here in the script rather than in
    `src/haze/` where it would affect the library for every caller.
    """
    original = socket.getaddrinfo

    def ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return original(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = ipv4_only  # type: ignore[assignment]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--lag-hours", type=int, default=12,
        help="Issue the forecast this many hours behind now. The trailing hours "
             "of any NRT file are only partly populated - a satellite has to fly "
             "over before a fire can be detected - so issuing at `now` "
             "understates recent fire exposure and biases the forecast LOW, "
             "which is the dangerous direction. Default 12.",
    )
    ap.add_argument("--window", default="7d", choices=("24h", "48h", "7d"))
    ap.add_argument("--out", default=None, help="Output JSON path.")
    ap.add_argument(
        "--allow-ipv6", action="store_true",
        help="Do not force IPv4 resolution. Off by default because GitHub "
             "Actions runners have no working IPv6 egress and every upstream "
             "publishes AAAA records, which makes urlopen wait out a connect "
             "timeout per host before failing.",
    )
    ap.add_argument(
        "--allow-cached", action="store_true",
        help="Reuse any cached Open-Meteo response for this date window instead "
             "of refetching. Faster for development, but the cache key is only "
             "date-granular, so a second run the same day would serve hours-old "
             "weather while still being labelled live. Off by default.",
    )
    args = ap.parse_args()

    if not args.allow_ipv6:
        force_ipv4()

    bundle_path = config.MODELS / "rf_forecast.joblib"
    if not bundle_path.exists():
        print(f"No served forest at {bundle_path} - run scripts/03_train.py first.")
        return 1

    ranges = extrapolation.load_training_ranges()
    if not ranges:
        print("No training_ranges.json - run scripts/03_train.py first.")
        return 1

    print("HazeWatch live snapshot")
    print("=" * 62)

    # -- 1. fire field ----------------------------------------------------
    print(f"\nFetching FIRMS NRT ({args.window})...")
    hotspots, fire_prov = firms_nrt.load_recent(args.window)
    print(
        f"  {fire_prov['rows_after_dedup']:,} detections in domain after dedup "
        f"(from {fire_prov['rows_before_dedup']:,} across sensors)"
    )
    for name, meta in fire_prov["sensors"].items():
        if meta["status"] == "ok":
            print(f"    {name:16} {meta['rows_in_domain']:>7,}  {meta['first_date']}..{meta['last_date']}")
        else:
            print(f"    {name:16} {'UNAVAILABLE':>7}")
    print(f"  latest detection: {fire_prov['latest_detection_utc']}")

    issued_at = firms_nrt.latest_complete_hour(hotspots, args.lag_hours)
    print(f"\n  issuing for {_iso(issued_at)}  (now - {args.lag_hours}h)")

    start = (issued_at - timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")
    end = (issued_at + timedelta(days=1)).strftime("%Y-%m-%d")

    # -- 2. weather + CAMS ------------------------------------------------
    print(f"\nFetching Open-Meteo {start}..{end} (this is the slow part)...")
    wind_grid, lats, lons, wind_times = feature_build.load_wind_grid(
        start, end, cached_only=False, refresh=not args.allow_cached
    )
    print(f"  wind grid {wind_grid.shape} over {len(wind_times)} hours")

    geometry = feature_build.HotspotGeometry(hotspots, lats, lons)

    bundle = joblib.load(bundle_path)
    models, model_features = bundle["models"], bundle["features"]
    log_space = bundle.get("log", False)
    lower_p = config.BAND_LOWER_PERCENTILE
    upper_p = config.ALERT_TRIGGER_PERCENTILE

    # -- 3. features + forecast per institution ---------------------------
    print("\nBuilding features and forecasting...")
    results = []
    for inst in INSTITUTIONS:
        series = feature_build.load_site_series(
            inst, start, end, cached_only=False, refresh=not args.allow_cached
        )
        site = feature_build.build_site(inst, geometry, wind_grid, wind_times, series)

        target = pd.Timestamp(issued_at).tz_localize(None)
        site["_t"] = pd.to_datetime(site["time"]).dt.tz_localize(None)
        row_at = site[site["_t"] <= target]
        if row_at.empty:
            print(f"  ! {inst.id}: no feature row at or before {_iso(issued_at)}")
            continue
        row = row_at.iloc[[-1]].copy()

        missing = [c for c in model_features if c not in row.columns]
        for c in missing:
            row[c] = 0.0  # site one-hots for the other five institutions
        nan_cols = [c for c in model_features if row[c].isna().any()]
        if nan_cols:
            print(f"  ! {inst.id}: NaN features {nan_cols[:5]} - skipping")
            continue

        preds: dict[int, float] = {}
        bands: dict[int, dict[int, float]] = {}
        for lead, model in sorted(models.items()):
            mean, q = rf.predict_quantiles(
                model, row, model_features, log=log_space,
                percentiles=(lower_p, 50, upper_p),
            )
            preds[lead] = float(mean[0])
            bands[lead] = {p: float(v[0]) for p, v in q.items()}

        novel = bool(extrapolation.out_of_range_features(row.iloc[0], ranges))
        oor = extrapolation.out_of_range_features(row.iloc[0], ranges)

        points = []
        for lead in sorted(models):
            upper = bands[lead][upper_p]
            saturation = extrapolation.saturation_threshold(ranges, lead)
            saturated = saturation is not None and upper >= saturation
            beyond, reason = extrapolation.combine(saturated, novel)
            points.append(
                precompute._point(
                    pd.Timestamp(issued_at) + pd.Timedelta(hours=lead),
                    lead, preds[lead],
                    lower=bands[lead][lower_p], upper=upper,
                    median=bands[lead][50],
                    beyond_training_range=beyond, extrapolation_reason=reason,
                )
            )

        observed = float(row.iloc[0]["pm25"])
        alert = rules.evaluate(inst, pd.Timestamp(issued_at).to_pydatetime(), points, None)
        peak = max(points, key=lambda p: p["pm25_upper"] or p["pm25"])

        results.append({
            "institution_id": inst.id,
            "institution_name": inst.name,
            "institution_type": inst.type,
            "country": inst.country,
            "city": inst.city,
            "observed_pm25": round(observed, 1),
            "observed_category": thresholds.categorise(observed),
            "forecast": points,
            "peak": peak,
            "alert": alert,
            "out_of_range_features": oor,
        })

        flagged = sum(p["beyond_training_range"] for p in points)
        state = "ALERT" if alert else "-"
        print(
            f"  {inst.id:18} now={observed:>6.1f}  peak_upper={peak['pm25_upper']:>6.1f}"
            f"  {state:<6} flagged {flagged:>2}/{len(points)}"
            + (f"  OOR:{','.join(oor)}" if oor else "")
        )

    if not results:
        print("\nNo institution produced a forecast. Refusing to write a snapshot.")
        return 1

    # -- 4. write ---------------------------------------------------------
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.out) if args.out else config.ROOT / "data" / "live" / f"snapshot_{stamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "data_source": "live_nrt",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "issued_at": _iso(issued_at),
        "issued_offset_hours": -args.lag_hours,
        "model_version": config.MODEL_VERSION,
        "alert_threshold_pm25": thresholds.alert_threshold("school").pm25,
        "alert_trigger_percentile": upper_p,
        "institutions": results,
        "provenance": {
            "hotspots": fire_prov,
            "weather": {
                "source": "Open-Meteo archive-api",
                "window": f"{start}..{end}",
                "refetched_now": not args.allow_cached,
                "caveat": (
                    "For recent days this endpoint returns forecast-model output, "
                    "not ERA5 reanalysis - verified byte-identical to "
                    "api.open-meteo.com/v1/forecast over 48 overlapping hours. The "
                    "model was trained on genuine ERA5, so live weather features "
                    "carry a provenance shift that did not exist in training."
                ),
            },
            "pm25": {
                "source": "Open-Meteo air-quality (CAMS)",
                "caveat": "CAMS reanalysis/forecast, not ground-station measurement.",
            },
            "limitations": [
                "Not a validation. The forecast hours have not happened yet; nothing "
                "here measures accuracy on live data.",
                f"The forest cannot emit above ~{ranges.get('model_ceiling', {}).get('by_lead', {}).get('1', {}).get('upper', 91)} ug/m3 "
                "regardless of conditions, so it will under-read a severe peak.",
                "Issued at now-%dh because the trailing hours of the NRT fire field "
                "are only partly populated." % args.lag_hours,
                "All institutions within one city share a CAMS grid cell, so their "
                "observed PM2.5 is identical by construction.",
            ],
        },
    }

    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {out_path}")

    alerting = [r for r in results if r["alert"]]
    total_flagged = sum(
        p["beyond_training_range"] for r in results for p in r["forecast"]
    )
    total_points = sum(len(r["forecast"]) for r in results)
    print(
        f"  {len(alerting)}/{len(results)} institutions alerting  |  "
        f"{total_flagged}/{total_points} forecast points beyond trained range"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

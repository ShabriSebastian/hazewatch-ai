"""NASA FIRMS near-real-time hotspot ingestion.

Sibling to `firms.py`, which reads the *country-year archive* files. Those are
published annually - `config.FIRMS_YEARS` stops at 2024 - so they can never
serve a forecast for today. This module reads the separate **active-fire NRT
product**, which is also keyless and is updated continuously:

    https://firms.modaps.eosdis.nasa.gov/data/active_fire/{sensor}/csv/{PREFIX}_SouthEast_Asia_{window}.csv

Latency is 1-3 hours after satellite overpass (NASA LANCE NRT). Ultra-real-time
(~60 s) exists but is US/Canada only, so 1-3 h is the floor for Indonesia.

**The trailing day is always partial.** Detections arrive as satellites pass, so
the most recent day in a file is truncated - measured 3,079 domain detections on
2026-08-10 against 693 on 08-13 for the same file. Feeding that to the UFEI
trailing windows makes recent fire exposure look smaller than it is, biasing a
forecast *downward* during an escalating event. `scripts/07_live_snapshot.py`
issues from `now - 12 h` for exactly this reason; see `latest_complete_hour()`.

Nothing under `src/haze/api/` may import this module. The served API is offline
by construction and must stay that way.
"""

from __future__ import annotations

import csv
import io
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd

from .. import config
from .firms import _parse_acq, normalise_confidence

BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire"

# Region split published by FIRMS. Our domain (105-116E, -5 to 4N) sits inside it.
REGION = "SouthEast_Asia"

# (path segment, file prefix). These are the same sensors the model trained on;
# NOAA-20 is included because it is the same VIIRS instrument on a second
# platform and materially improves overpass coverage of the trailing hours.
SENSORS: tuple[tuple[str, str], ...] = (
    ("suomi-npp-viirs-c2", "SUOMI_VIIRS_C2"),
    ("noaa-20-viirs-c2", "J1_VIIRS_C2"),
    ("modis-c6.1", "MODIS_C6_1"),
)

WINDOWS = ("24h", "48h", "7d")

# The NRT schema differs from the archive: there is no `instrument` column (it
# carries `version` instead), so the archive's KEEP list cannot be reused as-is.
# We derive `instrument` from the sensor we asked for.
NRT_COLUMNS = (
    "latitude", "longitude", "acq_date", "acq_time",
    "frp", "confidence", "satellite", "daynight",
)


def nrt_url(sensor_path: str, prefix: str, window: str = "7d") -> str:
    return f"{BASE}/{sensor_path}/csv/{prefix}_{REGION}_{window}.csv"


def fetch(sensor_path: str, prefix: str, window: str = "7d", timeout: int = 120) -> pd.DataFrame:
    """Download one NRT file and return it domain-filtered and normalised.

    Returns an empty frame on any failure. A live snapshot degrades to fewer
    sensors rather than dying, but the caller must report which sensors it
    actually got - silently forecasting off one satellite is not acceptable.
    """
    url = nrt_url(sensor_path, prefix, window)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                print(f"    ! {prefix} {window}: HTTP {resp.status}")
                return pd.DataFrame()
            payload = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"    ! {prefix} {window}: {exc}")
        return pd.DataFrame()

    rows = list(csv.DictReader(io.StringIO(payload)))
    if not rows:
        print(f"    ! {prefix} {window}: empty response")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    missing = [c for c in NRT_COLUMNS if c not in df.columns]
    if missing:
        # Schema drift upstream. Loud, because silently dropping a column that
        # feeds the exposure index would quietly change every forecast.
        print(f"    ! {prefix} {window}: missing columns {missing}; skipping this sensor")
        return pd.DataFrame()

    df = df[list(NRT_COLUMNS)].copy()
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"])

    lon_min, lat_min, lon_max, lat_max = config.DOMAIN_BBOX
    df = df[
        df["longitude"].between(lon_min, lon_max)
        & df["latitude"].between(lat_min, lat_max)
    ].copy()
    if df.empty:
        return df

    df["acq_time_utc"] = [
        _parse_acq(d, t) for d, t in zip(df["acq_date"].astype(str), df["acq_time"])
    ]
    df["frp"] = pd.to_numeric(df["frp"], errors="coerce").fillna(0.0)
    df["confidence"] = [
        normalise_confidence(sensor_path, v) for v in df["confidence"].astype(str)
    ]
    df["instrument"] = "MODIS" if "modis" in sensor_path else "VIIRS"
    df["sensor"] = sensor_path
    df["country"] = [
        assign_country(lat, lon)
        for lat, lon in zip(df["latitude"], df["longitude"])
    ]
    return df


# Approximate Indonesia/Malaysia land border across Borneo, as (lon, lat)
# waypoints. North of this line is Sarawak (MY), south is Kalimantan (ID).
# The real border is not a smooth curve; this is a piecewise-linear fit good to
# roughly 20-30 km, which is well inside the ~40 km CAMS grid the forecast is
# scored against.
_BORNEO_BORDER: tuple[tuple[float, float], ...] = (
    (109.0, 2.05), (110.0, 1.60), (111.0, 1.40), (112.0, 1.45),
    (113.0, 1.60), (114.0, 1.90), (115.0, 2.60), (116.0, 4.00),
)


def assign_country(lat: float, lon: float) -> str:
    """Which side of the border a detection sits on.

    The archive path gets this for free: FIRMS splits its country-year files by
    country, so `firms.load()` just labels each file. The NRT product is split
    by *region* instead, so country has to be derived from geometry.

    This matters more than it looks - `ufei_from_ID` and `ufei_from_MY` are
    model features, and they are the ones carrying the transboundary claim. A
    misassignment moves smoke across the border in the feature vector.

    The approximation is deliberately conservative for that claim: west of
    Borneo (Sumatra and the Java Sea) is unconditionally ID, so the failure mode
    is over-attributing to Indonesia rather than inventing Malaysian sources for
    haze that Sarawak is actually receiving.
    """
    if lon < 108.8:  # Sumatra / Java Sea side of the domain
        return "ID"

    pts = _BORNEO_BORDER
    if lon <= pts[0][0]:
        boundary = pts[0][1]
    elif lon >= pts[-1][0]:
        boundary = pts[-1][1]
    else:
        boundary = pts[-1][1]
        for (lon_a, lat_a), (lon_b, lat_b) in zip(pts, pts[1:]):
            if lon_a <= lon <= lon_b:
                span = lon_b - lon_a
                frac = 0.0 if span == 0 else (lon - lon_a) / span
                boundary = lat_a + frac * (lat_b - lat_a)
                break

    return "MY" if lat >= boundary else "ID"


def load_recent(window: str = "7d") -> tuple[pd.DataFrame, dict]:
    """Every available sensor for `window`, concatenated and deduplicated.

    Returns `(frame, provenance)`. The provenance dict records which sensors
    responded and the date span each contributed, so a snapshot can state what
    it was actually built from rather than implying full coverage.
    """
    frames: list[pd.DataFrame] = []
    provenance: dict = {"region": REGION, "window": window, "sensors": {}}

    for sensor_path, prefix in SENSORS:
        df = fetch(sensor_path, prefix, window)
        if df.empty:
            provenance["sensors"][prefix] = {"rows_in_domain": 0, "status": "unavailable"}
            continue
        dates = sorted(df["acq_date"].astype(str).unique())
        provenance["sensors"][prefix] = {
            "rows_in_domain": int(len(df)),
            "first_date": dates[0],
            "last_date": dates[-1],
            "status": "ok",
        }
        frames.append(df)

    if not frames:
        raise RuntimeError(
            "No FIRMS NRT data could be fetched for any sensor. A live snapshot "
            "cannot be produced without hotspots; refusing to emit a forecast "
            "built on an empty fire field."
        )

    out = pd.concat(frames, ignore_index=True)

    # Same dedup rule the archive path uses: MODIS and VIIRS see the same fire,
    # so round to ~1 km and 1 h and keep the highest-FRP detection. Without this
    # the exposure index double-counts a single burn across platforms.
    out["_k"] = (
        out["acq_time_utc"].dt.floor("h").astype(str)
        + "_"
        + out["latitude"].round(2).astype(str)
        + "_"
        + out["longitude"].round(2).astype(str)
    )
    before = len(out)
    out = out.sort_values("frp", ascending=False).drop_duplicates("_k", keep="first")
    out = out.drop(columns="_k").sort_values("acq_time_utc").reset_index(drop=True)
    out["hour"] = out["acq_time_utc"].dt.floor("h")

    provenance["rows_before_dedup"] = int(before)
    provenance["rows_after_dedup"] = int(len(out))
    provenance["latest_detection_utc"] = out["acq_time_utc"].max().isoformat()
    return out, provenance


def latest_complete_hour(hotspots: pd.DataFrame, lag_hours: int = 12) -> datetime:
    """The hour a live forecast should be issued for.

    Not `now`: the trailing hours of any NRT file are only partly populated,
    because a satellite has to fly over before a fire can be detected. Issuing
    at `now` therefore understates recent fire exposure and biases the forecast
    low, which is the dangerous direction. Backing off by `lag_hours` trades a
    little freshness for a fire field that is actually complete.
    """
    latest = hotspots["acq_time_utc"].max()
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return min(now - timedelta(hours=lag_hours), latest.replace(minute=0, second=0, microsecond=0))

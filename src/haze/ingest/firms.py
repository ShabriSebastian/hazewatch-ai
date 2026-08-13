"""NASA FIRMS hotspot ingestion.

Uses the FIRMS *country-year archive* files, which are served without an API
key. This matters: the alternative `/api/area/` endpoint requires a MAP_KEY,
and a demo that depends on a key someone has to provision is a demo that can
fail. Verified available for 2022-2024; 2025 archives are not yet published.

    https://firms.modaps.eosdis.nasa.gov/data/country/{sensor}/{year}/{sensor}_{year}_{Country}.csv
"""

from __future__ import annotations

import csv
import io
import urllib.request
from datetime import datetime, timezone

import pandas as pd

from .. import config

BASE = "https://firms.modaps.eosdis.nasa.gov/data/country"
COUNTRY_ISO = {"Indonesia": "ID", "Malaysia": "MY"}

# Column names differ between sensors (MODIS: brightness/bright_t31,
# VIIRS: bright_ti4/bright_ti5). We keep only what the model uses.
KEEP = [
    "latitude", "longitude", "acq_date", "acq_time", "frp",
    "confidence", "satellite", "instrument", "daynight",
]


def archive_url(sensor: str, year: int, country: str) -> str:
    return f"{BASE}/{sensor}/{year}/{sensor}_{year}_{country}.csv"


def local_path(sensor: str, year: int, country: str):
    return config.RAW_FIRMS / f"{sensor}_{year}_{country}.csv"


def download(sensor: str, year: int, country: str, timeout: int = 300) -> bool:
    """Fetch one country-year archive to disk. Returns False if unavailable."""
    dest = local_path(sensor, year, country)
    if dest.exists() and dest.stat().st_size > 1024:
        return True

    url = archive_url(sensor, year, country)
    config.RAW_FIRMS.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return False
            payload = resp.read()
    except Exception as exc:  # network or 404
        print(f"    ! {sensor} {year} {country}: {exc}")
        return False

    if len(payload) < 1024:  # 404 pages are tiny
        print(f"    ! {sensor} {year} {country}: response too small ({len(payload)} B)")
        return False

    dest.write_bytes(payload)
    return True


def _parse_acq(date_str: str, time_str: str) -> datetime:
    """FIRMS gives acq_time as HHMM (sometimes without leading zeros)."""
    t = str(time_str).zfill(4)
    return datetime(
        int(date_str[0:4]), int(date_str[5:7]), int(date_str[8:10]),
        int(t[0:2]), int(t[2:4]), tzinfo=timezone.utc,
    )


def load(sensor: str, year: int, country: str) -> pd.DataFrame:
    """Read one archive, filter to the transport domain, normalise columns."""
    path = local_path(sensor, year, country)
    if not path.exists():
        return pd.DataFrame(columns=KEEP)

    df = pd.read_csv(path, usecols=lambda c: c in KEEP, low_memory=False)
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
    df["country"] = COUNTRY_ISO.get(country, country[:2].upper())
    df["sensor"] = sensor
    df["frp"] = pd.to_numeric(df["frp"], errors="coerce").fillna(0.0)
    df["confidence"] = df["confidence"].astype(str)
    return df


def load_all() -> pd.DataFrame:
    """Every downloaded archive, concatenated and domain-filtered."""
    frames = []
    for sensor in config.FIRMS_SENSORS:
        for year in config.FIRMS_YEARS:
            for country in config.FIRMS_COUNTRIES:
                df = load(sensor, year, country)
                if not df.empty:
                    frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values("acq_time_utc").reset_index(drop=True)


def normalise_confidence(sensor: str, value: str) -> str:
    """MODIS reports 0-100; VIIRS reports l/n/h. Map both to low/nominal/high."""
    v = str(value).strip().lower()
    if v in ("l", "low"):
        return "low"
    if v in ("n", "nominal"):
        return "nominal"
    if v in ("h", "high"):
        return "high"
    try:
        score = float(v)
    except ValueError:
        return "nominal"
    if score < 30:
        return "low"
    if score < 80:
        return "nominal"
    return "high"

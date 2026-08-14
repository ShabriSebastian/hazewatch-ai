"""Open-Meteo ingestion: ERA5 reanalysis weather and CAMS air quality.

Both APIs are keyless. Every response is cached to disk keyed by
(endpoint, lat, lon, start, end, variables) and never re-fetched, so the whole
pipeline runs offline after one successful download pass.

Note on the PM2.5 target: CAMS is a *reanalysis model*, not a ground station.
Coverage begins around Aug 2022 (verified - 2019 and 2021 return all-null).
Every PM2.5 value this system emits is labelled `cams_reanalysis` for that
reason.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from .. import config

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

WEATHER_VARS = (
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_speed_100m",
    "precipitation",
    "relative_humidity_2m",
    "temperature_2m",
    "boundary_layer_height",
)
AIR_VARS = ("pm2_5", "pm10")


def _cache_path(kind: str, lat: float, lon: float, start: str, end: str, variables) -> str:
    key = f"{kind}|{lat:.3f}|{lon:.3f}|{start}|{end}|{','.join(variables)}"
    digest = hashlib.md5(key.encode()).hexdigest()[:12]
    return config.RAW_METEO / f"{kind}_{lat:.3f}_{lon:.3f}_{start}_{end}_{digest}.json"


def _fetch(
    url: str, params: dict, cache, retries: int = 6, pause: float = 3.0,
    cached_only: bool = False, refresh: bool = False,
) -> dict:
    """Fetch with disk caching and backoff.

    Open-Meteo rate-limits generously but not infinitely; a full grid pull will
    hit HTTP 429. Since every response is cached, the download script is
    resumable - it is worth waiting rather than failing the run.

    `cached_only` makes a miss return empty instead of reaching for the network.
    Everything downstream of the download step uses it, so feature building,
    training and the demo can never silently depend on connectivity.

    `refresh` is the opposite guarantee, and exists for live inference. The cache
    key contains only the start and end *dates*, so two runs on the same day hit
    the same key - a second run would silently reuse the first run's response and
    present hours-old weather as current. A caller claiming to be live must pass
    `refresh=True` so the bytes are actually fetched now.
    """
    if cache.exists() and not refresh:
        with cache.open() as fh:
            return json.load(fh)

    if cached_only:
        return {}

    config.RAW_METEO.mkdir(parents=True, exist_ok=True)
    full = f"{url}?{urllib.parse.urlencode(params)}"
    last: Exception | None = None

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(full, timeout=180) as resp:
                payload = json.load(resp)
            with cache.open("w") as fh:
                json.dump(payload, fh)
            return payload
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 429:
                # Rate limited: back off hard rather than hammering.
                wait = 60.0 * (attempt + 1)
                print(f"    rate limited, waiting {wait:.0f}s...")
                time.sleep(wait)
                continue
            if attempt < retries - 1:
                time.sleep(pause * (attempt + 1))
        except Exception as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(pause * (attempt + 1))

    raise RuntimeError(f"Open-Meteo fetch failed after {retries} attempts: {last}")


def _to_frame(payload: dict, variables) -> pd.DataFrame:
    hourly = payload.get("hourly", {})
    if "time" not in hourly:
        return pd.DataFrame()
    df = pd.DataFrame({"time": pd.to_datetime(hourly["time"], utc=True)})
    for var in variables:
        df[var] = hourly.get(var, [None] * len(df))
    return df


def weather(
    lat: float, lon: float, start: str, end: str, cached_only: bool = False,
    refresh: bool = False,
) -> pd.DataFrame:
    """Hourly ERA5 reanalysis weather at a point.

    For recent dates this endpoint returns forecast-model output rather than ERA5
    reanalysis - verified byte-identical to api.open-meteo.com/v1/forecast over
    48 overlapping hours. Live callers should surface that as a caveat.
    """
    cache = _cache_path("era5", lat, lon, start, end, WEATHER_VARS)
    payload = _fetch(
        ARCHIVE_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": start,
            "end_date": end,
            "hourly": ",".join(WEATHER_VARS),
            "timezone": "UTC",
            "wind_speed_unit": "ms",
        },
        cache,
        cached_only=cached_only,
        refresh=refresh,
    )
    return _to_frame(payload, WEATHER_VARS)


def air_quality(
    lat: float, lon: float, start: str, end: str, cached_only: bool = False,
    refresh: bool = False,
) -> pd.DataFrame:
    """Hourly CAMS PM2.5/PM10 at a point. This is the model target."""
    cache = _cache_path("cams", lat, lon, start, end, AIR_VARS)
    payload = _fetch(
        AIR_QUALITY_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": start,
            "end_date": end,
            "hourly": ",".join(AIR_VARS),
            "timezone": "UTC",
        },
        cache,
        cached_only=cached_only,
        refresh=refresh,
    )
    return _to_frame(payload, AIR_VARS)


def wind_grid_points() -> list[tuple[float, float]]:
    """Coarse grid over the fire domain, so the transport feature can use wind
    *at the fires* rather than only at the receptor."""
    lon_min, lat_min, lon_max, lat_max = config.DOMAIN_BBOX
    step = config.WIND_GRID_STEP
    points = []
    lat = lat_min
    while lat <= lat_max + 1e-9:
        lon = lon_min
        while lon <= lon_max + 1e-9:
            points.append((round(lat, 3), round(lon, 3)))
            lon += step
        lat += step
    return points

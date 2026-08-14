"""Assemble the hourly training matrix.

Performance note: hotspots do not move. Distance and bearing from every
detection to every receptor are therefore computed once up front, and each
hourly UFEI evaluation becomes a slice plus vectorised arithmetic over the
trailing window. That turns an otherwise hours-long build into a couple of
minutes on a laptop.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .. import config
from ..ingest import firms, weather
from ..institutions import INSTITUTIONS, Institution
from . import exposure

WEATHER_COLS = (
    "wind_speed_10m",
    "wind_direction_10m",
    "precipitation",
    "relative_humidity_2m",
    "temperature_2m",
    "boundary_layer_height",
)
PM_LAGS = (1, 3, 6, 12, 24)


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------
def load_hotspots() -> pd.DataFrame:
    """All detections in the transport domain, deduplicated across sensors."""
    df = firms.load_all()
    if df.empty:
        raise RuntimeError("No FIRMS data found - run scripts/01_download.py first")

    # MODIS and VIIRS see the same fire; round to ~1km and 1h to avoid
    # double-counting the same burn in the exposure sum.
    df["_k"] = (
        df["acq_time_utc"].dt.floor("h").astype(str)
        + "_"
        + df["latitude"].round(2).astype(str)
        + "_"
        + df["longitude"].round(2).astype(str)
    )
    df = df.sort_values("frp", ascending=False).drop_duplicates("_k", keep="first")
    df = df.drop(columns="_k").sort_values("acq_time_utc").reset_index(drop=True)
    df["hour"] = df["acq_time_utc"].dt.floor("h")
    return df


def load_wind_grid(
    start: str | None = None,
    end: str | None = None,
    cached_only: bool = True,
    refresh: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, pd.DatetimeIndex]:
    """Gridded wind direction over the fire domain.

    Returns (wind_dir[time, lat, lon], lats, lons, times).

    Defaults reproduce the historical behaviour exactly. A live caller passes a
    recent window with `cached_only=False`, which costs one Open-Meteo request
    per grid cell - 120 at `config.WIND_GRID_STEP = 1.0`, measured at ~0.8 s
    each, so roughly 100 s wall-clock for the grid alone.
    """
    start = start or config.HISTORY_START
    end = end or config.HISTORY_END
    points = weather.wind_grid_points()
    lats = np.array(sorted({p[0] for p in points}))
    lons = np.array(sorted({p[1] for p in points}))

    frames: dict[tuple[float, float], pd.DataFrame] = {}
    for lat, lon in points:
        df = weather.weather(lat, lon, start, end, cached_only=cached_only, refresh=refresh)
        if not df.empty:
            frames[(lat, lon)] = df.set_index("time")

    if not frames:
        raise RuntimeError("No gridded wind found - run scripts/01_download.py first")

    missing = len(points) - len(frames)
    if missing:
        # Gaps are interpolated from neighbouring cells below. Reported rather
        # than hidden, since silent interpolation is how bad features happen.
        print(f"  {missing}/{len(points)} grid cells uncached; interpolating from neighbours")

    times = next(iter(frames.values())).index
    grid = np.full((len(times), len(lats), len(lons)), np.nan, dtype=np.float32)
    lat_pos = {v: i for i, v in enumerate(lats)}
    lon_pos = {v: i for i, v in enumerate(lons)}
    for (lat, lon), df in frames.items():
        series = df.reindex(times)["wind_direction_10m"].to_numpy(dtype=np.float32)
        grid[:, lat_pos[lat], lon_pos[lon]] = series

    # A few grid cells sit over water with gaps; fill along time then fall back
    # to the domain mean so the kernel never sees NaN.
    grid = pd.DataFrame(grid.reshape(len(times), -1)).ffill().bfill().to_numpy(
        dtype=np.float32
    ).reshape(len(times), len(lats), len(lons))
    grid = np.nan_to_num(grid, nan=180.0)
    return grid, lats, lons, times


def load_site_series(
    inst: Institution,
    start: str | None = None,
    end: str | None = None,
    cached_only: bool = True,
    refresh: bool = False,
) -> pd.DataFrame:
    """Weather and PM2.5 at one institution, joined on the hour.

    Defaults reproduce the historical behaviour exactly: the training window,
    cache-only, never touching the network. `scripts/07_live_snapshot.py` passes
    a recent window with `cached_only=False` to reach Open-Meteo for today.
    Nothing under `src/haze/api/` may do the same - the served path is offline
    by construction.
    """
    start = start or config.HISTORY_START
    end = end or config.HISTORY_END
    w = weather.weather(inst.lat, inst.lon, start, end, cached_only=cached_only, refresh=refresh)
    a = weather.air_quality(inst.lat, inst.lon, start, end, cached_only=cached_only, refresh=refresh)
    if w.empty or a.empty:
        raise RuntimeError(f"Missing series for {inst.id} - run scripts/01_download.py")
    df = w.merge(a[["time", "pm2_5"]], on="time", how="inner")
    return df.rename(columns={"pm2_5": "pm25"}).sort_values("time").reset_index(drop=True)


# --------------------------------------------------------------------------
# Feature assembly
# --------------------------------------------------------------------------
class HotspotGeometry:
    """Precomputed fire->receptor geometry and wind-grid cell indices."""

    def __init__(self, hotspots: pd.DataFrame, lats: np.ndarray, lons: np.ndarray) -> None:
        self.frp = hotspots["frp"].to_numpy(dtype=np.float32)
        self.country = hotspots["country"].to_numpy()
        self.hours = hotspots["hour"].to_numpy()
        self.lat = hotspots["latitude"].to_numpy(dtype=np.float32)
        self.lon = hotspots["longitude"].to_numpy(dtype=np.float32)

        # Wind-grid cell for each fire (fires are static, so this is fixed).
        self.lat_idx = np.abs(lats[None, :] - self.lat[:, None]).argmin(axis=1)
        self.lon_idx = np.abs(lons[None, :] - self.lon[:, None]).argmin(axis=1)

        self._per_site: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    def for_site(self, inst: Institution) -> tuple[np.ndarray, np.ndarray]:
        """(distance_km, bearing_to_site_deg) from every fire to this receptor."""
        if inst.id not in self._per_site:
            dist = exposure.haversine_km(self.lat, self.lon, inst.lat, inst.lon)
            bear = exposure.bearing_deg(self.lat, self.lon, inst.lat, inst.lon)
            self._per_site[inst.id] = (
                dist.astype(np.float32),
                bear.astype(np.float32),
            )
        return self._per_site[inst.id]


def _ufei_slice(
    frp: np.ndarray, dist: np.ndarray, bear: np.ndarray, wind_dir: np.ndarray
) -> float:
    """UFEI over a preselected window slice, using precomputed geometry."""
    if frp.size == 0:
        return 0.0
    alignment = np.cos(np.radians(bear - (wind_dir + 180.0)))
    weights = (
        frp
        * np.clip(alignment, 0.0, None) ** config.UFEI_DIRECTIONAL_POWER
        * np.exp(-dist / config.UFEI_DECAY_KM)
    )
    return float(np.nansum(weights))


def build_site(
    inst: Institution,
    geometry: HotspotGeometry,
    wind_grid: np.ndarray,
    wind_times: pd.DatetimeIndex,
    series: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Hourly feature rows for one institution.

    `series` defaults to the cached training window, which is what every
    historical caller wants. A live caller passes an already-fetched recent
    frame so the same feature assembly runs against today's conditions without
    this function needing to know anything about windows or networks.
    """
    series = load_site_series(inst) if series is None else series
    dist, bear = geometry.for_site(inst)

    hours = series["time"].to_numpy()
    fire_hours = geometry.hours
    time_pos = {t: i for i, t in enumerate(wind_times)}

    max_window = max(config.UFEI_WINDOWS_H)
    rows: list[dict] = []

    for i, now in enumerate(hours):
        # Trailing window slices via binary search on the sorted detection times.
        window_start = now - np.timedelta64(max_window, "h")
        lo = np.searchsorted(fire_hours, window_start, side="left")
        hi = np.searchsorted(fire_hours, now, side="right")

        row: dict = {"time": now, "institution_id": inst.id}

        if hi > lo:
            w_pos = time_pos.get(pd.Timestamp(now))
            sl = slice(lo, hi)
            slice_hours = fire_hours[sl]
            if w_pos is None:
                wind_dir = np.full(hi - lo, 180.0, dtype=np.float32)
            else:
                wind_dir = wind_grid[w_pos, geometry.lat_idx[sl], geometry.lon_idx[sl]]

            for window in config.UFEI_WINDOWS_H:
                mask = slice_hours >= (now - np.timedelta64(window, "h"))
                row[f"ufei_{window}h"] = _ufei_slice(
                    geometry.frp[sl][mask], dist[sl][mask], bear[sl][mask], wind_dir[mask]
                )

            # Which side of the border is driving the exposure (48h window).
            mask48 = slice_hours >= (now - np.timedelta64(48, "h"))
            countries = geometry.country[sl][mask48]
            for code in ("ID", "MY"):
                cmask = countries == code
                row[f"ufei_from_{code}"] = _ufei_slice(
                    geometry.frp[sl][mask48][cmask],
                    dist[sl][mask48][cmask],
                    bear[sl][mask48][cmask],
                    wind_dir[mask48][cmask],
                )

            # Direction-blind ring counts (24h), to contrast against the UFEI.
            mask24 = slice_hours >= (now - np.timedelta64(24, "h"))
            d24, f24 = dist[sl][mask24], geometry.frp[sl][mask24]
            for a, b in zip(config.RING_EDGES_KM[:-1], config.RING_EDGES_KM[1:]):
                ring = (d24 >= a) & (d24 < b)
                row[f"hotspots_{a}_{b}km"] = float(ring.sum())
                row[f"frp_{a}_{b}km"] = float(np.nansum(f24[ring]))
        else:
            for window in config.UFEI_WINDOWS_H:
                row[f"ufei_{window}h"] = 0.0
            for code in ("ID", "MY"):
                row[f"ufei_from_{code}"] = 0.0
            for a, b in zip(config.RING_EDGES_KM[:-1], config.RING_EDGES_KM[1:]):
                row[f"hotspots_{a}_{b}km"] = 0.0
                row[f"frp_{a}_{b}km"] = 0.0

        rows.append(row)

    features = pd.DataFrame(rows)
    out = series.merge(features, on="time", how="left")

    # Receptor weather, temporal encodings, persistence lags.
    wd = out["wind_direction_10m"].fillna(180.0)
    out["wind_dir_sin"] = np.sin(np.radians(wd))
    out["wind_dir_cos"] = np.cos(np.radians(wd))
    out["precip_24h_sum"] = out["precipitation"].fillna(0).rolling(24, min_periods=1).sum()

    hour_of_day = out["time"].dt.hour
    day_of_year = out["time"].dt.dayofyear
    out["hour_sin"] = np.sin(2 * np.pi * hour_of_day / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hour_of_day / 24)
    out["doy_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    out["doy_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)

    for lag in PM_LAGS:
        out[f"pm25_lag_{lag}h"] = out["pm25"].shift(lag)
    out["pm25_roll_24h"] = out["pm25"].rolling(24, min_periods=1).mean()

    # Targets: PM2.5 at t+1 .. t+24.
    for lead in range(1, config.FORECAST_HORIZON_HOURS + 1):
        out[f"target_{lead}h"] = out["pm25"].shift(-lead)

    out["country"] = inst.country
    out["institution_id"] = inst.id
    return out


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Ordered model input columns. Frozen to models/v1/feature_spec.json to
    prevent train/serve skew."""
    exclude = {"time", "institution_id", "country", "pm25", "pm10"}
    return [
        c
        for c in df.columns
        if c not in exclude and not c.startswith("target_") and df[c].dtype != object
    ]


def build_all() -> pd.DataFrame:
    print("Loading hotspots...")
    hotspots = load_hotspots()
    print(f"  {len(hotspots):,} detections in domain after cross-sensor dedup")

    print("Loading gridded wind...")
    wind_grid, lats, lons, wind_times = load_wind_grid()
    print(f"  {wind_grid.shape[0]:,} hours x {len(lats)} x {len(lons)} cells")

    geometry = HotspotGeometry(hotspots, lats, lons)

    frames = []
    for inst in INSTITUTIONS:
        df = build_site(inst, geometry, wind_grid, wind_times)
        print(f"  {inst.id:20s} {len(df):,} rows, PM2.5 coverage {df['pm25'].notna().mean():.1%}")
        frames.append(df)

    out = pd.concat(frames, ignore_index=True)

    # One-hot site identity so a single model serves every institution.
    for inst in INSTITUTIONS:
        out[f"site_{inst.id}"] = (out["institution_id"] == inst.id).astype(float)

    return out


def save(df: pd.DataFrame) -> None:
    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    config.MODELS.mkdir(parents=True, exist_ok=True)
    df.to_parquet(config.FEATURES_PARQUET, index=False)

    spec = {
        "features": feature_columns(df),
        "targets": [f"target_{h}h" for h in range(1, config.FORECAST_HORIZON_HOURS + 1)],
        "ufei_decay_km": config.UFEI_DECAY_KM,
        "ufei_directional_power": config.UFEI_DIRECTIONAL_POWER,
        "ufei_windows_h": list(config.UFEI_WINDOWS_H),
        "ring_edges_km": list(config.RING_EDGES_KM),
    }
    with config.FEATURE_SPEC.open("w") as fh:
        json.dump(spec, fh, indent=2)
    print(f"\nWrote {config.FEATURES_PARQUET} ({len(df):,} rows)")
    print(f"Wrote {config.FEATURE_SPEC} ({len(spec['features'])} features)")

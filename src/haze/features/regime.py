"""Candidate regime features: landscape dryness and ENSO phase.

Both exist because the forecast model currently has no way to tell one fire
season from another. Its only seasonality is `doy_sin`/`doy_cos`, which take
identical values on the same calendar day of every year, so a La Nina September
and an El Nino September are the same input. Phase 1 recorded that as root
cause 4; these are the two cheapest candidate fixes.

**Deliberately not wired into `features.build.build_site` yet.** They are
evaluated as isolated ablations first (`scripts/13_ablations.py`), and only a
feature that earns its place should change the served feature set - adding a
column to the production pipeline also rewrites `models/v1/feature_spec.json`
and invalidates every published number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config

# --------------------------------------------------------------------------
# Dryness
# --------------------------------------------------------------------------
# BMKG's operational "hari tanpa hujan" (days without rain) counts a day dry
# below 1 mm of accumulated rainfall, not at exactly zero: trace amounts neither
# wet the fuel nor suppress a peat fire. Matching their definition matters
# because the resulting number is one Indonesian forecasters already act on.
DRY_DAY_MM = 1.0


def consecutive_dry_days(frame: pd.DataFrame) -> pd.Series:
    """Days without rain, as of the last *complete* day before each hour.

    `frame` needs `time` and `precipitation` for a single site.

    The causality here is the whole difficulty. At 09:00 the current day has
    fifteen hours still to come, so a count that included today would be reading
    rain that has not fallen yet - the feature would quietly carry the afternoon
    into the morning's forecast. The count is therefore taken as of the end of
    the previous complete day and held flat across the current one. That costs
    up to 23 hours of freshness and is the correct trade: a leaked feature
    inflates validation scores and then fails in production, which is precisely
    the class of error this project is auditing.
    """
    work = frame[["time", "precipitation"]].sort_values("time")
    day = work["time"].dt.floor("D")
    daily = work.groupby(day)["precipitation"].sum()

    dry = daily < DRY_DAY_MM
    # Run length of consecutive dry days ending on each day: reset the cumulative
    # count every time a wet day interrupts the streak.
    streak_id = (~dry).cumsum()
    run = dry.groupby(streak_id).cumsum()
    run[~dry] = 0

    # Shift to the previous complete day, then broadcast back to hourly.
    previous = run.shift(1).fillna(0.0)
    return day.map(previous).astype(float).rename("consecutive_dry_days")


def _streak_by_day(daily: pd.Series) -> pd.Series:
    """Consecutive-dry-day run length ending on each day, shifted one day back.

    Shared by the receptor and upwind indices so the causality argument above is
    made once and cannot drift between the two.
    """
    dry = daily < DRY_DAY_MM
    run = dry.groupby((~dry).cumsum()).cumsum()
    run[~dry] = 0
    return run.shift(1).fillna(0.0)


def upwind_dry_days(
    df: pd.DataFrame, lo_km: float = 150.0, hi_km: float = 400.0
) -> pd.Series:
    """Days without rain **in the fire source region**, per locality.

    `consecutive_dry_days` above measures the receiving city. That is the wrong
    place, and the archive says so: the 2024 season was drier at the receptor
    than 2023 (0.83 against 0.55 mean dry days) while recording a quarter of the
    peak PM2.5. The fires that drive these episodes burn 150-400 km upwind, and
    BMKG's operational `hari tanpa hujan` is a regional product, not a
    city-centre reading. This measures the same index where the fuel actually is.

    Precipitation comes from the cached 1-degree domain grid - the same cells
    `features.build.load_wind_grid` reads for wind at the fires, requested
    `cached_only` so this can never reach the network.

    Cells are included when they fall in the annulus **and** have at least one
    FIRMS detection in the archive. Roughly two-fifths of each annulus is ocean
    or unburnt, and averaging in rainfall from places nothing is burning would
    dilute the signal. The mask is binary rather than a fire-density weight,
    because a continuous weight is a free parameter a reviewer could fairly read
    as tuning; and it is derived from the whole archive rather than from any
    scoring window, so it carries no leakage.

    Returns a Series aligned to `df.index`.
    """
    from ..ingest import firms, weather
    from ..institutions import BY_ID
    from . import exposure

    points = weather.wind_grid_points()

    # Static fire mask over the grid. Note the unique sorted axes: `points` holds
    # one entry per cell, so its raw lat/lon lists repeat and cannot be used as
    # lookup axes - matching a detection against them would resolve to whichever
    # cell happened to come first at that latitude.
    grid_lats = np.array(sorted({p[0] for p in points}))
    grid_lons = np.array(sorted({p[1] for p in points}))
    hot = firms.load_all()
    burned = set(
        zip(
            np.abs(grid_lats[None, :] - hot["latitude"].to_numpy()[:, None])
            .argmin(axis=1)
            .tolist(),
            np.abs(grid_lons[None, :] - hot["longitude"].to_numpy()[:, None])
            .argmin(axis=1)
            .tolist(),
        )
    )

    # Per-cell dry-day streak, keyed by day. Cached cells only.
    streaks: dict[tuple[float, float], pd.Series] = {}
    for lat, lon in points:
        cell = weather.weather(
            lat, lon, config.HISTORY_START, config.HISTORY_END, cached_only=True
        )
        if cell.empty or cell["precipitation"].isna().all():
            continue
        daily = cell.groupby(cell["time"].dt.floor("D"))["precipitation"].sum()
        streaks[(lat, lon)] = _streak_by_day(daily)

    missing = len(points) - len(streaks)
    if missing:
        print(f"  {missing}/{len(points)} grid cells uncached; excluded from the index")

    def in_source_region(lat: float, lon: float, inst) -> bool:
        d = float(exposure.haversine_km(np.array([lat]), np.array([lon]), inst.lat, inst.lon)[0])
        if not (lo_km <= d < hi_km):
            return False
        cell = (
            int(np.abs(grid_lats - lat).argmin()),
            int(np.abs(grid_lons - lon).argmin()),
        )
        return cell in burned

    out = pd.Series(np.nan, index=df.index, dtype=float)
    for inst_id in df["institution_id"].unique():
        inst = BY_ID[inst_id]
        chosen = [c for c in streaks if in_source_region(c[0], c[1], inst)]
        if not chosen:
            raise RuntimeError(f"No fire-bearing grid cell in range for {inst_id}")

        regional = pd.concat([streaks[c] for c in chosen], axis=1).mean(axis=1)
        rows = df["institution_id"] == inst_id
        out.loc[rows] = df.loc[rows, "time"].dt.floor("D").map(regional).to_numpy()

    return out.rename("upwind_dry_days")


# --------------------------------------------------------------------------
# ENSO
# --------------------------------------------------------------------------
# Oceanic Nino Index: the 3-month running mean of ERSSTv5 SST anomalies in the
# Nino 3.4 region, keyed here by the month each season is centred on.
#
# !! PROVENANCE WARNING !!
# These values are RECALLED, not read from source. This repository is offline by
# construction and the NOAA CPC table was not fetched. The *phase* of each fire
# season is well established and is what the model feature encodes - 2022 La
# Nina throughout, 2023 rising into a strong El Nino from mid-year, 2024 decaying
# from El Nino to neutral - but the individual decimals should be verified
# against https://origin.cpc.ncep.noaa.gov/products/analysis_monitoring/
# ensostuff/ONI_v5.php before any production use. The categorical feature below
# is robust to a decimal or two of error; a continuous ONI feature would not be,
# which is the main reason the categorical one is what gets fed to the model.
ONI_BY_MONTH: dict[tuple[int, int], float] = {
    (2022, 1): -1.0, (2022, 2): -0.9, (2022, 3): -1.0, (2022, 4): -1.1,
    (2022, 5): -1.0, (2022, 6): -0.9, (2022, 7): -0.8, (2022, 8): -0.9,
    (2022, 9): -1.0, (2022, 10): -1.0, (2022, 11): -0.9, (2022, 12): -0.8,
    (2023, 1): -0.7, (2023, 2): -0.4, (2023, 3): -0.1, (2023, 4): 0.2,
    (2023, 5): 0.5, (2023, 6): 0.8, (2023, 7): 1.1, (2023, 8): 1.3,
    (2023, 9): 1.6, (2023, 10): 1.8, (2023, 11): 1.9, (2023, 12): 2.0,
    (2024, 1): 1.8, (2024, 2): 1.5, (2024, 3): 1.1, (2024, 4): 0.7,
    (2024, 5): 0.4, (2024, 6): 0.2, (2024, 7): 0.1, (2024, 8): 0.0,
    (2024, 9): -0.1, (2024, 10): -0.2, (2024, 11): -0.3, (2024, 12): -0.5,
}

# NOAA's conventional cut-points.
EL_NINO_ONI = 0.5
LA_NINA_ONI = -0.5


def oni(times: pd.Series) -> pd.Series:
    """Continuous ONI for each timestamp. Reported, not fed to the model."""
    keys = list(zip(times.dt.year, times.dt.month))
    return pd.Series([ONI_BY_MONTH.get(k, 0.0) for k in keys], index=times.index)


def enso_regime(times: pd.Series) -> pd.Series:
    """ENSO phase as an ordinal flag: -1 La Nina, 0 neutral, +1 El Nino.

    Ordinal rather than one-hot because the three states sit on a real
    continuum, so the ordering carries information a forest can split on, and
    one column is easier to read in a feature-importance table than three.

    Note what this can and cannot learn from. Across the whole archive the fire
    seasons are 2022 (La Nina), 2023 (El Nino) and 2024 (neutral) - one example
    each. Under the validation protocol, which withholds the 2023 and 2024 fire
    seasons, training sees exactly one labelled fire season. See the Phase 2D
    report before drawing any conclusion from this feature's measured effect.
    """
    values = oni(times)
    regime = pd.Series(0, index=times.index, dtype=int)
    regime[values >= EL_NINO_ONI] = 1
    regime[values <= LA_NINA_ONI] = -1
    return regime.rename("enso_regime")


# --------------------------------------------------------------------------
def add_dryness(df: pd.DataFrame) -> pd.DataFrame:
    """Attach `consecutive_dry_days`, computed per site."""
    out = df.copy()
    parts = [
        consecutive_dry_days(group)
        for _, group in out.groupby("institution_id", sort=False)
    ]
    out["consecutive_dry_days"] = pd.concat(parts).reindex(out.index)
    return out


def add_upwind_dryness(df: pd.DataFrame) -> pd.DataFrame:
    """Attach `upwind_dry_days`, measured over the 150-400 km fire source region."""
    out = df.copy()
    out["upwind_dry_days"] = upwind_dry_days(out)
    return out


def add_enso(df: pd.DataFrame) -> pd.DataFrame:
    """Attach `enso_regime`."""
    out = df.copy()
    out["enso_regime"] = enso_regime(out["time"]).astype(float)
    return out

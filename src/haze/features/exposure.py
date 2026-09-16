"""Upwind Fire Exposure Index (UFEI) and distance-ring hotspot features.

This is the mechanism that lets a fire in Indonesia raise a forecast at a school
in Malaysia. Rather than counting fires within some radius - which is blind to
whether the wind is even pointing at you - each detection is weighted by three
physically meaningful terms:

    alignment = cos(bearing(fire -> receptor) - wind_direction_at_fire)
    weight    = FRP * max(0, alignment)^p * exp(-distance / L)

so a fire counts only to the extent that it is intense, close, and genuinely
upwind. Summing over recent detections gives a source-receptor exposure index.

It is a deliberately simple stand-in for a Lagrangian dispersion model: cheap
enough to compute for every hour of three years on a laptop, and explainable in
one sentence - weight every fire by how hot it is, how far away it is, and
whether the wind is actually carrying its smoke toward you.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Array-safe."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial compass bearing from point 1 to point 2, degrees clockwise from
    north. Array-safe."""
    lat1r, lat2r = np.radians(lat1), np.radians(lat2)
    dlon = np.radians(lon2 - lon1)
    y = np.sin(dlon) * np.cos(lat2r)
    x = np.cos(lat1r) * np.sin(lat2r) - np.sin(lat1r) * np.cos(lat2r) * np.cos(dlon)
    return (np.degrees(np.arctan2(y, x)) + 360.0) % 360.0


def wind_alignment(fire_lat, fire_lon, site_lat, site_lon, wind_dir_deg):
    """How well the wind at the fire points toward the receptor, in [-1, 1].

    Meteorological convention: `wind_direction_10m` is the direction the wind
    blows FROM. The direction it blows TOWARD is that plus 180 degrees. Smoke
    reaches the site when the toward-direction matches the fire->site bearing.
    """
    to_site = bearing_deg(fire_lat, fire_lon, site_lat, site_lon)
    blowing_toward = (np.asarray(wind_dir_deg) + 180.0) % 360.0
    return np.cos(np.radians(to_site - blowing_toward))


def ufei(
    fire_lat,
    fire_lon,
    fire_frp,
    wind_dir_at_fire,
    site_lat: float,
    site_lon: float,
    decay_km: float = config.UFEI_DECAY_KM,
    power: float = config.UFEI_DIRECTIONAL_POWER,
) -> float:
    """Upwind fire exposure at one receptor from a set of detections."""
    if len(fire_lat) == 0:
        return 0.0

    fire_lat = np.asarray(fire_lat, dtype=float)
    fire_lon = np.asarray(fire_lon, dtype=float)
    fire_frp = np.asarray(fire_frp, dtype=float)

    distance = haversine_km(fire_lat, fire_lon, site_lat, site_lon)
    alignment = wind_alignment(fire_lat, fire_lon, site_lat, site_lon, wind_dir_at_fire)

    weights = (
        fire_frp
        * np.clip(alignment, 0.0, None) ** power
        * np.exp(-distance / decay_km)
    )
    return float(np.nansum(weights))


def ring_features(
    fire_lat, fire_lon, fire_frp, site_lat: float, site_lon: float,
    edges_km: tuple = config.RING_EDGES_KM,
) -> dict[str, float]:
    """Plain counts and FRP sums in concentric distance bands.

    Direction-blind on purpose: these give the model a baseline "how much is
    burning nearby at all" signal to contrast against the directional UFEI, so
    feature importances can distinguish the two.
    """
    out: dict[str, float] = {}
    if len(fire_lat) == 0:
        for lo, hi in zip(edges_km[:-1], edges_km[1:]):
            out[f"hotspots_{lo}_{hi}km"] = 0.0
            out[f"frp_{lo}_{hi}km"] = 0.0
        return out

    distance = haversine_km(
        np.asarray(fire_lat, dtype=float), np.asarray(fire_lon, dtype=float),
        site_lat, site_lon,
    )
    frp = np.asarray(fire_frp, dtype=float)
    for lo, hi in zip(edges_km[:-1], edges_km[1:]):
        mask = (distance >= lo) & (distance < hi)
        out[f"hotspots_{lo}_{hi}km"] = float(mask.sum())
        out[f"frp_{lo}_{hi}km"] = float(np.nansum(frp[mask]))
    return out


def source_country_split(
    fire_lat, fire_lon, fire_frp, fire_country, wind_dir_at_fire,
    site_lat: float, site_lon: float,
) -> dict[str, float]:
    """UFEI split by the country each fire sits in.

    This is what makes the transboundary claim measurable rather than asserted:
    for a receptor in Malaysia we can state how much of its upwind exposure
    originates on the Indonesian side of the border.
    """
    countries = np.asarray(fire_country)
    out: dict[str, float] = {}
    for code in ("ID", "MY"):
        mask = countries == code
        out[f"ufei_from_{code}"] = ufei(
            np.asarray(fire_lat)[mask],
            np.asarray(fire_lon)[mask],
            np.asarray(fire_frp)[mask],
            np.asarray(wind_dir_at_fire)[mask],
            site_lat,
            site_lon,
        )
    return out


class WindField:
    """Nearest-neighbour lookup of gridded wind, so each fire is weighted by the
    wind at *its own* location rather than the wind at the receptor hundreds of
    kilometres away."""

    def __init__(self, frame: pd.DataFrame) -> None:
        """`frame` needs columns: time, lat, lon, wind_direction_10m, wind_speed_10m."""
        self._lats = np.sort(frame["lat"].unique())
        self._lons = np.sort(frame["lon"].unique())
        self._by_time: dict[pd.Timestamp, dict[tuple[float, float], tuple[float, float]]] = {}
        for time, group in frame.groupby("time"):
            self._by_time[time] = {
                (r.lat, r.lon): (r.wind_direction_10m, r.wind_speed_10m)
                for r in group.itertuples()
            }

    def _snap(self, lat, lon):
        lat_idx = np.abs(self._lats[None, :] - np.asarray(lat)[:, None]).argmin(axis=1)
        lon_idx = np.abs(self._lons[None, :] - np.asarray(lon)[:, None]).argmin(axis=1)
        return self._lats[lat_idx], self._lons[lon_idx]

    def direction_at(self, time: pd.Timestamp, lat, lon, fallback: float = 180.0):
        """Wind direction at each (lat, lon) for the given hour."""
        cells = self._by_time.get(time)
        if not cells or len(lat) == 0:
            return np.full(len(lat), fallback, dtype=float)
        snap_lat, snap_lon = self._snap(lat, lon)
        return np.array(
            [cells.get((la, lo), (fallback, 0.0))[0] for la, lo in zip(snap_lat, snap_lon)],
            dtype=float,
        )

"""The shared builders for a forecast payload.

One forecast point, and the transboundary attribution block that goes beside it.
Both are used by `scripts/07_live_snapshot.py`, which is now the only thing that
assembles a payload.

This module used to freeze a 12-day scenario into SQLite for the replay
backend - hence the name, and hence `write_scenario`, which walked every hour of
the window recording what the system would have shown. That backend and its
database are retired; what survived is the part that was never about the
scenario, which is how a point and an attribution block are shaped.

Keeping these here rather than inlining them into the snapshot script is
deliberate: `tests/test_forecast_uncertainty.py` builds points through `_point`
so a test cannot accidentally assert against a shape the pipeline never emits.
"""

from __future__ import annotations

import pandas as pd

from .. import config
from ..alerts import thresholds
from ..institutions import Institution


def _iso(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")


def _point(
    timestamp,
    lead: int,
    pm25: float,
    lower=None,
    upper=None,
    median=None,
    beyond_training_range: bool = False,
    extrapolation_reason: str | None = None,
) -> dict:
    pm25 = float(max(0.0, pm25))
    return {
        "timestamp": _iso(timestamp),
        "lead_hours": int(lead),
        "pm25": round(pm25, 1),
        "pm25_lower": round(float(max(0.0, lower)), 1) if lower is not None else None,
        "pm25_upper": round(float(max(0.0, upper)), 1) if upper is not None else None,
        "pm25_p50": round(float(max(0.0, median)), 1) if median is not None else None,
        "beyond_training_range": bool(beyond_training_range),
        "extrapolation_reason": extrapolation_reason,
        "aqi_category": thresholds.categorise(pm25),
        "aqi_us": thresholds.aqi_us(pm25),
    }


def _attribution(row: pd.Series, inst: Institution, top_features: list[dict]) -> dict:
    """Build the transboundary attribution block from the row's UFEI terms."""
    from_id = float(row.get("ufei_from_ID", 0.0) or 0.0)
    from_my = float(row.get("ufei_from_MY", 0.0) or 0.0)
    total = from_id + from_my

    # Normalise the raw UFEI to a 0-1 index using a fixed reference so the
    # number is comparable across sites and over time.
    reference = 4000.0
    index = min(1.0, float(row.get("ufei_48h", 0.0) or 0.0) / reference)

    if total <= 0:
        dominant, share = None, 0.0
    elif from_id >= from_my:
        dominant, share = "ID", from_id / total
    else:
        dominant, share = "MY", from_my / total

    transboundary = bool(dominant is not None and dominant != inst.country and share > 0.5)

    region = None
    if dominant == "ID":
        region = "West Kalimantan, Indonesia"
    elif dominant == "MY":
        region = "Sarawak, Malaysia"

    hotspot_count = int(
        sum(float(row.get(f"hotspots_{a}_{b}km", 0) or 0)
            for a, b in zip(config.RING_EDGES_KM[:-1], config.RING_EDGES_KM[1:]))
    )

    return {
        "upwind_fire_exposure_index": round(index, 3),
        "transboundary": transboundary,
        "source_country": dominant,
        "dominant_source_region": region,
        # Rough transit time: dominant ring distance over observed wind speed.
        "estimated_transport_hours": _transport_hours(row, transboundary),
        "contributing_hotspot_count": hotspot_count,
        "top_feature_contributions": top_features[:4],
    }


def _transport_hours(row: pd.Series, transboundary: bool) -> int | None:
    """Rough transit time from the dominant source ring to the receptor.

    Uses the 100m wind rather than the 10m wind. A smoke plume is advected by
    the flow through the mixed layer, which is faster than the surface wind that
    friction has slowed - using 10m directly gives transit times around 50 hours
    for a 275km hop, which is not physical. Where the 100m field is missing, the
    10m wind is scaled by 1.6, a standard rough factor for this conversion.
    """
    speed = float(row.get("wind_speed_100m", 0) or 0)
    if speed <= 0.3:
        speed = float(row.get("wind_speed_10m", 0) or 0) * 1.6
    if speed <= 0.3:
        return None

    # Cross-border transport is dominated by the 150-400km ring; local by 0-50km.
    distance_km = 275.0 if transboundary else 40.0
    hours = distance_km / (speed * 3.6)  # m/s -> km/h
    return int(round(min(hours, 72)))

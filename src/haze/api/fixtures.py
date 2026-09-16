"""Deterministic placeholder scenario for Day 1.

Purpose: let the frontend build against realistically-shaped payloads before the
real pipeline exists. Curves are anchored on the *measured* 2023 event (Kuching
peaks 58.6 ug/m3 on 3 Sep; Pontianak 307.3 on 6 Sep; West Kalimantan hotspot
counts 1002/1054/1329 on 1-3 Sep) so shapes match what the real data will
produce, but the values here are generated, not observed.

This module is replaced by `haze.replay.store.ScenarioStore` once
`04_precompute_scenario.py` has run. Nothing else imports it.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from functools import lru_cache

from .. import config
from ..alerts import thresholds
from ..institutions import INSTITUTIONS, Institution
from ..models import extrapolation

# Peak PM2.5 and peak time per site, from the measured event.
_PEAKS: dict[str, tuple[float, float, str]] = {
    # id: (baseline, peak, peak_time)
    "id-ptk-sman1": (26.0, 300.0, "2023-09-06T02:00:00Z"),
    "id-ptk-soedarso": (26.0, 296.0, "2023-09-06T02:00:00Z"),
    "id-ptk-bpbd": (25.0, 292.0, "2023-09-06T03:00:00Z"),
    "my-kch-greenroad": (17.0, 57.0, "2023-09-03T02:00:00Z"),
    "my-kch-hus": (17.0, 56.0, "2023-09-03T02:00:00Z"),
    "my-kch-jpbn": (17.0, 55.0, "2023-09-03T03:00:00Z"),
}

_EVENT_WIDTH_H = 46.0  # half-width of the episode envelope


def _jitter(key: str, spread: float) -> float:
    """Deterministic pseudo-noise in [-spread, +spread]; stable across runs."""
    h = int(hashlib.md5(key.encode()).hexdigest()[:8], 16)
    return ((h / 0xFFFFFFFF) * 2.0 - 1.0) * spread


def pm25_at(institution_id: str, when: datetime) -> float:
    """Synthetic PM2.5 curve: baseline + episode envelope + diurnal + noise."""
    baseline, peak, peak_iso = _PEAKS[institution_id]
    peak_t = config.parse_ts(peak_iso)

    dt_h = (when - peak_t).total_seconds() / 3600.0
    envelope = math.exp(-((dt_h / _EVENT_WIDTH_H) ** 2))

    # Nocturnal boundary-layer collapse concentrates smoke overnight.
    diurnal = 1.0 + 0.22 * math.cos((when.hour - 4) / 24.0 * 2 * math.pi)

    value = (baseline + (peak - baseline) * envelope) * diurnal
    value += _jitter(f"{institution_id}{when:%Y%m%d%H}", 0.06 * value)
    return round(max(2.0, value), 1)


def _hotspot_count(when: datetime) -> int:
    """Daily West Kalimantan detection count, shaped like the measured event."""
    peak_t = config.parse_ts("2023-09-03T00:00:00Z")
    dt_h = (when - peak_t).total_seconds() / 3600.0
    envelope = math.exp(-((dt_h / 78.0) ** 2))
    base, top = 120, 1329
    return int(base + (top - base) * envelope)


def hotspots(start: datetime, end: datetime) -> list[dict]:
    """Deterministic hotspots spread over the West Kalimantan source region."""
    out: list[dict] = []
    lon_min, lat_min, lon_max, lat_max = config.WEST_KALIMANTAN_BBOX
    hour = start.replace(minute=0, second=0, microsecond=0)
    while hour <= end:
        # Detections cluster around the two VIIRS overpasses.
        per_hour = _hotspot_count(hour) // 24
        if hour.hour in (2, 6, 14, 18):
            per_hour *= 3
        for k in range(per_hour):
            seed = f"{hour:%Y%m%d%H}-{k}"
            fx = (_jitter(seed + "x", 1.0) + 1.0) / 2.0
            fy = (_jitter(seed + "y", 1.0) + 1.0) / 2.0
            ff = (_jitter(seed + "f", 1.0) + 1.0) / 2.0
            out.append(
                {
                    "id": f"h_{hour:%Y%m%d%H}_{k:04d}",
                    "lat": round(lat_min + fy * (lat_max - lat_min), 4),
                    "lon": round(lon_min + fx * (lon_max - lon_min), 4),
                    "acq_time": config.iso(hour + timedelta(minutes=int(ff * 59))),
                    "frp": round(2.0 + ff * 48.0, 1),
                    "confidence": "high" if ff > 0.6 else "nominal",
                    "satellite": "Suomi-NPP",
                    "instrument": "VIIRS",
                    "country": "ID",
                    "daynight": "D" if 0 <= hour.hour < 10 else "N",
                }
            )
        hour += timedelta(hours=1)
    return out


def observation(inst: Institution, at: datetime) -> dict:
    pm = pm25_at(inst.id, at)
    return {
        "timestamp": config.iso(at),
        "pm25": pm,
        "aqi_category": thresholds.categorise(pm),
        "aqi_us": thresholds.aqi_us(pm),
        "source": "cams_reanalysis",
    }


def forecast_points(inst: Institution, at: datetime, horizon: int) -> list[dict]:
    """Synthetic forecast points, shaped exactly like the precomputed ones.

    The extrapolation fields go through the same `extrapolation.classify` the
    real pipeline uses, so a frontend built entirely against fixtures sees the
    same keys with the same semantics and can build the flagged-state UI before
    the pipeline has ever run. No feature vector exists here, so only the
    band-saturation signal can fire; these curves are anchored on the measured
    307 ug/m3 peak, which is far above anything the forest can emit, so the flag
    does light up during the episode - which is the honest answer for a value the
    model could not have produced.
    """
    ranges = extrapolation.load_training_ranges() or {}
    points = []
    for lead in range(1, horizon + 1):
        ts = at + timedelta(hours=lead)
        pm = pm25_at(inst.id, ts)
        # Uncertainty widens with lead time.
        spread = pm * (0.10 + 0.011 * lead)
        upper = round(pm + spread, 1)
        beyond, reason = (
            extrapolation.classify(upper, None, ranges, lead) if ranges else (False, None)
        )
        points.append(
            {
                "timestamp": config.iso(ts),
                "lead_hours": lead,
                "pm25": pm,
                "pm25_lower": round(max(0.0, pm - spread), 1),
                "pm25_upper": upper,
                "pm25_p50": pm,
                "beyond_training_range": beyond,
                "extrapolation_reason": reason,
                "aqi_category": thresholds.categorise(pm),
                "aqi_us": thresholds.aqi_us(pm),
            }
        )
    return points


def uncertainty(points: list[dict]) -> dict | None:
    """The response-level block for the fixture path, or None when unmeasured."""
    ranges = extrapolation.load_training_ranges()
    return extrapolation.summarise(points, ranges) if ranges else None


@lru_cache(maxsize=1)
def _measured_top_features() -> tuple[dict, ...]:
    """The attribution model's real feature importances, or () when unmeasured.

    Everything else in this module is an invented curve, and that is fine because
    it is *shaped* like the real event and labelled `data_source: fixtures`. Feature
    importances are different: they are a claim about what the model learned, and
    there is no shape to imitate. This previously carried four hardcoded values
    (`upwind_fire_exposure_48h` 0.41, `wind_dir_sin` 0.17, `pm25_lag_24h` 0.14,
    `precip_24h_sum` 0.09) which were not merely approximate but impossible:
    two of those names do not exist in the feature set, and `pm25_lag_24h` is
    excluded from the attribution model by construction (`models/rf.py`, the model
    is trained without lags precisely so it cannot lean on persistence). A client
    comparing this against `/model/metrics` would have found the two disagreeing.

    So read the measured values, and when the model has never been trained return
    nothing at all. `top_feature_contributions` defaults to `[]` in the schema, so
    an empty list is a valid answer; an invented one is not.

    Cached: the file only changes when the training pipeline reruns, which restarts
    the process. Mirrors `extrapolation.load_training_ranges()`.
    """
    path = config.METRICS_JSON
    if not path.exists():
        return ()
    try:
        with path.open() as fh:
            rows = json.load(fh).get("top_features") or []
    except (OSError, ValueError):
        return ()
    return tuple(
        {"feature": r["feature"], "contribution": r["contribution"]}
        for r in rows
        if "feature" in r and "contribution" in r
    )


def attribution(inst: Institution, at: datetime) -> dict:
    """Upwind exposure proxy. Cross-border for Sarawak sites during the episode."""
    pm = pm25_at(inst.id, at)
    baseline = _PEAKS[inst.id][0]
    intensity = min(1.0, max(0.0, (pm - baseline) / (_PEAKS[inst.id][1] - baseline)))
    transboundary = inst.country == "MY" and intensity > 0.15
    return {
        "upwind_fire_exposure_index": round(intensity, 2),
        "transboundary": transboundary,
        "source_country": "ID" if (transboundary or inst.country == "ID") else None,
        "dominant_source_region": "West Kalimantan, Indonesia",
        "estimated_transport_hours": 19 if inst.country == "MY" else 4,
        "contributing_hotspot_count": int(_hotspot_count(at) * (0.3 + 0.5 * intensity)),
        "top_feature_contributions": [dict(r) for r in _measured_top_features()[:4]],
    }


def all_institutions() -> tuple[Institution, ...]:
    return INSTITUTIONS

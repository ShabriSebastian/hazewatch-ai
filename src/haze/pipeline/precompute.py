"""Freeze the demo scenario into SQLite.

Walks every hour of the scenario window and records what the system would have
shown at that moment: hotspots, observed PM2.5, a full 24-hour forecast per
institution, the resulting alert state, and the notification feed.

The point is that the recorded demo does no work at all - it reads rows. No
inference, no network, no variability between takes.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta

import numpy as np
import pandas as pd

from .. import config
from ..alerts import messages, rules, thresholds
from ..institutions import INSTITUTIONS, Institution
from ..models import extrapolation
from ..replay.store import SCHEMA


def _epoch(ts) -> int:
    return int(pd.Timestamp(ts).timestamp())


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


def write_scenario(
    features: pd.DataFrame,
    hotspots: pd.DataFrame,
    forecasts: dict[str, dict],
    top_features: list[dict],
    baselines_by_lead: dict,
    model_name: str,
    db_path=None,
    training_ranges: dict | None = None,
) -> None:
    """Write the scenario database.

    `forecasts` maps institution_id -> {issued_at_iso -> list[point dict]}.
    `training_ranges` is the output of `extrapolation.training_ranges`, already
    carrying the measured model ceiling; omitted, the uncertainty block is simply
    left null and the payload stays valid.
    """
    db_path = db_path or config.SCENARIO_DB
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)

    start = config.parse_ts(config.SCENARIO_START)
    end = config.parse_ts(config.SCENARIO_END)

    # -- meta --------------------------------------------------------------
    conn.executemany(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        [
            ("scenario_id", config.SCENARIO_ID),
            ("scenario_name", config.SCENARIO_NAME),
            ("start", config.SCENARIO_START),
            ("end", config.SCENARIO_END),
            ("model_name", model_name),
            ("model_version", config.MODEL_VERSION),
            ("data_version", config.DATA_VERSION),
        ],
    )

    # -- hotspots ----------------------------------------------------------
    window = hotspots[
        (hotspots["acq_time_utc"] >= start) & (hotspots["acq_time_utc"] <= end)
    ]
    rows = []
    for i, h in enumerate(window.itertuples()):
        rows.append(
            (
                f"h_{_epoch(h.acq_time_utc)}_{i:06d}",
                float(h.latitude),
                float(h.longitude),
                _iso(h.acq_time_utc),
                _epoch(h.acq_time_utc),
                float(h.frp),
                str(h.confidence),
                str(h.satellite),
                str(h.instrument),
                str(h.country),
                str(h.daynight),
            )
        )
    conn.executemany(
        "INSERT OR REPLACE INTO hotspots VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows
    )
    print(f"  hotspots        {len(rows):,}")

    # -- observations, forecasts, alerts, notifications --------------------
    obs_rows, fc_rows, meta_rows, alert_rows, notif_rows = [], [], [], [], []
    last_rank: dict[str, int] = {}
    notif_seq = 0

    for inst in INSTITUTIONS:
        site = features[
            (features["institution_id"] == inst.id)
            & (features["time"] >= start)
            & (features["time"] <= end)
        ].sort_values("time")

        site_forecasts = forecasts.get(inst.id, {})

        for row in site.itertuples():
            when = row.time
            pm = float(row.pm25) if not pd.isna(row.pm25) else 0.0
            obs_rows.append(
                (
                    inst.id,
                    _iso(when),
                    _epoch(when),
                    round(pm, 1),
                    thresholds.categorise(pm),
                    thresholds.aqi_us(pm),
                    "cams_reanalysis",
                )
            )

            issued = _iso(when)
            points = site_forecasts.get(issued)
            if not points:
                continue

            series = pd.Series({c: getattr(row, c, np.nan) for c in features.columns})
            attribution = _attribution(series, inst, top_features)

            uncertainty = (
                extrapolation.summarise(points, training_ranges)
                if training_ranges
                else None
            )

            meta_rows.append(
                (
                    inst.id,
                    issued,
                    _epoch(when),
                    model_name,
                    config.MODEL_VERSION,
                    json.dumps(attribution),
                    json.dumps(baselines_by_lead),
                    json.dumps(uncertainty) if uncertainty else None,
                )
            )
            for p in points:
                fc_rows.append(
                    (
                        inst.id,
                        issued,
                        p["lead_hours"],
                        p["timestamp"],
                        p["pm25"],
                        p["pm25_lower"],
                        p["pm25_upper"],
                        p["aqi_category"],
                        p["aqi_us"],
                        p.get("pm25_p50"),
                        int(bool(p.get("beyond_training_range"))),
                        p.get("extrapolation_reason"),
                    )
                )

            alert = rules.evaluate(inst, when.to_pydatetime(), points, attribution)
            payload = alert or {
                "alert_id": f"alr_clear_{_epoch(when)}_{inst.id}",
                "institution_id": inst.id,
                "institution_name": inst.name,
                "institution_type": inst.type,
                "country": inst.country,
                "severity": thresholds.categorise(max(p["pm25"] for p in points)),
                "status": "resolved",
                "triggered_at": issued,
                "forecast_peak_pm25": max(p["pm25"] for p in points),
                "forecast_peak_at": max(points, key=lambda p: p["pm25"])["timestamp"],
                "lead_time_hours": 0,
                "threshold_pm25": thresholds.alert_threshold(inst.type).pm25,
                "transboundary": attribution["transboundary"],
                "source_country": attribution["source_country"],
                "recommended_actions": [],
                "affected_population": inst.population_served,
                "resolved_at": issued,
            }
            alert_rows.append(
                (payload["alert_id"], inst.id, _epoch(when), json.dumps(payload))
            )

            # Notify only on escalation, as a real system would.
            if alert:
                rank = thresholds.CATEGORY_RANK[alert["severity"]]
                if rank > last_rank.get(inst.id, -1):
                    last_rank[inst.id] = rank
                    notif_seq += 1
                    sent_at = when + timedelta(minutes=5)
                    notification = _notification(inst, alert, sent_at, notif_seq)
                    notif_rows.append(
                        (
                            notification["notification_id"],
                            inst.id,
                            _epoch(sent_at),
                            json.dumps(notification),
                        )
                    )

    conn.executemany("INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?,?)", obs_rows)
    conn.executemany("INSERT OR REPLACE INTO forecast_meta VALUES (?,?,?,?,?,?,?,?)", meta_rows)
    conn.executemany(
        "INSERT OR REPLACE INTO forecasts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", fc_rows
    )
    conn.executemany("INSERT OR REPLACE INTO alerts VALUES (?,?,?,?)", alert_rows)
    conn.executemany("INSERT OR REPLACE INTO notifications VALUES (?,?,?,?)", notif_rows)

    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    print(f"  observations    {len(obs_rows):,}")
    print(f"  forecast issues {len(meta_rows):,}")
    print(f"  forecast points {len(fc_rows):,}")
    print(f"  alert states    {len(alert_rows):,}")
    print(f"  notifications   {len(notif_rows):,}")
    print(f"\n  wrote {db_path} ({db_path.stat().st_size / 1e6:.1f} MB)")


def _notification(inst: Institution, alert: dict, sent_at, seq: int) -> dict:
    lang = messages.default_language(inst)
    return {
        "notification_id": f"ntf_{seq:04d}",
        "alert_id": alert["alert_id"],
        "institution_id": inst.id,
        "institution_name": inst.name,
        "country": inst.country,
        "channel": "whatsapp" if inst.type != "authority" else "sms",
        "recipient_group": inst.recipient_group or f"contacts_{inst.id}",
        "recipient_count": inst.population_served,
        "language": lang,
        "sent_at": _iso(sent_at),
        "status": "delivered",
        "message": messages.render(
            inst=inst,
            severity=alert["severity"],
            peak_pm25=alert["forecast_peak_pm25"],
            peak_at=config.parse_ts(alert["forecast_peak_at"]),
            lead_hours=alert["lead_time_hours"],
            language=lang,
        ),
        "simulated": True,
    }

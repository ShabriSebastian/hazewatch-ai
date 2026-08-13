"""Data access behind the API.

`Store` is the seam that lets the API be built and frozen on Day 1 against
generated fixtures, then switched to precomputed real data with no route
changes. `ScenarioStore` (SQLite, added once the pipeline runs) implements the
same surface.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from .. import config
from ..alerts import messages, rules, thresholds
from ..institutions import INSTITUTIONS, Institution
from . import fixtures


class Store(Protocol):
    source_name: str

    def hotspots(
        self, start: datetime, end: datetime, bbox: tuple[float, float, float, float],
        min_frp: float | None, limit: int,
    ) -> tuple[list[dict], int]: ...

    def observation(self, inst: Institution, at: datetime) -> dict: ...

    def forecast(self, inst: Institution, at: datetime, horizon: int) -> dict: ...

    def alerts(self, at: datetime) -> list[dict]: ...

    def notifications(self, at: datetime, limit: int) -> list[dict]: ...


def _in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    lon_min, lat_min, lon_max, lat_max = bbox
    return lon_min <= lon <= lon_max and lat_min <= lat <= lat_max


class FixtureStore:
    """Day-1 placeholder. Deterministic, offline, realistically shaped.

    Replaced by ScenarioStore once real precomputed data exists.
    """

    source_name = "fixtures"

    def __init__(self) -> None:
        self._hotspot_cache: dict[tuple[str, str], list[dict]] = {}
        self._notification_cache: dict[str, list[dict]] = {}

    # -- hotspots ----------------------------------------------------------
    def hotspots(self, start, end, bbox, min_frp, limit):
        key = (config.iso(start), config.iso(end))
        if key not in self._hotspot_cache:
            self._hotspot_cache[key] = fixtures.hotspots(start, end)
        rows = self._hotspot_cache[key]
        rows = [h for h in rows if _in_bbox(h["lat"], h["lon"], bbox)]
        if min_frp is not None:
            rows = [h for h in rows if h["frp"] >= min_frp]
        return rows[:limit], len(rows)

    # -- forecasts ---------------------------------------------------------
    def observation(self, inst, at):
        return fixtures.observation(inst, at)

    def forecast(self, inst, at, horizon):
        points = fixtures.forecast_points(inst, at, horizon)
        peak = max(points, key=lambda p: p["pm25"])
        return {
            "institution": inst.compact(),
            "issued_at": config.iso(at),
            "model": {
                "name": "fixture-placeholder",
                "version": config.MODEL_VERSION,
                "horizon_hours": horizon,
            },
            "current": fixtures.observation(inst, at),
            "forecast": points,
            "peak": peak,
            "attribution": fixtures.attribution(inst, at),
            "baselines": {
                "persistence_mae": None,
                "climatology_mae": None,
                "model_mae": None,
            },
            "uncertainty": fixtures.uncertainty(points),
        }

    # -- alerts ------------------------------------------------------------
    def alerts(self, at):
        out = []
        for inst in INSTITUTIONS:
            points = fixtures.forecast_points(inst, at, config.FORECAST_HORIZON_HOURS)
            alert = rules.evaluate(inst, at, points, fixtures.attribution(inst, at))
            if alert:
                out.append(alert)
        out.sort(key=lambda a: thresholds.CATEGORY_RANK[a["severity"]], reverse=True)
        return out

    # -- notifications -----------------------------------------------------
    def notifications(self, at, limit):
        """Replay the feed from scenario start up to `at`.

        A notification is emitted the first time an institution's forecast
        severity escalates, which is how a real system would behave: recipients
        are not messaged every hour that conditions stay bad.
        """
        key = config.iso(at)
        if key in self._notification_cache:
            return self._notification_cache[key][:limit]

        start = config.parse_ts(config.SCENARIO_START)
        last_rank: dict[str, int] = {}
        feed: list[dict] = []
        counter = 0

        step = start
        while step <= at:
            for inst in INSTITUTIONS:
                points = fixtures.forecast_points(inst, step, config.FORECAST_HORIZON_HOURS)
                alert = rules.evaluate(inst, step, points, fixtures.attribution(inst, step))
                if not alert:
                    continue
                rank = thresholds.CATEGORY_RANK[alert["severity"]]
                if rank <= last_rank.get(inst.id, -1):
                    continue
                last_rank[inst.id] = rank
                counter += 1
                feed.append(_build_notification(inst, alert, step, counter))
            step += timedelta(hours=1)

        feed.reverse()  # newest first
        self._notification_cache[key] = feed
        return feed[:limit]


def _build_notification(
    inst: Institution, alert: dict, sent_at: datetime, seq: int, channel: str | None = None
) -> dict:
    lang = messages.default_language(inst)
    text = messages.render(
        inst=inst,
        severity=alert["severity"],
        peak_pm25=alert["forecast_peak_pm25"],
        peak_at=config.parse_ts(alert["forecast_peak_at"]),
        lead_hours=alert["lead_time_hours"],
        language=lang,
    )
    return {
        "notification_id": f"ntf_{seq:04d}",
        "alert_id": alert["alert_id"],
        "institution_id": inst.id,
        "institution_name": inst.name,
        "country": inst.country,
        "channel": channel or ("whatsapp" if inst.type != "authority" else "sms"),
        "recipient_group": inst.recipient_group or f"contacts_{inst.id}",
        "recipient_count": inst.population_served,
        "language": lang,
        "sent_at": config.iso(sent_at + timedelta(minutes=5)),
        "status": "delivered",
        "message": text,
        "simulated": True,
    }


build_notification = _build_notification

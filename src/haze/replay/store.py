"""Read the precomputed demo scenario from SQLite.

Everything the demo shows is computed ahead of time and frozen into a single
file: hotspots, observations, the full 24-hour forecast issued at every hour,
alert state, and the notification feed. At demo time there is no network call
and no model inference, so a recorded take is byte-identical to a rehearsal and
cannot fail because a laptop lost Wi-Fi.

Implements the same surface as `haze.api.store.FixtureStore`.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .. import config
from ..institutions import Institution
from ..models import extrapolation


def _epoch(dt: datetime) -> int:
    return int(dt.timestamp())


def _decode_point(row: dict) -> dict:
    """SQLite has no boolean type; the flag round-trips as 0/1."""
    if "beyond_training_range" in row:
        row["beyond_training_range"] = bool(row["beyond_training_range"])
    return row


# Columns added after the contract was first frozen. A database written by an
# older precompute run will not have them, and the frontend team is integrating
# against a live server - so the read path asks what the file actually contains
# and omits what is missing, rather than raising OperationalError on every
# forecast request until someone re-runs `make scenario`.
_OPTIONAL_FORECAST_COLUMNS = ("pm25_p50", "beyond_training_range", "extrapolation_reason")
_BASE_FORECAST_COLUMNS = (
    "timestamp",
    "lead_hours",
    "pm25",
    "pm25_lower",
    "pm25_upper",
    "aqi_category",
    "aqi_us",
)


class ScenarioStore:
    source_name = "scenario_db"

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"No scenario database at {self.path}")
        # Each thread gets its own connection; FastAPI serves from a pool.
        self._local = threading.local()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'scenario_id'"
            ).fetchone()
            self.scenario_id = row[0] if row else config.SCENARIO_ID
            self._forecast_columns = [
                *_BASE_FORECAST_COLUMNS,
                *(c for c in _OPTIONAL_FORECAST_COLUMNS if self._has_column(conn, "forecasts", c)),
            ]
            self._has_uncertainty = self._has_column(conn, "forecast_meta", "uncertainty")

    @staticmethod
    def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
        return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    # -- hotspots ----------------------------------------------------------
    def hotspots(self, start, end, bbox, min_frp, limit):
        lon_min, lat_min, lon_max, lat_max = bbox
        where = [
            "acq_epoch BETWEEN ? AND ?",
            "lon BETWEEN ? AND ?",
            "lat BETWEEN ? AND ?",
        ]
        params: list = [_epoch(start), _epoch(end), lon_min, lon_max, lat_min, lat_max]
        if min_frp is not None:
            where.append("frp >= ?")
            params.append(min_frp)
        clause = " AND ".join(where)

        conn = self._connect()
        total = conn.execute(
            f"SELECT COUNT(*) FROM hotspots WHERE {clause}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT id, lat, lon, acq_time, frp, confidence, satellite, instrument, "
            f"country, daynight FROM hotspots WHERE {clause} "
            f"ORDER BY frp DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
        return [dict(r) for r in rows], int(total)

    # -- observations ------------------------------------------------------
    def observation(self, inst: Institution, at: datetime) -> dict:
        row = self._connect().execute(
            "SELECT timestamp, pm25, aqi_category, aqi_us, source FROM observations "
            "WHERE institution_id = ? AND epoch <= ? ORDER BY epoch DESC LIMIT 1",
            (inst.id, _epoch(at)),
        ).fetchone()
        if row is None:
            return {
                "timestamp": config.iso(at),
                "pm25": 0.0,
                "aqi_category": "GOOD",
                "aqi_us": 0,
                "source": "cams_reanalysis",
            }
        return dict(row)

    # -- forecasts ---------------------------------------------------------
    def forecast(self, inst: Institution, at: datetime, horizon: int) -> dict:
        conn = self._connect()
        head = conn.execute(
            "SELECT * FROM forecast_meta WHERE institution_id = ? AND issued_epoch <= ? "
            "ORDER BY issued_epoch DESC LIMIT 1",
            (inst.id, _epoch(at)),
        ).fetchone()

        if head is None:
            return {
                "institution": inst.compact(),
                "issued_at": config.iso(at),
                "model": {
                    "name": "unavailable",
                    "version": config.MODEL_VERSION,
                    "horizon_hours": horizon,
                },
                "current": self.observation(inst, at),
                "forecast": [],
                "peak": {
                    "timestamp": config.iso(at),
                    "lead_hours": 0,
                    "pm25": 0.0,
                    "aqi_category": "GOOD",
                    "aqi_us": 0,
                },
                "attribution": {
                    "upwind_fire_exposure_index": 0.0,
                    "transboundary": False,
                    "contributing_hotspot_count": 0,
                    "top_feature_contributions": [],
                },
                "baselines": {},
                "uncertainty": None,
            }

        points = [
            _decode_point(dict(r))
            for r in conn.execute(
                f"SELECT {', '.join(self._forecast_columns)} FROM forecasts "
                "WHERE institution_id = ? AND issued_at = ? AND lead_hours <= ? "
                "ORDER BY lead_hours",
                (inst.id, head["issued_at"], horizon),
            ).fetchall()
        ]
        peak = max(points, key=lambda p: p["pm25"]) if points else None

        # Rebuilt from the points actually returned: a caller asking for a shorter
        # horizon must not be told the forecast saturates at +20h when it only
        # asked out to +12h. Rebuilt through `summarise` rather than patched in
        # place so the flags and the human-readable note cannot drift apart.
        uncertainty = None
        if self._has_uncertainty and head["uncertainty"]:
            stored = json.loads(head["uncertainty"])
            uncertainty = extrapolation.summarise(
                points,
                {
                    "target_max_pm25": stored["training_target_max_pm25"],
                    "model_ceiling": {"mean_upper": stored.get("model_ceiling_pm25")},
                },
            )

        return {
            "institution": inst.compact(),
            "issued_at": head["issued_at"],
            "model": {
                "name": head["model_name"],
                "version": head["model_version"],
                "horizon_hours": horizon,
            },
            "current": self.observation(inst, at),
            "forecast": points,
            "peak": peak
            or {
                "timestamp": head["issued_at"],
                "lead_hours": 0,
                "pm25": 0.0,
                "aqi_category": "GOOD",
                "aqi_us": 0,
            },
            "attribution": json.loads(head["attribution"]),
            "baselines": json.loads(head["baselines"]),
            "uncertainty": uncertainty,
        }

    # -- alerts ------------------------------------------------------------
    def alerts(self, at: datetime) -> list[dict]:
        """Alerts as they stood at `at`: the latest evaluation per institution."""
        rows = self._connect().execute(
            "SELECT a.payload FROM alerts a "
            "JOIN (SELECT institution_id, MAX(issued_epoch) AS latest FROM alerts "
            "      WHERE issued_epoch <= ? GROUP BY institution_id) m "
            "  ON a.institution_id = m.institution_id AND a.issued_epoch = m.latest "
            "WHERE a.issued_epoch <= ?",
            (_epoch(at), _epoch(at)),
        ).fetchall()
        alerts = [json.loads(r["payload"]) for r in rows]
        alerts = [a for a in alerts if a.get("status") == "active"]

        from ..alerts import thresholds

        alerts.sort(key=lambda a: thresholds.CATEGORY_RANK[a["severity"]], reverse=True)
        return alerts

    # -- notifications -----------------------------------------------------
    def notifications(self, at: datetime, limit: int) -> list[dict]:
        rows = self._connect().execute(
            "SELECT payload FROM notifications WHERE sent_epoch <= ? "
            "ORDER BY sent_epoch DESC LIMIT ?",
            (_epoch(at), limit),
        ).fetchall()
        return [json.loads(r["payload"]) for r in rows]


# --------------------------------------------------------------------------
# Schema (used by scripts/04_precompute_scenario.py)
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS hotspots (
    id TEXT PRIMARY KEY, lat REAL, lon REAL, acq_time TEXT, acq_epoch INTEGER,
    frp REAL, confidence TEXT, satellite TEXT, instrument TEXT,
    country TEXT, daynight TEXT
);
CREATE INDEX IF NOT EXISTS idx_hotspots_epoch ON hotspots(acq_epoch);

CREATE TABLE IF NOT EXISTS observations (
    institution_id TEXT, timestamp TEXT, epoch INTEGER, pm25 REAL,
    aqi_category TEXT, aqi_us INTEGER, source TEXT,
    PRIMARY KEY (institution_id, epoch)
);

CREATE TABLE IF NOT EXISTS forecast_meta (
    institution_id TEXT, issued_at TEXT, issued_epoch INTEGER,
    model_name TEXT, model_version TEXT,
    attribution TEXT, baselines TEXT, uncertainty TEXT,
    PRIMARY KEY (institution_id, issued_epoch)
);

CREATE TABLE IF NOT EXISTS forecasts (
    institution_id TEXT, issued_at TEXT, lead_hours INTEGER, timestamp TEXT,
    pm25 REAL, pm25_lower REAL, pm25_upper REAL, aqi_category TEXT, aqi_us INTEGER,
    pm25_p50 REAL, beyond_training_range INTEGER, extrapolation_reason TEXT,
    PRIMARY KEY (institution_id, issued_at, lead_hours)
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT, institution_id TEXT, issued_epoch INTEGER, payload TEXT,
    PRIMARY KEY (institution_id, issued_epoch)
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id TEXT PRIMARY KEY, institution_id TEXT,
    sent_epoch INTEGER, payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_notifications_epoch ON notifications(sent_epoch);
"""

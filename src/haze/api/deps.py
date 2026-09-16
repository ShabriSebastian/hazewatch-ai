"""Shared singletons: the replay clock and the active data store.

`get_store()` prefers precomputed real scenario data and falls back to fixtures,
so the API is runnable from Day 1 and upgrades itself the moment
`04_precompute_scenario.py` has produced a scenario database.
"""

from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache

from fastapi import HTTPException

from .. import config
from ..institutions import Institution, get as get_institution
from ..replay.clock import ReplayClock
from .store import FixtureStore, Store

log = logging.getLogger("haze.api")

_clock = ReplayClock()


def get_clock() -> ReplayClock:
    return _clock


@lru_cache(maxsize=1)
def get_store() -> Store:
    """The real precomputed scenario if it is there, fixtures if it is not.

    The fallback keeps the API bootable on Day 1 and on a fresh clone, but it is
    dangerous in a deployment: fixtures are *invented* curves shaped like the
    real event, and an API serving them looks entirely healthy. The only signal
    is `data_source` in /health. So the fallback is loud - if the scenario
    database did not make it into the image, that should be obvious in the logs
    within seconds of boot, not inferred from a judge saying the numbers look
    wrong.
    """
    if config.SCENARIO_DB.exists():
        try:
            from ..replay.store import ScenarioStore

            return ScenarioStore(config.SCENARIO_DB)
        except Exception as exc:  # pragma: no cover - fall back rather than fail to boot
            log.error(
                "Scenario database at %s could not be opened (%s). Falling back to "
                "FIXTURES: responses will be synthetic, not the precomputed 2023 "
                "event. /health will report data_source=fixtures.",
                config.SCENARIO_DB,
                exc,
            )
    else:
        log.error(
            "No scenario database at %s. Falling back to FIXTURES: responses will be "
            "synthetic, not the precomputed 2023 event. If this is a deployment, the "
            "database was left out of the image - it is tracked in git and must ship "
            "with the app. /health will report data_source=fixtures.",
            config.SCENARIO_DB,
        )
    return FixtureStore()


def reset_store_cache() -> None:
    """Used by tests and by the precompute script after writing a scenario."""
    get_store.cache_clear()


def require_institution(institution_id: str) -> Institution:
    inst = get_institution(institution_id)
    if inst is None:
        raise HTTPException(status_code=404, detail=f"Unknown institution '{institution_id}'")
    return inst


def now() -> datetime:
    return _clock.now()


def parse_at(at: str | None) -> datetime:
    """Resolve the `?at=` override, falling back to the replay clock.

    Every read endpoint takes this parameter, and the frontend is expected to
    send it on every request once deployed - holding its own clock rather than
    sharing the server's single global one, so two visitors cannot move each
    other's view of time.

    That makes `at` the most-exercised untrusted input in the API, which is
    reason enough not to let `parse_ts` raise straight through the handler: a
    typo in a URL should be a 422 that says so, not a 500.
    """
    if not at:
        return _clock.now()
    try:
        return config.parse_ts(at)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="at must be ISO-8601 UTC, e.g. 2023-09-04T21:00:00Z"
        )


def parse_bbox(value: str | None) -> tuple[float, float, float, float]:
    if not value:
        return config.DOMAIN_BBOX
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 4:
        raise HTTPException(
            status_code=422, detail="bbox must be 'lon_min,lat_min,lon_max,lat_max'"
        )
    try:
        lon_min, lat_min, lon_max, lat_max = (float(p) for p in parts)
    except ValueError:
        raise HTTPException(status_code=422, detail="bbox values must be numeric")
    if lon_min >= lon_max or lat_min >= lat_max:
        raise HTTPException(status_code=422, detail="bbox min must be less than max")
    return lon_min, lat_min, lon_max, lat_max


def parse_window(start: str | None, end: str | None, default_hours: int = 24):
    """Resolve a [start, end] window, defaulting to the trailing N hours from
    the replay clock."""
    from datetime import timedelta

    clock_now = _clock.now()
    try:
        end_dt = config.parse_ts(end) if end else clock_now
        start_dt = config.parse_ts(start) if start else end_dt - timedelta(hours=default_hours)
    except ValueError:
        raise HTTPException(status_code=422, detail="timestamps must be ISO-8601")
    if start_dt > end_dt:
        raise HTTPException(status_code=422, detail="start must be before end")
    return start_dt, end_dt

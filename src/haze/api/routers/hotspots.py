from __future__ import annotations

import math
from collections import defaultdict

from fastapi import APIRouter, Query

from ... import config
from .. import deps, schemas

router = APIRouter(tags=["hotspots"])


def _query_model(start, end, bbox, min_frp) -> schemas.HotspotQuery:
    return schemas.HotspotQuery(
        start=config.iso(start),
        end=config.iso(end),
        bbox=list(bbox),
        min_frp=min_frp,
    )


@router.get("/hotspots", response_model=schemas.HotspotList)
def list_hotspots(
    start: str | None = Query(None, description="ISO-8601 UTC. Defaults to 24h before `end`."),
    end: str | None = Query(None, description="ISO-8601 UTC. Defaults to the replay clock."),
    bbox: str | None = Query(None, description="lon_min,lat_min,lon_max,lat_max"),
    min_frp: float | None = Query(None, description="Minimum fire radiative power, MW"),
    limit: int = Query(5000, ge=1, le=50000),
) -> schemas.HotspotList:
    start_dt, end_dt = deps.parse_window(start, end)
    box = deps.parse_bbox(bbox)
    rows, total = deps.get_store().hotspots(start_dt, end_dt, box, min_frp, limit)
    return schemas.HotspotList(
        query=_query_model(start_dt, end_dt, box, min_frp),
        count=len(rows),
        total_available=total,
        hotspots=rows,
    )


@router.get("/hotspots/summary", response_model=schemas.HotspotSummary)
def summarise_hotspots(
    start: str | None = Query(None),
    end: str | None = Query(None),
    bbox: str | None = Query(None),
    min_frp: float | None = Query(None),
    grid: float = Query(0.25, gt=0.01, le=5.0, description="Cell size in degrees"),
) -> schemas.HotspotSummary:
    """Gridded aggregation so a map can show a whole season without rendering
    tens of thousands of individual points."""
    start_dt, end_dt = deps.parse_window(start, end)
    box = deps.parse_bbox(bbox)
    rows, _ = deps.get_store().hotspots(start_dt, end_dt, box, min_frp, 1_000_000)

    cells: dict[tuple[int, int], list[float]] = defaultdict(lambda: [0, 0.0])
    for h in rows:
        key = (math.floor(h["lat"] / grid), math.floor(h["lon"] / grid))
        cells[key][0] += 1
        cells[key][1] += h["frp"]

    out = [
        schemas.HotspotGridCell(
            lat=round((gy + 0.5) * grid, 4),
            lon=round((gx + 0.5) * grid, 4),
            count=int(c),
            frp_sum=round(f, 1),
        )
        for (gy, gx), (c, f) in sorted(cells.items())
    ]
    return schemas.HotspotSummary(
        query=_query_model(start_dt, end_dt, box, min_frp),
        grid=grid,
        count=len(rows),
        cells=out,
    )

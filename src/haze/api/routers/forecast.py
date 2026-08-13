from __future__ import annotations

from fastapi import APIRouter, Query

from ... import config
from .. import deps, schemas

router = APIRouter(tags=["forecast"])


@router.get(
    "/institutions/{institution_id}/forecast",
    response_model=schemas.Forecast,
    summary="Short-horizon PM2.5 forecast at one institution",
)
def get_forecast(
    institution_id: str,
    horizon_hours: int = Query(
        config.FORECAST_HORIZON_HOURS, ge=1, le=config.FORECAST_HORIZON_HOURS
    ),
    at: str | None = Query(None, description="Override the replay clock (ISO-8601 UTC)."),
) -> schemas.Forecast:
    """The core endpoint. Returns the hourly PM2.5 trajectory, the forecast
    peak, and an `attribution` block naming the source region and whether the
    smoke is crossing a national border."""
    inst = deps.require_institution(institution_id)
    issued_at = deps.parse_at(at)
    return schemas.Forecast(**deps.get_store().forecast(inst, issued_at, horizon_hours))


@router.get(
    "/institutions/{institution_id}/observation",
    response_model=schemas.Observation,
    summary="Current PM2.5 at one institution",
)
def get_observation(
    institution_id: str,
    at: str | None = Query(None, description="Override the replay clock (ISO-8601 UTC)."),
) -> schemas.Observation:
    inst = deps.require_institution(institution_id)
    when = deps.parse_at(at)
    return schemas.Observation(**deps.get_store().observation(inst, when))

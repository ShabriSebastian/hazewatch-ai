from __future__ import annotations

from fastapi import APIRouter, Query

from .. import deps, schemas

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=schemas.AlertList)
def list_alerts(
    status: str = Query("active", description="active | pending | resolved | all"),
    country: str | None = Query(None, description="ISO-3166-1 alpha-2, e.g. 'MY'"),
    transboundary: bool | None = Query(
        None, description="Filter to alerts whose dominant source is another country."
    ),
    at: str | None = Query(None, description="Override the replay clock (ISO-8601 UTC)."),
) -> schemas.AlertList:
    when = deps.parse_at(at)
    rows = deps.get_store().alerts(when)
    if status != "all":
        rows = [a for a in rows if a["status"] == status]
    if country:
        rows = [a for a in rows if a["country"] == country.upper()]
    if transboundary is not None:
        rows = [a for a in rows if a["transboundary"] is transboundary]
    return schemas.AlertList(count=len(rows), alerts=rows)


@router.get(
    "/institutions/{institution_id}/alert",
    response_model=schemas.AlertStatusResponse,
    summary="Current alert status for one institution",
)
def get_institution_alert(
    institution_id: str,
    at: str | None = Query(None, description="Override the replay clock (ISO-8601 UTC)."),
) -> schemas.AlertStatusResponse:
    inst = deps.require_institution(institution_id)
    when = deps.parse_at(at)
    match = next(
        (a for a in deps.get_store().alerts(when) if a["institution_id"] == institution_id),
        None,
    )
    return schemas.AlertStatusResponse(
        institution=inst.compact(),
        status=match["status"] if match else "resolved",
        alert=match,
    )

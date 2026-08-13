from __future__ import annotations

from fastapi import APIRouter, Query

from ...institutions import INSTITUTIONS
from .. import deps, schemas

router = APIRouter(tags=["institutions"])


@router.get("/institutions", response_model=schemas.InstitutionList)
def list_institutions(
    country: str | None = Query(None, description="Filter by ISO-3166-1 alpha-2, e.g. 'MY'"),
    type: str | None = Query(None, description="school | hospital | authority"),
) -> schemas.InstitutionList:
    rows = list(INSTITUTIONS)
    if country:
        rows = [i for i in rows if i.country == country.upper()]
    if type:
        rows = [i for i in rows if i.type == type.lower()]
    return schemas.InstitutionList(
        count=len(rows), institutions=[i.as_dict() for i in rows]
    )


@router.get("/institutions/{institution_id}", response_model=schemas.Institution)
def get_institution(institution_id: str) -> schemas.Institution:
    return schemas.Institution(**deps.require_institution(institution_id).as_dict())

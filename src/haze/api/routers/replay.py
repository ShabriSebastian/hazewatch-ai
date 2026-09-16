from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ... import config
from ...institutions import INSTITUTIONS
from .. import deps, schemas

router = APIRouter(tags=["replay"])


def _state() -> schemas.ReplayState:
    clock = deps.get_clock().state()
    return schemas.ReplayState(
        scenario_id=config.SCENARIO_ID,
        scenario_name=config.SCENARIO_NAME,
        bookmarks=[schemas.Bookmark(**b) for b in config.BOOKMARKS],
        **clock,
    )


@router.get("/replay/state", response_model=schemas.ReplayState)
def get_state() -> schemas.ReplayState:
    return _state()


@router.post(
    "/replay/seek",
    response_model=schemas.ReplayState,
    summary="Jump the virtual clock to a timestamp or a named bookmark",
)
def seek(request: schemas.SeekRequest) -> schemas.ReplayState:
    clock = deps.get_clock()
    if request.bookmark:
        if clock.seek_bookmark(request.bookmark) is None:
            known = ", ".join(b["key"] for b in config.BOOKMARKS)
            raise HTTPException(
                status_code=404,
                detail=f"Unknown bookmark '{request.bookmark}'. Known: {known}",
            )
    elif request.timestamp:
        try:
            clock.seek(request.timestamp)
        except ValueError:
            raise HTTPException(status_code=422, detail="timestamp must be ISO-8601")
    else:
        raise HTTPException(status_code=422, detail="Provide either 'timestamp' or 'bookmark'")
    return _state()


@router.post("/replay/play", response_model=schemas.ReplayState)
def play(request: schemas.PlayRequest | None = None) -> schemas.ReplayState:
    deps.get_clock().play(request.speed if request else None)
    return _state()


@router.post("/replay/pause", response_model=schemas.ReplayState)
def pause() -> schemas.ReplayState:
    deps.get_clock().pause()
    return _state()


@router.post(
    "/replay/reset",
    response_model=schemas.ReplayState,
    summary="Return to the opening bookmark, paused - used between recording takes",
)
def reset() -> schemas.ReplayState:
    deps.get_clock().reset()
    return _state()


@router.get("/scenarios", response_model=schemas.ScenarioList)
def list_scenarios() -> schemas.ScenarioList:
    scenario = schemas.Scenario(
        id=config.SCENARIO_ID,
        name=config.SCENARIO_NAME,
        start=config.SCENARIO_START,
        end=config.SCENARIO_END,
        institutions=len(INSTITUTIONS),
        bookmarks=[schemas.Bookmark(**b) for b in config.BOOKMARKS],
    )
    return schemas.ScenarioList(count=1, scenarios=[scenario])

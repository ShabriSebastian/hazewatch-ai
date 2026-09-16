from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from ... import config
from .. import deps, schemas

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=schemas.Health)
def health() -> schemas.Health:
    store = deps.get_store()
    return schemas.Health(
        status="ok",
        mode="replay" if config.REPLAY_MODE else "live",
        scenario_id=config.SCENARIO_ID if config.REPLAY_MODE else None,
        clock=deps.get_clock().now_iso() if config.REPLAY_MODE else None,
        data_version=config.DATA_VERSION,
        model_version=config.MODEL_VERSION,
        api_version=config.API_VERSION,
        data_source=store.source_name,
    )


@router.get(
    "/model/metrics",
    response_model=schemas.ModelMetrics,
    summary="Honest held-out performance, for display in the dashboard",
)
def model_metrics() -> schemas.ModelMetrics:
    if not config.METRICS_JSON.exists():
        raise HTTPException(
            status_code=503,
            detail="Model metrics not available yet - training has not been run.",
        )
    with config.METRICS_JSON.open() as fh:
        return schemas.ModelMetrics(**json.load(fh))

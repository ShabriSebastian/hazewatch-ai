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


# Keys `06_validate_events.py` records per event that the API republishes as-is.
_EVENT_FIELDS = ("key", "label", "window", "role", "horizons", "alerts",
                 "peak_observed_pm25", "rows_evaluated")

_MERGE_NOTE = (
    "alerts_corrected supersedes the alerts block above, which is frozen at the "
    "training run that wrote metrics.json and counts all six institutions "
    "separately - reporting 99 episodes where there are 33 distinct ones. "
    "validation_events carries two independently held-out fire seasons scored by "
    "a model that trained on neither; those are a different artifact from the "
    "served model and are labelled separately rather than pooled with it."
)


def _merge_validation(payload: dict) -> dict:
    """Fold the held-out event artifact into the served metrics response.

    Two artifacts, deliberately kept apart. `models/v1/metrics.json` belongs to
    the served model and is frozen for reproducibility - it is never rewritten
    here. `models/v1/metrics_by_event.json` belongs to the validation model and
    carries both held-out seasons plus a recomputed, receptor-deduplicated view
    of the served model's own 2023 numbers.

    Merging happens at read time so the frozen file stays byte-identical while
    the API still tells a reader about the second, less flattering event. Every
    field added here is optional in the schema, so a deployment without the
    validation artifact answers exactly as it did before.
    """
    if not config.METRICS_BY_EVENT_JSON.exists():
        return payload

    with config.METRICS_BY_EVENT_JSON.open() as fh:
        by_event = json.load(fh)

    events = [
        {k: event[k] for k in _EVENT_FIELDS if k in event}
        for event in by_event.get("events", [])
    ]
    if events:
        payload["validation_events"] = events

    # The served model rescored through the same code, not its frozen figures.
    served = by_event.get("served_model_reference") or {}
    if served.get("alerts"):
        payload["alerts_corrected"] = served["alerts"]

    if events or served.get("alerts"):
        payload["notes"] = [*payload.get("notes", []), _MERGE_NOTE]
    return payload


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
        payload = json.load(fh)
    return schemas.ModelMetrics(**_merge_validation(payload))

"""FastAPI application.

Transboundary haze early-warning backend. Consumes existing public hotspot
detections (NASA FIRMS) and adds short-horizon PM2.5 forecasting at named
institutions across two countries, plus automated last-mile alert triggering.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import config
from .routers import alerts, forecast, hotspots, institutions, meta, notifications, replay

DESCRIPTION = """
Short-horizon PM2.5 forecasting and last-mile alerting for institutions exposed
to transboundary haze from Indonesian land and forest fires.

**What this system does**: consumes public satellite hotspot detections and
reanalysis weather, forecasts PM2.5 up to 24 hours ahead at specific schools,
hospitals and disaster-management offices in West Kalimantan (Indonesia) and
Sarawak (Malaysia), and raises alerts with an explicit warning lead time.

**What it does not do**: it does not detect fires from raw satellite imagery -
it consumes NASA FIRMS detections as input. Notifications are simulated; there
is no live SMS or WhatsApp integration. PM2.5 values are drawn from the ECMWF
CAMS reanalysis and are labelled `cams_reanalysis`, not ground-station
measurements.

**Replay mode**: the API serves a precomputed scenario against a virtual clock
so a recorded demonstration is reproducible and needs no network access. See
the `replay` endpoints.
"""

app = FastAPI(
    title="Transboundary Haze Early-Warning API",
    version=config.API_VERSION,
    description=DESCRIPTION,
    contact={"name": "Oxford Saïd Global Climate Tech Challenge 2026 entry"},
)

# The dashboard is built and deployed separately, so it always calls this API
# cross-origin. `allow_credentials` stays False - there are no cookies and no
# auth - which is what makes a wildcard default legitimate rather than lax.
# Narrow it by setting HAZE_ALLOWED_ORIGINS once the dashboard's domain is known.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/api/v1"
for module in (meta, institutions, hotspots, forecast, alerts, notifications, replay):
    app.include_router(module.router, prefix=PREFIX)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "name": app.title,
        "version": app.version,
        "docs": "/docs",
        "openapi": "/openapi.json",
        "api_base": PREFIX,
    }

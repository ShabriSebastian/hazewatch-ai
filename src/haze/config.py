"""Central configuration: spatial domains, time windows, scenario definition.

Everything that a reviewer might want to sanity-check lives here rather than
being scattered through the pipeline.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
# Where the data and model directories live, relative to the repository root.
#
# The default walks up from this file, which is correct for a source checkout and
# for an editable install (src/haze/config.py -> repo root). It is *wrong* for a
# normal `pip install`, where this file lands in site-packages and the walk ends
# up somewhere inside lib/pythonX.Y - so the scenario database is not found and
# the API quietly serves fixtures instead. Deployments therefore set HAZE_ROOT
# explicitly; see the Dockerfile.
ROOT = Path(os.getenv("HAZE_ROOT") or Path(__file__).resolve().parents[2]).resolve()
DATA = ROOT / "data"
RAW_FIRMS = DATA / "raw" / "firms"
RAW_METEO = DATA / "raw" / "openmeteo"
PROCESSED = DATA / "processed"
REPLAY_DIR = DATA / "replay"
MODELS = ROOT / "models" / "v1"
CONTRACT = ROOT / "api_contract"

FEATURES_PARQUET = PROCESSED / "features.parquet"
HOTSPOTS_PARQUET = PROCESSED / "hotspots.parquet"
SCENARIO_DB = REPLAY_DIR / "scenario_2023_sept.sqlite"
METRICS_JSON = MODELS / "metrics.json"
METRICS_BY_EVENT_JSON = MODELS / "metrics_by_event.json"
FEATURE_SPEC = MODELS / "feature_spec.json"
TRAINING_RANGES_JSON = MODELS / "training_ranges.json"

DATA_VERSION = "v1"
MODEL_VERSION = "1.0.0"
API_VERSION = "1.0.0"

# --------------------------------------------------------------------------
# Spatial domain
# --------------------------------------------------------------------------
# Transport domain: everything that could plausibly send smoke to our receptors.
# Covers South Sumatra, West/Central Kalimantan and Sarawak.
DOMAIN_BBOX = (105.0, -5.0, 116.0, 4.0)  # lon_min, lat_min, lon_max, lat_max

# The source region we attribute transboundary transport to.
WEST_KALIMANTAN_BBOX = (108.5, -3.2, 114.3, 2.2)

FIRMS_COUNTRIES = ("Indonesia", "Malaysia")
FIRMS_SENSORS = ("viirs-snpp", "modis")
# 2025 country archives are not published yet (verified 404).
FIRMS_YEARS = (2022, 2023, 2024)

# Coarse grid for wind *at the fires* (not just at the receptor). 1 degree.
WIND_GRID_STEP = 1.0

# --------------------------------------------------------------------------
# Time windows
# --------------------------------------------------------------------------
# CAMS PM2.5 via Open-Meteo begins ~Aug 2022 (verified: 2019/2021 return nulls).
HISTORY_START = "2022-08-01"
HISTORY_END = "2024-12-31"

# The demo event is held out of training entirely - no leakage, and it makes
# the stronger claim: the model had never seen this event.
TEST_START = "2023-08-16"
TEST_END = "2023-10-15"
VAL_START = "2024-11-01"
VAL_END = "2024-12-31"

# --------------------------------------------------------------------------
# Model hyperparameters
# --------------------------------------------------------------------------
FORECAST_HORIZON_HOURS = 24
SEQUENCE_LENGTH_HOURS = 48

# Alerts fire on this percentile of the prediction spread rather than on the
# point forecast, because missing an episode and raising a false alarm are not
# equally costly. Chosen from a measured sweep on held-out data, re-recorded in
# metrics.json under `trigger_sweep` on every training run:
#   p75 -> hit 62.0% / FAR 14.9%      p90 -> hit 83.5% / FAR 25.6%   <- chosen
#   p80 -> hit 67.2% / FAR 17.1%      p95 -> hit 92.0% / FAR 33.0%
#   p85 -> hit 74.1% / FAR 21.1%
# p90 is the most aggressive setting that still keeps false alarms under 30%.
# The right value moves when the model changes, which is why the sweep is
# recomputed and published rather than fixed once.
ALERT_TRIGGER_PERCENTILE = 90

# The lower edge of the prediction band. Both edges are percentiles taken across
# the individual trees of the forest, and both are now published in the API so
# the frontend does not have to assume what the band means.
BAND_LOWER_PERCENTILE = 10

# Number of trees in each forest. Lives here rather than only in RF_PARAMS so
# the API can report it without importing sklearn.
RF_N_ESTIMATORS = 300

# A forecast point counts as "beyond the trained range" once the upper band
# reaches this fraction of the training target ceiling. A tree ensemble averages
# training targets within each leaf, so it cannot report a value above that
# ceiling at all; by the time the band is within 15% of it, the forecast has
# stopped being a severity estimate and become a floor. Verified against the
# scenario: this fires only on the Pontianak peak and never during ordinary
# hours - see the separation table in the offline gate.
EXTRAPOLATION_SATURATION_FRACTION = 0.85

# Upwind Fire Exposure Index kernel
UFEI_DECAY_KM = 300.0  # transport decay length
UFEI_DIRECTIONAL_POWER = 2.0  # sharpness of the upwind cone
UFEI_WINDOWS_H = (24, 48, 72)
RING_EDGES_KM = (0, 50, 150, 400)

# --------------------------------------------------------------------------
# Demo scenario
# --------------------------------------------------------------------------
SCENARIO_ID = "sept_2023_wkal_sarawak"
SCENARIO_NAME = "West Kalimantan -> Sarawak, 28 Aug - 8 Sep 2023"
SCENARIO_START = "2023-08-28T00:00:00Z"
SCENARIO_END = "2023-09-08T23:00:00Z"

# Presenter jump targets. Every one of these was selected by querying the
# precomputed scenario for what the system actually produces, not chosen from
# the daily-mean reconnaissance and hoped for. The figures in each description
# are the ones the API returns at that instant.
BOOKMARKS = [
    {
        "key": "calm",
        "label": "Baseline",
        "timestamp": "2023-08-28T09:00:00Z",
        "description": (
            "No active alerts anywhere. The state the system is watching for a "
            "departure from."
        ),
    },
    {
        "key": "first_warning",
        "label": "Sarawak warned before Indonesia",
        "timestamp": "2023-08-30T19:00:00Z",
        "description": (
            "All three Sarawak institutions alerted 18 hours ahead, while no "
            "Indonesian institution is alerted at all - the smoke is already crossing "
            "the border. Air outside still reads 27 ug/m3. Observation later confirms "
            "a peak of 53 ug/m3."
        ),
    },
    {
        "key": "crossborder",
        "label": "Both countries alerted, 18h ahead",
        "timestamp": "2023-09-02T16:00:00Z",
        "description": (
            "All six institutions alerted across two countries. Kuching is warned 18 "
            "hours ahead while its air reads 13 ug/m3 - good, nothing visibly wrong. "
            "Observation later confirms a peak of 49 ug/m3. Pontianak, alerted from "
            "its own fires, is forecast to 58 ug/m3. Attribution for Sarawak: "
            "West Kalimantan, Indonesia."
        ),
    },
    {
        "key": "severe",
        "label": "Severe episode, Pontianak",
        "timestamp": "2023-09-04T21:00:00Z",
        "description": (
            "Pontianak institutions forecast to reach 86 ug/m3 (unhealthy), with "
            "Sarawak simultaneously alerted 17 hours ahead."
        ),
    },
]
DEFAULT_BOOKMARK = "calm"

# --------------------------------------------------------------------------
# Runtime
# --------------------------------------------------------------------------
REPLAY_MODE = os.getenv("HAZE_REPLAY_MODE", "true").lower() in ("1", "true", "yes")
DEFAULT_REPLAY_SPEED = 120.0  # 120x real time: the 11-day scenario plays in ~2 min

# Browser origins permitted to call the API, comma-separated in
# HAZE_ALLOWED_ORIGINS. The default stays "*", which is correct here rather than
# merely convenient: the API is a public read-only demo, it carries no
# credentials or cookies, and a wildcard is only rejected by browsers when
# `allow_credentials` is on - which it is not. Set the variable to the deployed
# dashboard's origin to narrow it, without a code change or a redeploy of the
# frontend contract.
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("HAZE_ALLOWED_ORIGINS", "*").split(",") if o.strip()
] or ["*"]


def parse_ts(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, tolerating a trailing 'Z', as tz-aware UTC."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    """Serialise a datetime as ISO-8601 UTC with a trailing 'Z'."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bookmark(key: str) -> dict | None:
    return next((b for b in BOOKMARKS if b["key"] == key), None)

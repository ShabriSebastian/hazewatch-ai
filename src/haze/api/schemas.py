"""API response models.

This module IS the contract. `api_contract/openapi.json` is generated from it
and handed to the frontend team; after that point changes must be additive
only (new optional fields, new endpoints) - no renames, no type changes.
`tests/test_contract.py` enforces this.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Enums - the frontend can hardcode these
# --------------------------------------------------------------------------
class AqiCategory(str, Enum):
    GOOD = "GOOD"
    MODERATE = "MODERATE"
    UNHEALTHY_SENSITIVE = "UNHEALTHY_SENSITIVE"
    UNHEALTHY = "UNHEALTHY"
    VERY_UNHEALTHY = "VERY_UNHEALTHY"
    HAZARDOUS = "HAZARDOUS"


class InstitutionType(str, Enum):
    school = "school"
    hospital = "hospital"
    authority = "authority"


class Role(str, Enum):
    source_region = "source_region"
    affected_region = "affected_region"


class AlertStatus(str, Enum):
    active = "active"
    pending = "pending"
    resolved = "resolved"


class Channel(str, Enum):
    sms = "sms"
    whatsapp = "whatsapp"


class DeliveryStatus(str, Enum):
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    failed = "failed"


class Pm25Source(str, Enum):
    """Provenance of a PM2.5 value. Surfaced deliberately: CAMS is a reanalysis
    model, not a ground station, and the product says so rather than implying
    these are measurements."""

    cams_reanalysis = "cams_reanalysis"
    model_forecast = "model_forecast"
    ground_station = "ground_station"


class ExtrapolationReason(str, Enum):
    """Why a forecast point is flagged as beyond the model's trained range."""

    band_saturated = "band_saturated"
    feature_out_of_range = "feature_out_of_range"
    both = "both"


# --------------------------------------------------------------------------
# Core objects
# --------------------------------------------------------------------------
class Institution(BaseModel):
    id: str = Field(examples=["my-kch-greenroad"])
    name: str = Field(examples=["SMK Green Road"])
    type: InstitutionType
    country: str = Field(description="ISO-3166-1 alpha-2", examples=["MY"])
    country_name: str = Field(examples=["Malaysia"])
    admin_region: str = Field(examples=["Sarawak"])
    city: str = Field(examples=["Kuching"])
    lat: float
    lon: float
    population_served: int = Field(
        description="Indirect beneficiaries protected by decisions taken at this site."
    )
    role: Role
    contact_channels: list[Channel]
    languages: list[str] = Field(examples=[["ms", "en"]])
    recipient_group: str = Field(
        description="Mock last-mile distribution list identifier.", default=""
    )


class InstitutionCompact(BaseModel):
    id: str
    name: str
    type: InstitutionType
    country: str
    city: str
    lat: float
    lon: float


class InstitutionList(BaseModel):
    count: int
    institutions: list[Institution]


class Hotspot(BaseModel):
    id: str
    lat: float
    lon: float
    acq_time: str = Field(description="ISO-8601 UTC", examples=["2023-09-03T06:12:00Z"])
    frp: float = Field(description="Fire radiative power, MW")
    confidence: str = Field(examples=["high"])
    satellite: str = Field(examples=["Suomi-NPP"])
    instrument: str = Field(examples=["VIIRS"])
    country: str = Field(examples=["ID"])
    daynight: str = Field(examples=["D"])


class HotspotQuery(BaseModel):
    start: str
    end: str
    bbox: list[float] = Field(description="[lon_min, lat_min, lon_max, lat_max]")
    min_frp: float | None = None


class HotspotList(BaseModel):
    query: HotspotQuery
    count: int = Field(description="Number returned (after `limit`).")
    total_available: int = Field(description="Number matching before `limit` was applied.")
    hotspots: list[Hotspot]


class HotspotGridCell(BaseModel):
    lat: float = Field(description="Cell centre latitude")
    lon: float = Field(description="Cell centre longitude")
    count: int
    frp_sum: float


class HotspotSummary(BaseModel):
    query: HotspotQuery
    grid: float = Field(description="Cell size in degrees")
    count: int = Field(description="Total detections aggregated")
    cells: list[HotspotGridCell]


# --------------------------------------------------------------------------
# Forecast
# --------------------------------------------------------------------------
class Observation(BaseModel):
    timestamp: str
    pm25: float
    aqi_category: AqiCategory
    aqi_us: int
    source: Pm25Source


class ForecastPoint(BaseModel):
    timestamp: str
    lead_hours: int
    pm25: float = Field(
        description="Point forecast: the mean across the forest's trees, in ug/m3."
    )
    pm25_lower: float | None = Field(
        default=None, description="Lower prediction band - p10 across the trees."
    )
    pm25_upper: float | None = Field(
        default=None,
        description=(
            "Upper prediction band - p90 across the trees. This is the value "
            "alerting triggers on, not `pm25`."
        ),
    )
    pm25_p50: float | None = Field(
        default=None, description="Median across the trees. Completes the p10/p50/p90 band."
    )
    beyond_training_range: bool = Field(
        default=False,
        description=(
            "True when this point has left the range the model was trained on - "
            "either the band has saturated against the forest's structural ceiling "
            "or an input feature was outside its training range. Render "
            "'beyond the model's trained range' rather than the bare number: "
            "during extreme episodes the value is a floor, not a severity estimate."
        ),
    )
    extrapolation_reason: ExtrapolationReason | None = Field(
        default=None, description="Which signal fired. Null when the point is in range."
    )
    aqi_category: AqiCategory
    aqi_us: int


class FeatureContribution(BaseModel):
    feature: str
    contribution: float = Field(description="Normalised importance, 0-1")


class Attribution(BaseModel):
    """Why the model expects this. The transboundary claim, made visible in the
    product rather than only asserted in a slide deck."""

    upwind_fire_exposure_index: float = Field(
        description="Normalised 0-1 upwind fire exposure at this receptor."
    )
    transboundary: bool = Field(
        description="True when the dominant contributing hotspots lie in another country."
    )
    source_country: str | None = Field(
        default=None, description="ISO-3166-1 alpha-2 of the dominant source region."
    )
    dominant_source_region: str | None = None
    estimated_transport_hours: int | None = None
    contributing_hotspot_count: int = 0
    top_feature_contributions: list[FeatureContribution] = []


class ModelInfo(BaseModel):
    name: str = Field(examples=["gru-multisite"])
    version: str
    horizon_hours: int


class Baselines(BaseModel):
    """Model error against trivial baselines. Reported so a reviewer can see the
    model earns its place rather than restating persistence."""

    persistence_mae: float | None = None
    climatology_mae: float | None = None
    model_mae: float | None = None


class Uncertainty(BaseModel):
    """Where the prediction band comes from, and where the model runs out of range.

    The band is not a fitted confidence interval: it is the spread of the
    forest's own trees, which disagree most where the training data was thinnest.
    That has a hard consequence worth stating in the payload rather than only in
    a README. Each tree returns an average of training targets in a leaf, so the
    ensemble cannot output a value above `model_ceiling_pm25` no matter how bad
    the air gets. When the band reaches that bound, the forecast has become a
    floor and should be labelled as one.
    """

    method: str = Field(examples=["random_forest_tree_quantiles"])
    lower_percentile: int = Field(description="Percentile across trees for `pm25_lower`.")
    upper_percentile: int = Field(description="Percentile across trees for `pm25_upper`.")
    n_estimators: int = Field(description="Trees in the forest the band is taken across.")
    training_target_max_pm25: float = Field(
        description="Largest PM2.5 target seen in training, in ug/m3."
    )
    model_ceiling_pm25: float | None = Field(
        default=None,
        description=(
            "Highest upper-band value the forest can structurally emit, measured "
            "from its leaves. Lower than `training_target_max_pm25`, because every "
            "leaf averages at least 20 training rows and none is a pure extreme."
        ),
    )
    any_point_beyond_training_range: bool = Field(
        description="True when any point in this forecast is flagged. Drive a banner off this."
    )
    beyond_training_range_from_lead_hours: int | None = Field(
        default=None, description="Earliest flagged lead time, or null when none is."
    )
    note: str = Field(description="A sentence written to be rendered to a user as-is.")


class Forecast(BaseModel):
    institution: InstitutionCompact
    issued_at: str
    model: ModelInfo
    current: Observation
    forecast: list[ForecastPoint]
    peak: ForecastPoint
    attribution: Attribution
    baselines: Baselines
    uncertainty: Uncertainty | None = None


# --------------------------------------------------------------------------
# Alerts
# --------------------------------------------------------------------------
class Alert(BaseModel):
    alert_id: str
    institution_id: str
    institution_name: str
    institution_type: InstitutionType
    country: str
    severity: AqiCategory
    status: AlertStatus
    triggered_at: str
    forecast_peak_pm25: float = Field(
        description="Peak of the value the alert triggered on - the upper prediction "
        "band, not the central estimate. `severity` is derived from this, so the two "
        "always agree. The central forecast is in the forecast endpoint."
    )
    forecast_peak_at: str
    lead_time_hours: int = Field(
        description="Hours between the alert firing and conditions being expected to "
        "cross the threshold - the time the recipient has to act. This is the "
        "headline number; display it prominently."
    )
    peak_lead_hours: int | None = Field(
        default=None, description="Hours until the forecast peak, which is later."
    )
    threshold_crossed_at: str | None = Field(
        default=None, description="When the threshold is expected to be crossed."
    )
    threshold_pm25: float = Field(
        description="The PM2.5 level this alert fired on: always 35.5 ug/m3, the floor "
        "of UNHEALTHY_SENSITIVE. It is the same for every institution type - a hospital "
        "and a school alert on the same air. Institution type changes only the wording "
        "of `recommended_actions`, never the number."
    )
    transboundary: bool
    source_country: str | None = None
    recommended_actions: list[str]
    affected_population: int
    resolved_at: str | None = None


class AlertList(BaseModel):
    count: int
    alerts: list[Alert]


class AlertStatusResponse(BaseModel):
    """Current alert state for one institution; `alert` is null when clear."""

    institution: InstitutionCompact
    status: AlertStatus
    alert: Alert | None = None


# --------------------------------------------------------------------------
# Mocked last-mile notifications
# --------------------------------------------------------------------------
class Notification(BaseModel):
    notification_id: str
    alert_id: str
    institution_id: str
    institution_name: str
    country: str
    channel: Channel
    recipient_group: str
    recipient_count: int
    language: str = Field(examples=["ms"])
    sent_at: str
    status: DeliveryStatus
    message: str
    simulated: bool = Field(
        default=True,
        description="Always true in this MVP. No real SMS/WhatsApp integration exists.",
    )


class NotificationList(BaseModel):
    count: int
    notifications: list[Notification]


class SimulateNotificationRequest(BaseModel):
    institution_id: str
    channel: Channel = Channel.whatsapp
    language: str | None = None


# --------------------------------------------------------------------------
# Replay control
# --------------------------------------------------------------------------
class Bookmark(BaseModel):
    key: str
    label: str
    timestamp: str
    description: str


class ReplayState(BaseModel):
    scenario_id: str
    scenario_name: str
    clock: str
    start: str
    end: str
    speed: float
    playing: bool
    bookmarks: list[Bookmark]


class SeekRequest(BaseModel):
    timestamp: str | None = None
    bookmark: str | None = None


class PlayRequest(BaseModel):
    speed: float = 120.0


class Scenario(BaseModel):
    id: str
    name: str
    start: str
    end: str
    institutions: int
    bookmarks: list[Bookmark]


class ScenarioList(BaseModel):
    count: int
    scenarios: list[Scenario]


# --------------------------------------------------------------------------
# Meta
# --------------------------------------------------------------------------
class Health(BaseModel):
    status: str
    mode: str = Field(description="replay | live")
    scenario_id: str | None = None
    clock: str | None = None
    data_version: str
    model_version: str
    api_version: str
    data_source: str = Field(
        default="fixtures",
        description="'scenario_db' once precomputed data is in place, 'fixtures' before then.",
    )


class HorizonMetrics(BaseModel):
    lead_hours: int
    model_mae: float
    persistence_mae: float
    climatology_mae: float
    improvement_vs_persistence: float = Field(description="Fraction, e.g. 0.18 = 18% better")


class AlertMetrics(BaseModel):
    hit_rate: float = Field(
        description="Hour-level: of issuance hours with a breach coming, how many warned."
    )
    false_alarm_rate: float = Field(
        description=(
            "1 - precision. Depends on how often the event occurs, so it is not "
            "comparable across seasons with different base rates; use specificity."
        )
    )
    median_lead_time_hours: float
    events_evaluated: int = Field(
        description=(
            "Episodes counted per institution. Institutions sharing a grid cell "
            "count separately, so this exceeds distinct_episodes."
        )
    )
    # Optional so the frozen contract stays valid and pre-deduplication metrics
    # files still parse; populated by any run after the receptor fix.
    specificity: float | None = Field(
        default=None, description="Prevalence-free. The figure to compare across years."
    )
    alertable_hour_prevalence: float | None = None
    distinct_episodes: int | None = Field(
        default=None, description="Episodes counted per distinct PM2.5 series."
    )
    episode_detection_rate: float | None = Field(
        default=None,
        description="Episode-level: of distinct episodes, how many were warned before onset.",
    )
    episode_detection_ci95: list[float] | None = Field(
        default=None, description="95% Wilson interval on episode_detection_rate."
    )


class TriggerOperatingPoint(BaseModel):
    percentile: int
    hit_rate: float
    false_alarm_rate: float
    median_lead_time_hours: float


class SpatialResolution(BaseModel):
    """What the PM2.5 source can actually resolve.

    CAMS global composition is ~0.4 degrees native. The three Pontianak
    institutions sit ~3 km apart, as do the three Kuching ones, so all three of
    each share a grid cell and receive the identical series. Forecasts are
    therefore **per-locality**, not per-institution, and this block says so
    rather than leaving a reader to infer it from six identical rows.
    """

    source: str = Field(description="e.g. 'CAMS reanalysis via Open-Meteo'")
    native_resolution_deg: float
    note: str
    groups: dict[str, list[str]] = Field(
        description="Representative institution id -> every institution sharing its cell."
    )
    distinct_receptors: int
    institutions: int


class ModelMetrics(BaseModel):
    model_name: str
    model_version: str
    trained_at: str
    train_period: str
    test_period: str
    test_period_held_out: bool = Field(
        default=True,
        description="The demo event is excluded from training - forecasts over it are out-of-sample.",
    )
    r2_attribution: float | None = Field(
        default=None,
        description="R-squared of the fire-and-weather-only model, in log space. "
        "Log space is the primary figure because the held-out episode peaks above "
        "the training maximum, which a tree ensemble cannot extrapolate past.",
    )
    r2_attribution_raw: float | None = Field(
        default=None, description="The same figure in raw ug/m3 space, for completeness."
    )
    horizons: list[HorizonMetrics]
    alerts: AlertMetrics
    spatial_resolution: SpatialResolution | None = Field(
        default=None,
        description="Which institutions the PM2.5 source can and cannot tell apart.",
    )
    top_features: list[FeatureContribution]
    alert_trigger_percentile: int | None = Field(
        default=None,
        description="Percentile of the prediction spread that alerts fire on. "
        "Above the point forecast, because a missed episode costs more than a "
        "false alarm.",
    )
    trigger_sweep: list[TriggerOperatingPoint] = Field(
        default=[],
        description="The full hit-rate/false-alarm trade-off curve, so the chosen "
        "operating point is visible rather than implicit.",
    )
    notes: list[str] = []

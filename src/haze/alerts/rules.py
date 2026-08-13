"""Turn a forecast into an alert decision.

One rule, applied identically to fixture data and to real model output, so the
demo and the evaluation cannot drift apart.
"""

from __future__ import annotations

from datetime import datetime

from .. import config
from ..institutions import Institution
from . import thresholds

# Actions are institution-type specific: a hospital and a school do different
# things with the same forecast.
RECOMMENDED_ACTIONS: dict[str, dict[str, list[str]]] = {
    "school": {
        "UNHEALTHY_SENSITIVE": [
            "Cancel outdoor sports and morning assembly",
            "Issue N95 masks to students with asthma or respiratory conditions",
            "Keep windows closed; run indoor air filtration where available",
        ],
        "UNHEALTHY": [
            "Suspend all outdoor activity",
            "Move lessons to filtered indoor spaces",
            "Notify parents of students with respiratory conditions",
        ],
        "VERY_UNHEALTHY": [
            "Close the school or switch to remote learning",
            "Advise all students to remain indoors",
            "Coordinate closure timing with the district education office",
        ],
        "HAZARDOUS": [
            "Close the school immediately",
            "Activate the emergency communication tree to all parents",
            "Direct symptomatic students to the nearest clinic",
        ],
    },
    "hospital": {
        "UNHEALTHY_SENSITIVE": [
            "Pre-position nebulisers and salbutamol stock",
            "Brief triage staff on expected respiratory presentations",
            "Verify HVAC filtration is running on recirculation",
        ],
        "UNHEALTHY": [
            "Increase respiratory ward staffing for the next 24 hours",
            "Defer non-urgent outpatient appointments",
            "Open additional oxygen supply points",
        ],
        "VERY_UNHEALTHY": [
            "Activate the surge protocol for respiratory admissions",
            "Recall on-call respiratory staff",
            "Coordinate with district health office on transfer capacity",
        ],
        "HAZARDOUS": [
            "Declare a respiratory emergency footing",
            "Request regional mutual-aid support",
            "Establish a dedicated haze triage area at the entrance",
        ],
    },
    "authority": {
        "UNHEALTHY_SENSITIVE": [
            "Issue a public advisory for sensitive groups",
            "Prepare mask distribution points",
            "Alert school and clinic networks in the district",
        ],
        "UNHEALTHY": [
            "Issue a general public health advisory",
            "Open clean-air shelters",
            "Advise schools to suspend outdoor activity",
        ],
        "VERY_UNHEALTHY": [
            "Recommend school closures across the district",
            "Distribute N95 masks at community points",
            "Escalate to provincial/state disaster command",
        ],
        "HAZARDOUS": [
            "Declare a haze emergency",
            "Close schools district-wide",
            "Coordinate cross-border notification with counterpart agencies",
        ],
    },
}


def actions_for(institution_type: str, severity: str) -> list[str]:
    by_type = RECOMMENDED_ACTIONS.get(institution_type, RECOMMENDED_ACTIONS["authority"])
    if severity in by_type:
        return by_type[severity]
    # Fall back to the most severe tier at or below the requested one.
    for name in reversed(thresholds.CATEGORY_ORDER):
        if name in by_type and thresholds.CATEGORY_RANK[name] <= thresholds.CATEGORY_RANK[severity]:
            return by_type[name]
    return by_type[thresholds.DEFAULT_ALERT_CATEGORY]


def alert_id(institution_id: str, triggered_at: datetime) -> str:
    return f"alr_{triggered_at:%Y%m%d%H}_{institution_id}"


def evaluate(
    inst: Institution,
    issued_at: datetime,
    forecast: list[dict],
    attribution: dict | None = None,
) -> dict | None:
    """Return an alert dict if the forecast breaches this institution's
    threshold within the horizon, else None.

    `lead_time_hours` runs from the alert firing to the expected threshold
    crossing - the time the recipient actually has to act. `peak_lead_hours`
    additionally reports when conditions are expected to be worst, which is
    later and is the wrong number to headline.
    """
    if not forecast:
        return None

    threshold = thresholds.alert_threshold(inst.type)

    # Trigger on the upper prediction band where one exists, falling back to the
    # point forecast. This must match what `evaluate.alert_metrics` measures,
    # otherwise the published hit rate and false alarm rate would describe a
    # system different from the one actually raising these alerts.
    def trigger_value(point: dict) -> float:
        upper = point.get("pm25_upper")
        return float(upper) if upper is not None else float(point["pm25"])

    breaching = [p for p in forecast if trigger_value(p) >= threshold.pm25]
    if not breaching:
        return None

    # Severity, and the peak we report, describe the value the alert actually
    # fired on. Reporting the point forecast here instead would produce alerts
    # labelled "MODERATE" that fired because the upper band reached unhealthy
    # levels - which reads on a dashboard as a system contradicting itself.
    peak = max(forecast, key=trigger_value)
    peak_value = trigger_value(peak)
    severity = thresholds.categorise(peak_value)
    attribution = attribution or {}

    # Warning lead time is the interval between issuing the alert and conditions
    # being expected to cross the threshold - the time the recipient has to act.
    # Measuring to the forecast *peak* instead would inflate the number and
    # would not match the episode-onset lead time reported in metrics.json.
    onset = breaching[0]
    lead_hours = int(onset["lead_hours"])

    return {
        "alert_id": alert_id(inst.id, issued_at),
        "institution_id": inst.id,
        "institution_name": inst.name,
        "institution_type": inst.type,
        "country": inst.country,
        "severity": severity,
        "status": "active",
        "triggered_at": config.iso(issued_at),
        "forecast_peak_pm25": round(peak_value, 1),
        "forecast_peak_at": peak["timestamp"],
        "lead_time_hours": lead_hours,
        "peak_lead_hours": int(peak["lead_hours"]),
        "threshold_crossed_at": onset["timestamp"],
        "threshold_pm25": threshold.pm25,
        "transboundary": bool(attribution.get("transboundary", False)),
        "source_country": attribution.get("source_country"),
        "recommended_actions": actions_for(inst.type, severity),
        "affected_population": inst.population_served,
        "resolved_at": None,
    }

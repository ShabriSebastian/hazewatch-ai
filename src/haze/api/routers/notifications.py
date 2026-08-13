from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ... import config
from ...alerts import rules, thresholds
from .. import deps, schemas
from ..store import build_notification

router = APIRouter(tags=["notifications"])


@router.get(
    "/notifications",
    response_model=schemas.NotificationList,
    summary="Mocked last-mile notification feed",
)
def list_notifications(
    institution_id: str | None = Query(None),
    country: str | None = Query(None, description="ISO-3166-1 alpha-2"),
    limit: int = Query(50, ge=1, le=500),
    at: str | None = Query(None, description="Override the replay clock (ISO-8601 UTC)."),
) -> schemas.NotificationList:
    """Messages that would reach indirect beneficiaries - parents, patients, the
    public. Nothing is actually sent: every entry carries `simulated: true`."""
    when = deps.parse_at(at)
    rows = deps.get_store().notifications(when, limit=500)
    if institution_id:
        rows = [n for n in rows if n["institution_id"] == institution_id]
    if country:
        rows = [n for n in rows if n["country"] == country.upper()]
    rows = rows[:limit]
    return schemas.NotificationList(count=len(rows), notifications=rows)


@router.post(
    "/notifications/simulate",
    response_model=schemas.Notification,
    summary="Fire a single simulated notification on demand",
)
def simulate_notification(
    request: schemas.SimulateNotificationRequest,
    at: str | None = Query(None, description="Override the replay clock (ISO-8601 UTC)."),
) -> schemas.Notification:
    """Sends one message for the institution's current forecast. Used in the
    demo to show the last-mile step happening live."""
    inst = deps.require_institution(request.institution_id)
    when = deps.parse_at(at)

    store = deps.get_store()
    forecast = store.forecast(inst, when, config.FORECAST_HORIZON_HOURS)
    alert = rules.evaluate(inst, when, forecast["forecast"], forecast["attribution"])

    if alert is None:
        # Nothing is breaching, but the operator asked to send. Report the peak
        # anyway rather than inventing an alert that the rules did not raise.
        peak = forecast["peak"]
        alert = {
            "alert_id": f"alr_manual_{when:%Y%m%d%H}_{inst.id}",
            "severity": thresholds.categorise(peak["pm25"]),
            "forecast_peak_pm25": peak["pm25"],
            "forecast_peak_at": peak["timestamp"],
            "lead_time_hours": int(peak["lead_hours"]),
        }

    lang = request.language or None
    notification = build_notification(inst, alert, when, seq=0, channel=request.channel.value)
    notification["notification_id"] = f"ntf_manual_{when:%Y%m%d%H%M}_{inst.id}"
    if lang:
        from ...alerts import messages

        notification["language"] = lang
        notification["message"] = messages.render(
            inst=inst,
            severity=alert["severity"],
            peak_pm25=alert["forecast_peak_pm25"],
            peak_at=config.parse_ts(alert["forecast_peak_at"]),
            lead_hours=alert["lead_time_hours"],
            language=lang,
        )
    return schemas.Notification(**notification)

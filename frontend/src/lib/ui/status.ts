import type { Alert, AlertStatusResponse, Forecast } from "@/lib/api/types";

export type LiteRiskStatus = "safe" | "watch" | "alert";

/**
 * Safe / Watch / Alert is derived from what the API returns, never recomputed
 * from a second copy of the thresholds.
 *
 * - **Alert** is whatever the backend raised an alert for. It owns that
 *   decision and reports the level it fired on as `Alert.threshold_pm25`, which
 *   is 35.5 for every institution type. Recomputing it here against our own
 *   copy of that boundary would risk showing Watch next to a live backend
 *   alert, so we do not keep one.
 * - **Safe vs Watch** comes from the current observation's `aqi_category`,
 *   which already encodes the EPA breakpoints the backend applied (GOOD is
 *   <= 12.0). Safe therefore means "air is normal right now, and nothing in the
 *   forecast window is expected to trigger an alert".
 *
 * A tempting shortcut is to read `forecast.peak.aqi_category` instead of asking
 * whether an alert exists. It does not work: `peak.aqi_category` is categorised
 * from the *central* estimate, while alerting fires on the upper band. At the
 * crossborder bookmark both Kuching and Pontianak read MODERATE on that field
 * while the backend has them actively alerting (upper band 38.5 and 57.7).
 *
 * Requiring every forecast point to be GOOD as well was the obvious
 * alternative for Safe, but it makes Safe unreachable here: the region's
 * ordinary baseline is around 18 ug/m3, already MODERATE, so a sweep of the
 * whole demo scenario returned zero Safe samples.
 */
export function getRiskStatus(
  forecast: Forecast,
  alert: Alert | null | undefined,
): LiteRiskStatus {
  if (alert) return "alert";
  return forecast.current.aqi_category === "GOOD" ? "safe" : "watch";
}

/** Lite screens hold the whole `/alert` response; unwrap and defer. */
export function getLiteRiskStatus(
  forecast: Forecast,
  alertResponse: AlertStatusResponse,
): LiteRiskStatus {
  return getRiskStatus(forecast, alertResponse.alert);
}

/**
 * Pro's Live Monitor ranks all six institutions at once from one `/alerts`
 * call, so it looks each institution up in that list rather than making a
 * per-institution request.
 */
export function getStatusFromAlerts(
  forecast: Forecast,
  alerts: Alert[],
): LiteRiskStatus {
  const match = alerts.find(
    (item) => item.institution_id === forecast.institution.id && item.status === "active",
  );
  return getRiskStatus(forecast, match ?? null);
}

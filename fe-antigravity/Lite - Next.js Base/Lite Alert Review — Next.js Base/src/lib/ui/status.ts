import type { AlertStatusResponse, Forecast } from "@/lib/api/types";

export type LiteRiskStatus = "safe" | "watch" | "alert";

/**
 * Safe / Watch / Alert is derived from what the API returns, never recomputed
 * from a second copy of the thresholds.
 *
 * - **Alert** is whatever the backend raised an alert for. It owns that
 *   decision, including the per-institution-type sensitivity factor that makes
 *   hospitals trigger earlier than schools. Recomputing it here against a single
 *   hardcoded boundary would show Watch next to a live backend alert.
 * - **Safe vs Watch** comes from the current observation's `aqi_category`,
 *   which already encodes the EPA breakpoints the backend applied (GOOD is
 *   <= 12.0). Reading the category reproduces the boundary without restating
 *   the number. Safe therefore means "air is normal right now, and nothing in
 *   the next 24 hours is forecast to trigger an alert".
 *
 * Requiring every forecast point to be GOOD as well was the obvious
 * alternative, but it makes Safe unreachable here: the region's ordinary
 * baseline is around 18 ug/m3, which is already MODERATE, so a sweep of the
 * whole demo scenario returned zero Safe samples and the three-state design
 * collapsed to two on screen.
 *
 * Note that the current observation deliberately does not raise the status to
 * Alert: the contract is explicit that alerting triggers on the forecast upper
 * band, not on present conditions.
 */
export function getLiteRiskStatus(
  forecast: Forecast,
  alertResponse: AlertStatusResponse,
): LiteRiskStatus {
  if (alertResponse.alert) return "alert";

  return forecast.current.aqi_category === "GOOD" ? "safe" : "watch";
}

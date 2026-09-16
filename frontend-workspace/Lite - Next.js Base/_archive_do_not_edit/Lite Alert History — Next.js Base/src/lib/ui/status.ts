import type { AlertStatusResponse, Forecast } from "@/lib/api/types";

export type LiteRiskStatus = "safe" | "watch" | "alert";

export const SAFE_MAX_PM25 = 12.0;
export const ALERT_MIN_PM25 = 35.5;

function getRiskValue(forecast: Forecast) {
  const values = forecast.forecast.map((point) => point.pm25_upper ?? point.pm25);
  return Math.max(forecast.current.pm25, ...values);
}

/**
 * Lite product mapping agreed against CONTRACT.md:
 * Safe 0–12.0; Watch 12.1–35.4; Alert >=35.5.
 * Alerting is based on the upper prediction band when available.
 */
export function getLiteRiskStatus(
  forecast: Forecast,
  alertResponse: AlertStatusResponse,
): LiteRiskStatus {
  if (alertResponse.alert) return "alert";

  const value = getRiskValue(forecast);
  if (value >= ALERT_MIN_PM25) return "alert";
  if (value <= SAFE_MAX_PM25) return "safe";
  return "watch";
}

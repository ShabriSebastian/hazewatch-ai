import type { Alert } from "@/lib/api/types";

/**
 * The alert threshold, for **drawing** only.
 *
 * Status decisions never use this — they come from `alert !== null` and from
 * `aqi_category` (see `getLiteRiskStatus` / `getForecastStatus`), so the client
 * holds no second copy of the alerting logic. But a chart still needs a number
 * to place a reference line on an axis, and a legend still needs one to label.
 *
 * CONTRACT.md states the threshold is 35.5 µg/m³ for every institution type —
 * the floor of UNHEALTHY_SENSITIVE. It is reported per alert as
 * `Alert.threshold_pm25`, so prefer `thresholdFor(alert)`: when an alert is in
 * hand the drawn line comes from the payload, and the constant is only the
 * fallback for charts rendered while nothing is alerting.
 */
export const ALERT_THRESHOLD_PM25 = 35.5;

/** Upper bound of GOOD, used for the Safe/Watch band on chart legends. */
export const GOOD_MAX_PM25 = 12.0;

export function thresholdFor(alert: Alert | null | undefined): number {
  return alert?.threshold_pm25 ?? ALERT_THRESHOLD_PM25;
}

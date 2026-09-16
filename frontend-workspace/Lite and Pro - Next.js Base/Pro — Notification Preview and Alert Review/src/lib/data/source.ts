import {
  getAlertsAt,
  getForecast,
  getHealth,
  getHotspotSummary,
  getInstitution,
  getInstitutionAlert,
  getInstitutions,
  getStatusTimeline,
} from "@/lib/api/hazewatch";
import { initialiseClock } from "@/lib/replay/clock";
import type { Channel, Institution, Notification } from "@/lib/api/types";
import {
  createLocalNotification,
  mockAlertResponse,
  mockForecast,
  mockHealth,
  mockInstitution,
  mockStatusTimeline,
} from "./mock";
import {
  proMockAlerts,
  proMockForecasts,
  proMockHealth,
  proMockHotspotSummary,
  proMockInstitutions,
} from "./proMock";
import { proMockHistoryEvents } from "./proAlertHistoryMock";

export type DataMode = "api" | "mock";

/** Lite shows a 24-hour outlook; Pro's screens are labelled "Next 12 Hours". */
export const LITE_HORIZON_HOURS = 24;
export const PRO_HORIZON_HOURS = 12;

export function getDataMode(): DataMode {
  return process.env.NEXT_PUBLIC_HAZE_DATA_MODE === "mock" ? "mock" : "api";
}

/**
 * Institution context comes from the selector, not a login — there is no
 * authentication in this build.
 */
async function resolveInstitutionId(
  preferred: string | null | undefined,
  envVar: string | undefined,
  prefer?: (item: Institution) => boolean,
): Promise<string> {
  if (preferred) return preferred;

  const configured = envVar?.trim();
  if (configured) return configured;

  const list = await getInstitutions();
  const addressable = list.institutions.filter(
    (item) => item.type === "school" || item.type === "hospital",
  );
  const match = (prefer && addressable.find(prefer)) ?? addressable[0];

  if (!match) {
    throw new Error("No school/hospital institution is available from GET /institutions.");
  }

  return match.id;
}

// -- Lite -------------------------------------------------------------------

export async function loadLiteOverviewData(institutionId?: string | null) {
  const mode = getDataMode();

  if (mode === "mock") {
    return {
      mode,
      at: mockHealth.clock ?? null,
      health: mockHealth,
      institutions: [mockInstitution] as readonly Institution[],
      institution: mockInstitution,
      forecast: mockForecast,
      alertResponse: mockAlertResponse,
      statusTimeline: mockStatusTimeline,
    } as const;
  }

  // Pin this visitor's own clock before any read, so nobody else's use of the
  // shared server clock can move the dashboard mid-session.
  const [at, health, list] = await Promise.all([
    initialiseClock(),
    getHealth(),
    getInstitutions(),
  ]);

  const resolvedId = await resolveInstitutionId(
    institutionId,
    process.env.NEXT_PUBLIC_HAZE_INSTITUTION_ID,
  );

  const [institution, forecast, alertResponse, statusTimeline] = await Promise.all([
    getInstitution(resolvedId),
    getForecast(resolvedId, LITE_HORIZON_HOURS, at),
    getInstitutionAlert(resolvedId, at),
    getStatusTimeline(resolvedId, at),
  ]);

  return {
    mode,
    at,
    health,
    institutions: list.institutions as readonly Institution[],
    institution,
    forecast,
    alertResponse,
    statusTimeline,
  } as const;
}

export async function loadLiteAlertHistoryData(institutionId?: string | null) {
  return loadLiteOverviewData(institutionId);
}

// -- Pro --------------------------------------------------------------------

export async function loadProLiveMonitorData() {
  const mode = getDataMode();

  if (mode === "mock") {
    return {
      mode,
      at: proMockHealth.clock ?? null,
      health: proMockHealth,
      institutions: proMockInstitutions as readonly Institution[],
      forecasts: proMockForecasts,
      alerts: proMockAlerts,
      hotspotSummary: proMockHotspotSummary,
    } as const;
  }

  const [at, health, institutionList] = await Promise.all([
    initialiseClock(),
    getHealth(),
    getInstitutions(),
  ]);

  const [alertList, hotspotSummary, forecasts] = await Promise.all([
    getAlertsAt(at),
    getHotspotSummary(0.25, at),
    Promise.all(
      institutionList.institutions.map((institution) =>
        getForecast(institution.id, PRO_HORIZON_HOURS, at),
      ),
    ),
  ]);

  return {
    mode,
    at,
    health,
    institutions: institutionList.institutions as readonly Institution[],
    forecasts,
    alerts: alertList.alerts,
    hotspotSummary,
  } as const;
}

export async function loadProInstitutionDetailData(institutionId?: string | null) {
  const mode = getDataMode();

  if (mode === "mock") {
    const institution =
      proMockInstitutions.find((item) => item.country === "MY" && item.type === "school")
      ?? proMockInstitutions[0];
    const forecast =
      proMockForecasts.find((item) => item.institution.id === institution.id)
      ?? proMockForecasts[0];
    const alert = proMockAlerts.find((item) => item.institution_id === institution.id) ?? null;

    return {
      mode,
      at: proMockHealth.clock ?? null,
      health: proMockHealth,
      institutions: proMockInstitutions as readonly Institution[],
      institution,
      forecast,
      alertResponse: {
        institution: forecast.institution,
        status: alert?.status ?? ("resolved" as const),
        alert,
      },
      statusTimeline: mockStatusTimeline,
      hotspotSummary: proMockHotspotSummary,
    } as const;
  }

  const [at, health, institutionList] = await Promise.all([
    initialiseClock(),
    getHealth(),
    getInstitutions(),
  ]);

  const resolvedId = await resolveInstitutionId(
    institutionId,
    process.env.NEXT_PUBLIC_HAZE_PRO_INSTITUTION_ID,
    (item) => item.country === "MY",
  );

  const [institution, forecast, alertResponse, statusTimeline, hotspotSummary] =
    await Promise.all([
      getInstitution(resolvedId),
      getForecast(resolvedId, PRO_HORIZON_HOURS, at),
      getInstitutionAlert(resolvedId, at),
      getStatusTimeline(resolvedId, at),
      getHotspotSummary(0.25, at),
    ]);

  return {
    mode,
    at,
    health,
    institutions: institutionList.institutions as readonly Institution[],
    institution,
    forecast,
    alertResponse,
    statusTimeline,
    hotspotSummary,
  } as const;
}

export async function loadProAlertHistoryData(institutionId?: string | null) {
  const base = await loadProInstitutionDetailData(institutionId);

  if (base.mode === "mock") {
    return { ...base, historyEvents: proMockHistoryEvents } as const;
  }

  // Reconstructed from the sampled timeline: the contract has no alert-history
  // endpoint, so each entry is an observed state at a sampled instant.
  const historyEvents = base.statusTimeline
    .filter((point) => point.alert)
    .map((point) => {
      const alert = point.alert!;
      return {
        id: `${alert.alert_id}-${point.at}`,
        timestamp: point.at,
        status: "alert" as const,
        title: "Forecast alert in effect",
        description:
          `Forecast upper-band peak reached ${alert.forecast_peak_pm25.toFixed(1)} µg/m³ `
          + `with ${alert.lead_time_hours}h warning lead time.`,
        forecastPeak: alert.forecast_peak_pm25,
        sourceArea: alert.source_country ?? undefined,
        notificationState: "prepared" as const,
      };
    });

  return { ...base, historyEvents } as const;
}

export async function loadProNotificationPreviewData(institutionId?: string | null) {
  return loadProInstitutionDetailData(institutionId);
}

// -- Confirm & Send (simulated, local only) ---------------------------------

/**
 * Confirm & Send is **simulated only, and entirely local** in both Lite and Pro.
 *
 * It never calls a write endpoint. The record it returns exists only in React
 * state for the life of the page, so the demo behaves identically with the
 * backend stopped, and no click can mutate shared server state. This is why
 * `apiPost` no longer exists in the client at all.
 */
export function confirmNotification({
  institution,
  channel,
  language,
  previewMessage,
  alertId,
}: {
  institution: Institution;
  channel: Channel;
  language?: string | null;
  previewMessage: string;
  alertId?: string;
}): Notification {
  return createLocalNotification({
    institution,
    channel,
    message: previewMessage,
    language: language ?? institution.languages[0] ?? "en",
    alertId,
  });
}

/** Kept as named aliases so Lite and Pro screens read naturally. */
export const confirmLiteNotification = confirmNotification;
export const confirmProNotification = confirmNotification;

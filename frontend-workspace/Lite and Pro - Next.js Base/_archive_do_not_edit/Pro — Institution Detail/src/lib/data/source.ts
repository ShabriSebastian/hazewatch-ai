import {
  getAlertHistory,
  getAlerts,
  getForecast,
  getHealth,
  getHotspotSummary,
  getInstitution,
  getInstitutionAlert,
  getInstitutions,
  simulateNotification,
} from "@/lib/api/hazewatch";
import type { Channel } from "@/lib/api/types";
import {
  createMockNotification,
  mockAlertHistory,
  mockAlertResponse,
  mockForecast,
  mockHealth,
  mockInstitution,
} from "./mock";
import { mockLiteStatusTimeline } from "./liteHistoryMock";
import {
  proMockAlerts,
  proMockForecasts,
  proMockHealth,
  proMockHotspotSummary,
  proMockInstitutions,
} from "./proMock";

export type DataMode = "api" | "mock";

export function getDataMode(): DataMode {
  return process.env.NEXT_PUBLIC_HAZE_DATA_MODE === "api" ? "api" : "mock";
}

export async function loadLiteOverviewData() {
  const mode = getDataMode();

  if (mode === "mock") {
    return {
      mode,
      health: mockHealth,
      institution: mockInstitution,
      forecast: mockForecast,
      alertResponse: mockAlertResponse,
      alertHistory: mockAlertHistory,
    } as const;
  }

  const configuredId = process.env.NEXT_PUBLIC_HAZE_INSTITUTION_ID?.trim();
  const health = await getHealth();
  let institutionId = configuredId;

  if (!institutionId) {
    const list = await getInstitutions();
    institutionId = list.institutions.find((item) => item.type === "school" || item.type === "hospital")?.id;
  }

  if (!institutionId) {
    throw new Error("No school/hospital institution is available from GET /institutions.");
  }

  const [institution, forecast, alertResponse, alertHistory] = await Promise.all([
    getInstitution(institutionId),
    getForecast(institutionId, 24),
    getInstitutionAlert(institutionId),
    getAlertHistory(institutionId),
  ]);

  return { mode, health, institution, forecast, alertResponse, alertHistory } as const;
}

export async function loadLiteAlertHistoryData() {
  const base = await loadLiteOverviewData();
  return {
    ...base,
    statusTimeline: base.mode === "mock" ? mockLiteStatusTimeline : null,
  } as const;
}

export async function confirmLiteNotification({
  institutionId,
  channel,
  language,
  previewMessage,
}: {
  institutionId: string;
  channel: Channel;
  language?: string | null;
  previewMessage: string;
}) {
  if (getDataMode() === "mock") {
    return createMockNotification(channel, previewMessage, language ?? "ms");
  }

  return simulateNotification(institutionId, channel, language);
}


export async function loadProLiveMonitorData() {
  const mode = getDataMode();

  if (mode === "mock") {
    return {
      mode,
      health: proMockHealth,
      institutions: proMockInstitutions,
      forecasts: proMockForecasts,
      alerts: proMockAlerts,
      hotspotSummary: proMockHotspotSummary,
    } as const;
  }

  const [health, institutionList, alertList, hotspotSummary] = await Promise.all([
    getHealth(),
    getInstitutions(),
    getAlerts("all"),
    getHotspotSummary(0.25),
  ]);

  const forecasts = await Promise.all(
    institutionList.institutions.map((institution) => getForecast(institution.id, 12)),
  );

  return {
    mode,
    health,
    institutions: institutionList.institutions,
    forecasts,
    alerts: alertList.alerts,
    hotspotSummary,
  } as const;
}


export async function loadProInstitutionDetailData() {
  const mode = getDataMode();

  if (mode === "mock") {
    const institution = proMockInstitutions.find((item) => item.country === "MY" && item.type === "school") ?? proMockInstitutions[0];
    const forecast = proMockForecasts.find((item) => item.institution.id === institution.id) ?? proMockForecasts[0];
    const alert = proMockAlerts.find((item) => item.institution_id === institution.id) ?? null;
    const alertHistory = proMockAlerts
      .filter((item) => item.institution_id === institution.id)
      .sort((a, b) => Date.parse(b.triggered_at) - Date.parse(a.triggered_at));

    return {
      mode,
      health: proMockHealth,
      institution,
      forecast,
      alertResponse: {
        institution: forecast.institution,
        status: alert?.status ?? "resolved",
        alert,
      },
      alertHistory,
      hotspotSummary: proMockHotspotSummary,
    } as const;
  }

  const health = await getHealth();
  const configuredId = process.env.NEXT_PUBLIC_HAZE_PRO_INSTITUTION_ID?.trim();
  const institutionList = await getInstitutions();
  const institutionId = configuredId
    ?? institutionList.institutions.find((item) => item.country === "MY" && (item.type === "school" || item.type === "hospital"))?.id
    ?? institutionList.institutions.find((item) => item.type === "school" || item.type === "hospital")?.id;

  if (!institutionId) {
    throw new Error("No school/hospital institution is available for Pro Institution Detail.");
  }

  const [institution, forecast, alertResponse, alertHistory, hotspotSummary] = await Promise.all([
    getInstitution(institutionId),
    getForecast(institutionId, 12),
    getInstitutionAlert(institutionId),
    getAlertHistory(institutionId),
    getHotspotSummary(0.25),
  ]);

  return {
    mode,
    health,
    institution,
    forecast,
    alertResponse,
    alertHistory,
    hotspotSummary,
  } as const;
}

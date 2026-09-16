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

import {
  getAlertHistory,
  getForecast,
  getHealth,
  getInstitution,
  getInstitutionAlert,
  getInstitutions,
} from "@/lib/api/hazewatch";
import {
  mockAlertHistory,
  mockAlertResponse,
  mockForecast,
  mockHealth,
  mockInstitution,
} from "./mock";
import { mockLiteStatusTimeline } from "./liteHistoryMock";

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

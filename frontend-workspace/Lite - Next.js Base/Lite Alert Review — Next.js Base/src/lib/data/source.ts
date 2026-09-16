import {
  getForecast,
  getHealth,
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

export type DataMode = "api" | "mock";

/** The Lite build shows a 24-hour outlook. */
export const LITE_HORIZON_HOURS = 24;

export function getDataMode(): DataMode {
  return process.env.NEXT_PUBLIC_HAZE_DATA_MODE === "mock" ? "mock" : "api";
}

/**
 * Institution context comes from the selector, not a login — there is no
 * authentication in this build. Falls back to the configured id, then to the
 * first school or hospital the API returns.
 */
async function resolveInstitutionId(preferred?: string | null): Promise<string> {
  if (preferred) return preferred;

  const configured = process.env.NEXT_PUBLIC_HAZE_INSTITUTION_ID?.trim();
  if (configured) return configured;

  const list = await getInstitutions();
  const match = list.institutions.find(
    (item) => item.type === "school" || item.type === "hospital",
  );

  if (!match) {
    throw new Error("No school/hospital institution is available from GET /institutions.");
  }

  return match.id;
}

export async function loadLiteOverviewData(institutionId?: string | null) {
  const mode = getDataMode();

  if (mode === "mock") {
    return {
      mode,
      at: mockHealth.clock ?? null,
      health: mockHealth,
      institutions: [mockInstitution],
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

  const resolvedId = await resolveInstitutionId(institutionId);

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
    institutions: list.institutions,
    institution,
    forecast,
    alertResponse,
    statusTimeline,
  } as const;
}

export async function loadLiteAlertHistoryData(institutionId?: string | null) {
  return loadLiteOverviewData(institutionId);
}

/**
 * Confirm & Send is **simulated only, and entirely local**.
 *
 * It never calls a write endpoint. The record it returns exists only in React
 * state for the life of the page, so the demo behaves identically with the
 * backend stopped, and no click can mutate shared server state. This is why
 * `apiPost` no longer exists in the client at all.
 */
export function confirmLiteNotification({
  institution,
  channel,
  language,
  previewMessage,
}: {
  institution: Institution;
  channel: Channel;
  language?: string | null;
  previewMessage: string;
}): Notification {
  return createLocalNotification({
    institution,
    channel,
    message: previewMessage,
    language: language ?? institution.languages[0] ?? "en",
  });
}

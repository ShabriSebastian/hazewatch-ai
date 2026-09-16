import { apiGet, apiPost } from "./client";
import type {
  AlertList,
  AlertStatusResponse,
  Channel,
  Forecast,
  Health,
  HotspotSummary,
  Institution,
  Notification,
  NotificationList,
  SimulateNotificationRequest,
} from "./types";

interface InstitutionListResponse {
  count: number;
  institutions: Institution[];
}

export async function getHealth() {
  return apiGet<Health>("/health");
}

export async function getInstitutions() {
  return apiGet<InstitutionListResponse>("/institutions");
}

export async function getInstitution(id: string) {
  return apiGet<Institution>(`/institutions/${encodeURIComponent(id)}`);
}

export async function getForecast(id: string, horizonHours = 24) {
  return apiGet<Forecast>(
    `/institutions/${encodeURIComponent(id)}/forecast?horizon_hours=${horizonHours}`,
  );
}

export async function getInstitutionAlert(id: string) {
  return apiGet<AlertStatusResponse>(`/institutions/${encodeURIComponent(id)}/alert`);
}

export async function getAlerts(status = "all") {
  return apiGet<AlertList>(`/alerts?status=${encodeURIComponent(status)}`);
}

export async function getHotspotSummary(grid = 0.25) {
  return apiGet<HotspotSummary>(`/hotspots/summary?grid=${grid}`);
}

export async function getAlertHistory(id: string) {
  const response = await apiGet<AlertList>("/alerts?status=all");
  return response.alerts
    .filter((alert) => alert.institution_id === id)
    .sort((a, b) => Date.parse(b.triggered_at) - Date.parse(a.triggered_at));
}

export async function getNotifications(id: string, limit = 50) {
  return apiGet<NotificationList>(
    `/notifications?institution_id=${encodeURIComponent(id)}&limit=${limit}`,
  );
}

export async function simulateNotification(
  institutionId: string,
  channel: Channel = "whatsapp",
  language?: string | null,
) {
  const body: SimulateNotificationRequest = {
    institution_id: institutionId,
    channel,
    language,
  };

  return apiPost<Notification, SimulateNotificationRequest>("/notifications/simulate", body);
}

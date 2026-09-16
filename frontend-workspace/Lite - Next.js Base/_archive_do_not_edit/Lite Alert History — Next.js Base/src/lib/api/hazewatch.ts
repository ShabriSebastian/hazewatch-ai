import { apiGet } from "./client";
import type {
  AlertList,
  AlertStatusResponse,
  Forecast,
  Health,
  Institution,
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

export async function getAlertHistory(id: string) {
  const response = await apiGet<AlertList>("/alerts?status=all");
  return response.alerts
    .filter((alert) => alert.institution_id === id)
    .sort((a, b) => Date.parse(b.triggered_at) - Date.parse(a.triggered_at));
}

// Minimal exact subset of the frozen OpenAPI schemas used by Lite Overview.
// Do not add UI-only fields here. For the full generated contract run: npm run generate:api

export type AqiCategory =
  | "GOOD"
  | "MODERATE"
  | "UNHEALTHY_SENSITIVE"
  | "UNHEALTHY"
  | "VERY_UNHEALTHY"
  | "HAZARDOUS";

export type InstitutionType = "school" | "hospital" | "authority";
export type Role = "source_region" | "affected_region";
export type Channel = "sms" | "whatsapp";
export type Pm25Source = "cams_reanalysis" | "model_forecast" | "ground_station";
export type AlertStatus = "active" | "pending" | "resolved";
export type DeliveryStatus = "queued" | "sent" | "delivered" | "failed";

export interface Institution {
  id: string;
  name: string;
  type: InstitutionType;
  country: string;
  country_name: string;
  admin_region: string;
  city: string;
  lat: number;
  lon: number;
  population_served: number;
  role: Role;
  contact_channels: Channel[];
  languages: string[];
  recipient_group?: string;
}

export interface InstitutionCompact {
  id: string;
  name: string;
  type: InstitutionType;
  country: string;
  city: string;
  lat: number;
  lon: number;
}

export interface Observation {
  timestamp: string;
  pm25: number;
  aqi_category: AqiCategory;
  aqi_us: number;
  source: Pm25Source;
}

export interface ForecastPoint {
  timestamp: string;
  lead_hours: number;
  pm25: number;
  pm25_lower?: number | null;
  pm25_p50?: number | null;
  pm25_upper?: number | null;
  aqi_category: AqiCategory;
  aqi_us: number;
  beyond_training_range?: boolean;
  extrapolation_reason?: "band_saturated" | "feature_out_of_range" | "both" | null;
}

export interface Uncertainty {
  method: string;
  lower_percentile: number;
  upper_percentile: number;
  n_estimators: number;
  training_target_max_pm25: number;
  model_ceiling_pm25?: number | null;
  any_point_beyond_training_range: boolean;
  beyond_training_range_from_lead_hours?: number | null;
  note: string;
}

export interface Attribution {
  upwind_fire_exposure_index: number;
  transboundary: boolean;
  source_country?: string | null;
  dominant_source_region?: string | null;
  estimated_transport_hours?: number | null;
  contributing_hotspot_count?: number;
}

export interface Forecast {
  institution: InstitutionCompact;
  issued_at: string;
  model: { name: string; version: string; horizon_hours: number };
  current: Observation;
  forecast: ForecastPoint[];
  peak: ForecastPoint;
  attribution: Attribution;
  baselines: {
    model_mae?: number | null;
    persistence_mae?: number | null;
    climatology_mae?: number | null;
  };
  uncertainty?: Uncertainty | null;
}

export interface Alert {
  alert_id: string;
  institution_id: string;
  institution_name: string;
  institution_type: InstitutionType;
  country: string;
  severity: AqiCategory;
  status: AlertStatus;
  triggered_at: string;
  forecast_peak_pm25: number;
  forecast_peak_at: string;
  lead_time_hours: number;
  peak_lead_hours?: number | null;
  threshold_pm25: number;
  threshold_crossed_at?: string | null;
  transboundary: boolean;
  source_country?: string | null;
  recommended_actions: string[];
  affected_population: number;
  resolved_at?: string | null;
}

export interface AlertStatusResponse {
  institution: InstitutionCompact;
  status: AlertStatus;
  alert?: Alert | null;
}

export interface AlertList {
  count: number;
  alerts: Alert[];
}

export interface Health {
  status: string;
  mode: string;
  data_version: string;
  model_version: string;
  api_version: string;
  clock?: string | null;
  data_source?: string;
  scenario_id?: string | null;
}

export interface Notification {
  notification_id: string;
  alert_id: string;
  institution_id: string;
  institution_name: string;
  country: string;
  channel: Channel;
  recipient_group: string;
  recipient_count: number;
  language: string;
  sent_at: string;
  status: DeliveryStatus;
  message: string;
  simulated?: boolean;
}

export interface NotificationList {
  count: number;
  notifications: Notification[];
}

export interface SimulateNotificationRequest {
  institution_id: string;
  channel?: Channel;
  language?: string | null;
}

export interface HotspotGridCell {
  lat: number;
  lon: number;
  count: number;
  frp_sum: number;
}

export interface HotspotSummary {
  query: {
    start: string;
    end: string;
    bbox: number[];
    min_frp?: number | null;
  };
  grid: number;
  count: number;
  cells: HotspotGridCell[];
}

import type { StatusTimelinePoint } from "@/lib/api/hazewatch";
import type {
  Alert,
  AlertStatusResponse,
  Channel,
  Forecast,
  Health,
  Institution,
  Notification,
} from "@/lib/api/types";

export const mockHealth: Health = {
  status: "ok",
  mode: "replay",
  data_version: "demo-crossborder",
  model_version: "rf-demo",
  api_version: "1.0.0",
  data_source: "scenario_db",
  clock: "2023-09-02T16:00:00Z",
  scenario_id: "crossborder-demo",
};

export const mockInstitution: Institution = {
  id: "my-kuching-school-demo",
  name: "Kuching International Secondary School",
  type: "school",
  country: "MY",
  country_name: "Malaysia",
  admin_region: "Sarawak",
  city: "Kuching",
  lat: 1.5533,
  lon: 110.3592,
  population_served: 920,
  role: "affected_region",
  contact_channels: ["whatsapp", "sms"],
  languages: ["ms", "en"],
  recipient_group: "verified-admin-contact",
};

export const mockForecast: Forecast = {
  institution: {
    id: mockInstitution.id,
    name: mockInstitution.name,
    type: mockInstitution.type,
    country: mockInstitution.country,
    city: mockInstitution.city,
    lat: mockInstitution.lat,
    lon: mockInstitution.lon,
  },
  issued_at: "2023-09-02T16:00:00Z",
  model: { name: "random-forest", version: "demo", horizon_hours: 24 },
  current: {
    timestamp: "2023-09-02T16:00:00Z",
    pm25: 9,
    aqi_category: "GOOD",
    aqi_us: 37,
    source: "cams_reanalysis",
  },
  forecast: [
    {
      timestamp: "2023-09-02T22:00:00Z",
      lead_hours: 6,
      pm25: 23,
      pm25_lower: 16,
      pm25_p50: 22,
      pm25_upper: 31,
      aqi_category: "MODERATE",
      aqi_us: 74,
      beyond_training_range: false,
    },
    {
      timestamp: "2023-09-03T04:00:00Z",
      lead_hours: 12,
      pm25: 34,
      pm25_lower: 26,
      pm25_p50: 33,
      pm25_upper: 42,
      aqi_category: "MODERATE",
      aqi_us: 96,
      beyond_training_range: true,
      extrapolation_reason: "feature_out_of_range",
    },
    {
      timestamp: "2023-09-03T10:00:00Z",
      lead_hours: 18,
      pm25: 42,
      pm25_lower: 34,
      pm25_p50: 41,
      pm25_upper: 49,
      aqi_category: "UNHEALTHY_SENSITIVE",
      aqi_us: 116,
      beyond_training_range: true,
      extrapolation_reason: "feature_out_of_range",
    },
    {
      timestamp: "2023-09-03T16:00:00Z",
      lead_hours: 24,
      pm25: 36,
      pm25_lower: 28,
      pm25_p50: 35,
      pm25_upper: 45,
      aqi_category: "UNHEALTHY_SENSITIVE",
      aqi_us: 105,
      beyond_training_range: true,
      extrapolation_reason: "feature_out_of_range",
    }
  ],
  peak: {
    timestamp: "2023-09-03T10:00:00Z",
    lead_hours: 18,
    pm25: 42,
    pm25_lower: 34,
    pm25_p50: 41,
    pm25_upper: 49,
    aqi_category: "UNHEALTHY_SENSITIVE",
    aqi_us: 116,
    beyond_training_range: true,
    extrapolation_reason: "feature_out_of_range",
  },
  attribution: {
    upwind_fire_exposure_index: 0.83,
    transboundary: true,
    source_country: "ID",
    dominant_source_region: "West Kalimantan, Indonesia",
    estimated_transport_hours: 18,
    contributing_hotspot_count: 486,
  },
  baselines: {},
  uncertainty: {
    method: "random_forest_tree_quantiles",
    lower_percentile: 10,
    upper_percentile: 90,
    n_estimators: 300,
    training_target_max_pm25: 112.9,
    model_ceiling_pm25: 90.1,
    any_point_beyond_training_range: true,
    beyond_training_range_from_lead_hours: 12,
    note: "From +12h this forecast uses conditions outside the model's usual training range.",
  },
};

export const mockAlert: Alert = {
  alert_id: "alert-kuching-demo",
  institution_id: mockInstitution.id,
  institution_name: mockInstitution.name,
  institution_type: "school",
  country: "MY",
  severity: "UNHEALTHY_SENSITIVE",
  status: "active",
  triggered_at: "2023-09-02T16:00:00Z",
  forecast_peak_pm25: 49,
  forecast_peak_at: "2023-09-03T10:00:00Z",
  lead_time_hours: 18,
  peak_lead_hours: 18,
  threshold_pm25: 35.5,
  threshold_crossed_at: "2023-09-03T10:00:00Z",
  transboundary: true,
  source_country: "ID",
  recommended_actions: [
    "Move outdoor activities indoors",
    "Prepare indoor spaces",
    "Inform relevant school staff",
    "Review closure guidance if conditions worsen",
  ],
  affected_population: 920,
};

export const mockAlertResponse: AlertStatusResponse = {
  institution: mockForecast.institution,
  status: "active",
  alert: mockAlert,
};

/**
 * Offline stand-in for the reconstructed timeline. Same shape the API path
 * produces, so the screen cannot tell the two apart.
 */
export const mockStatusTimeline: StatusTimelinePoint[] = [
  { at: "2023-09-02T16:00:00Z", alert: mockAlert },
  { at: "2023-09-02T04:00:00Z", alert: null },
];

/**
 * Builds the record shown after Confirm & Send. Purely local — nothing is sent,
 * and `simulated` is always true, which the UI is required to surface.
 */
export function createLocalNotification({
  institution,
  channel,
  message,
  language,
  alertId,
}: {
  institution: Institution;
  channel: Channel;
  message: string;
  language: string;
  alertId?: string;
}): Notification {
  const sentAt = new Date().toISOString();

  return {
    notification_id: `local-${Date.parse(sentAt)}`,
    alert_id: alertId ?? mockAlert.alert_id,
    institution_id: institution.id,
    institution_name: institution.name,
    country: institution.country,
    channel,
    recipient_group: institution.recipient_group ?? "verified-admin-contact",
    recipient_count: 1,
    language,
    sent_at: sentAt,
    status: "sent",
    message,
    simulated: true,
  };
}

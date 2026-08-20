import type { Alert, Forecast, Health, HotspotSummary, Institution } from "@/lib/api/types";

export const proMockHealth: Health = {
  status: "ok",
  mode: "replay",
  data_version: "demo-crossborder",
  model_version: "rf-demo",
  api_version: "1.0.0",
  data_source: "scenario_db",
  clock: "2023-09-02T16:00:00Z",
  scenario_id: "crossborder-demo",
};

export const proMockInstitutions: Institution[] = [
  {
    id: "id-ptk-sman1",
    name: "SMA Negeri 1 Pontianak",
    type: "school",
    country: "ID",
    country_name: "Indonesia",
    admin_region: "West Kalimantan",
    city: "Pontianak",
    lat: -0.0263,
    lon: 109.3425,
    population_served: 1180,
    role: "source_region",
    contact_channels: ["whatsapp", "sms"],
    languages: ["id"],
    recipient_group: "verified-admin-contact",
  },
  {
    id: "id-ptk-hospital",
    name: "Pontianak General Hospital",
    type: "hospital",
    country: "ID",
    country_name: "Indonesia",
    admin_region: "West Kalimantan",
    city: "Pontianak",
    lat: -0.045,
    lon: 109.325,
    population_served: 520,
    role: "source_region",
    contact_channels: ["whatsapp", "sms"],
    languages: ["id"],
    recipient_group: "verified-admin-contact",
  },
  {
    id: "id-sintang-hospital",
    name: "Sintang Hospital",
    type: "hospital",
    country: "ID",
    country_name: "Indonesia",
    admin_region: "West Kalimantan",
    city: "Sintang",
    lat: 0.078,
    lon: 111.495,
    population_served: 410,
    role: "source_region",
    contact_channels: ["whatsapp", "sms"],
    languages: ["id"],
    recipient_group: "verified-admin-contact",
  },
  {
    id: "my-kch-school",
    name: "Kuching High School",
    type: "school",
    country: "MY",
    country_name: "Malaysia",
    admin_region: "Sarawak",
    city: "Kuching",
    lat: 1.5533,
    lon: 110.3592,
    population_served: 940,
    role: "affected_region",
    contact_channels: ["whatsapp", "sms"],
    languages: ["ms", "en"],
    recipient_group: "verified-admin-contact",
  },
  {
    id: "my-kch-hospital",
    name: "Kuching General Hospital",
    type: "hospital",
    country: "MY",
    country_name: "Malaysia",
    admin_region: "Sarawak",
    city: "Kuching",
    lat: 1.543,
    lon: 110.341,
    population_served: 760,
    role: "affected_region",
    contact_channels: ["whatsapp", "sms"],
    languages: ["ms", "en"],
    recipient_group: "verified-admin-contact",
  },
  {
    id: "my-sibu-hospital",
    name: "Sibu Hospital",
    type: "hospital",
    country: "MY",
    country_name: "Malaysia",
    admin_region: "Sarawak",
    city: "Sibu",
    lat: 2.2873,
    lon: 111.8305,
    population_served: 610,
    role: "affected_region",
    contact_channels: ["whatsapp", "sms"],
    languages: ["ms", "en"],
    recipient_group: "verified-admin-contact",
  },
];

const forecastShape = [
  { lead_hours: 1, pm25: 24, pm25_lower: 18, pm25_p50: 23, pm25_upper: 31 },
  { lead_hours: 3, pm25: 30, pm25_lower: 22, pm25_p50: 29, pm25_upper: 39 },
  { lead_hours: 6, pm25: 39, pm25_lower: 30, pm25_p50: 38, pm25_upper: 49 },
  { lead_hours: 9, pm25: 46, pm25_lower: 35, pm25_p50: 44, pm25_upper: 57.7 },
  { lead_hours: 12, pm25: 42, pm25_lower: 33, pm25_p50: 41, pm25_upper: 53 },
];

function category(v: number): Forecast["peak"]["aqi_category"] {
  if (v <= 12) return "GOOD";
  if (v <= 35.4) return "MODERATE";
  if (v <= 55.4) return "UNHEALTHY_SENSITIVE";
  return "UNHEALTHY";
}

function makeForecast(institution: Institution, scale = 1, sourceRegion?: string): Forecast {
  const issued = new Date("2023-09-02T16:00:00Z");
  const points = forecastShape.map((point) => {
    const pm25 = +(point.pm25 * scale).toFixed(1);
    const lower = +(point.pm25_lower * scale).toFixed(1);
    const p50 = +(point.pm25_p50 * scale).toFixed(1);
    const upper = +(point.pm25_upper * scale).toFixed(1);
    return {
      timestamp: new Date(issued.getTime() + point.lead_hours * 3600000).toISOString(),
      lead_hours: point.lead_hours,
      pm25,
      pm25_lower: lower,
      pm25_p50: p50,
      pm25_upper: upper,
      aqi_category: category(pm25),
      aqi_us: Math.round(pm25 * 2.1),
      beyond_training_range: false,
      extrapolation_reason: null,
    };
  });
  const peak = points.reduce((a, b) => ((a.pm25_upper ?? a.pm25) > (b.pm25_upper ?? b.pm25) ? a : b));
  const currentPm25 = institution.country === "MY" ? 13 : institution.type === "school" ? 22 : 20;
  return {
    institution: {
      id: institution.id,
      name: institution.name,
      type: institution.type,
      country: institution.country,
      city: institution.city,
      lat: institution.lat,
      lon: institution.lon,
    },
    issued_at: issued.toISOString(),
    model: { name: "random-forest", version: "demo", horizon_hours: 12 },
    current: {
      timestamp: issued.toISOString(),
      pm25: currentPm25,
      aqi_category: category(currentPm25),
      aqi_us: Math.round(currentPm25 * 2.1),
      source: "cams_reanalysis",
    },
    forecast: points,
    peak,
    attribution: {
      upwind_fire_exposure_index: institution.country === "MY" ? 0.83 : 0.65,
      transboundary: institution.country === "MY",
      source_country: institution.country === "MY" ? "ID" : "ID",
      dominant_source_region: sourceRegion ?? "West Kalimantan, Indonesia",
      estimated_transport_hours: institution.country === "MY" ? 18 : 6,
      contributing_hotspot_count: 24,
    },
    baselines: {},
    uncertainty: {
      method: "random_forest_tree_quantiles",
      lower_percentile: 10,
      upper_percentile: 90,
      n_estimators: 300,
      training_target_max_pm25: 112.9,
      model_ceiling_pm25: 90.1,
      any_point_beyond_training_range: false,
      beyond_training_range_from_lead_hours: null,
      note: "Forecast remains within the model's trained range.",
    },
  };
}

export const proMockForecasts: Forecast[] = [
  makeForecast(proMockInstitutions[0], 0.82),
  makeForecast(proMockInstitutions[1], 0.91),
  makeForecast(proMockInstitutions[2], 0.74),
  makeForecast(proMockInstitutions[3], 1),
  makeForecast(proMockInstitutions[4], 0.95),
  makeForecast(proMockInstitutions[5], 0.72),
];

export const proMockAlerts: Alert[] = proMockForecasts
  .filter((forecast) => (forecast.peak.pm25_upper ?? forecast.peak.pm25) >= 35.5)
  .map((forecast, index) => ({
    alert_id: `pro-alert-${index + 1}`,
    institution_id: forecast.institution.id,
    institution_name: forecast.institution.name,
    institution_type: forecast.institution.type,
    country: forecast.institution.country,
    severity: (forecast.peak.pm25_upper ?? forecast.peak.pm25) > 55.4 ? "UNHEALTHY" : "UNHEALTHY_SENSITIVE",
    status: "active",
    triggered_at: "2023-09-02T16:00:00Z",
    forecast_peak_pm25: forecast.peak.pm25_upper ?? forecast.peak.pm25,
    forecast_peak_at: forecast.peak.timestamp,
    lead_time_hours: forecast.institution.country === "MY" ? 18 : 9,
    peak_lead_hours: forecast.peak.lead_hours,
    threshold_pm25: 35.5,
    threshold_crossed_at: forecast.forecast.find((p) => (p.pm25_upper ?? p.pm25) >= 35.5)?.timestamp ?? null,
    transboundary: forecast.attribution.transboundary,
    source_country: forecast.attribution.source_country,
    recommended_actions: forecast.institution.type === "hospital"
      ? ["Review indoor filtration readiness", "Prepare respiratory-care capacity", "Inform relevant hospital staff"]
      : ["Move outdoor activities indoors", "Prepare indoor spaces", "Inform relevant school staff"],
    affected_population: proMockInstitutions.find((i) => i.id === forecast.institution.id)?.population_served ?? 0,
  }));

export const proMockHotspotSummary: HotspotSummary = {
  query: {
    start: "2023-09-01T16:00:00Z",
    end: "2023-09-02T16:00:00Z",
    bbox: [108.4, -1.1, 113.3, 3.3],
    min_frp: null,
  },
  grid: 0.25,
  count: 24,
  cells: [
    { lat: -0.12, lon: 108.95, count: 3, frp_sum: 88 },
    { lat: 0.12, lon: 109.25, count: 4, frp_sum: 105 },
    { lat: -0.35, lon: 109.5, count: 2, frp_sum: 62 },
    { lat: 0.65, lon: 109.1, count: 5, frp_sum: 140 },
    { lat: 0.35, lon: 109.85, count: 3, frp_sum: 91 },
    { lat: -0.62, lon: 110.05, count: 4, frp_sum: 117 },
    { lat: 0.88, lon: 110.2, count: 3, frp_sum: 74 },
  ],
};

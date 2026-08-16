import type { Attribution, Forecast, Institution } from "@/lib/api/types";

/** Institutions sit in West Kalimantan (WIB) or Sarawak (MYT). */
function timeZoneFor(country: string) {
  return country === "ID" ? "Asia/Pontianak" : "Asia/Kuching";
}

export function localTime(iso: string, country: string) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: timeZoneFor(country),
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

/**
 * A standalone instant, with its date.
 *
 * Bare HH:MM reads as "now" while the replay clock sits a day away. On Lite
 * Overview at the opening bookmark three different instants all render as
 * "23:00": the replay clock (2 Sep), the forecast peak the banner points at
 * (3 Sep, a full day out) and the oldest sampled alert (1 Sep).
 *
 * Formatted to match the Pro screens - `03 Sept 23:00` - so one timestamp does
 * not look like two different things across the two modes. `localDayLabel` keeps
 * its weekday form: it heads day *groups* in Alert History, a different job.
 *
 * Not for times that already sit under a date, and not for `peakTime`, which
 * also feeds the recipient-facing message body.
 */
export function localStamp(iso: string, country: string) {
  const day = new Intl.DateTimeFormat("en-GB", {
    timeZone: timeZoneFor(country),
    day: "2-digit",
    month: "short",
  }).format(new Date(iso));
  return `${day} ${localTime(iso, country)}`;
}

export function localDayKey(iso: string, country: string) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: timeZoneFor(country),
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(iso));
}

export function localDayLabel(iso: string, country: string) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: timeZoneFor(country),
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(new Date(iso));
}

export function formatLocation(institution: Institution) {
  return [institution.city, institution.admin_region, institution.country_name]
    .filter(Boolean)
    .join(", ");
}

/**
 * The contract gives a single instant for the peak (`forecast_peak_at` /
 * `peak.timestamp`), not a range. Earlier drafts rendered it as peak +/- 1 hour,
 * which invented a window the model never produced.
 */
export function peakTime(iso: string, country: string) {
  return localTime(iso, country);
}

/**
 * The transboundary claim, in one sentence. Returns null when the smoke is
 * local, so callers can render nothing rather than an empty qualifier.
 */
export function attributionLine(attribution: Attribution): string | null {
  if (!attribution.transboundary || !attribution.dominant_source_region) return null;

  const hours = attribution.estimated_transport_hours;
  const transport = typeof hours === "number" ? ` — about ${hours}h downwind transport` : "";

  return `Smoke is arriving from ${attribution.dominant_source_region}${transport}.`;
}

/**
 * `uncertainty.note` is written by the backend to be shown to a user as-is.
 * Falls back to a plain-language sentence when the server is on fixtures or an
 * older scenario database, where `uncertainty` is null.
 */
export const RELIABILITY_FALLBACK =
  "This forecast may be less reliable than usual because conditions are outside the range commonly seen during model training.";

export function reliabilityNote(forecast: Forecast): string | null {
  const uncertainty = forecast.uncertainty;
  if (!uncertainty?.any_point_beyond_training_range) return null;
  return uncertainty.note || RELIABILITY_FALLBACK;
}

/**
 * The scheduled live snapshot.
 *
 * This is deliberately NOT part of the API client. The backend serves the
 * validated Sept 2023 replay and knows nothing about live data - it cannot
 * fetch it even by accident. The snapshot is produced out-of-band by
 * `make refresh` and published as a static JSON file, which this module reads
 * directly from the browser.
 *
 * Consequences worth understanding before changing anything here:
 *
 *   - A failed refresh simply does not publish. The previous file stays at the
 *     same URL, so the fallback is the *absence* of an action rather than a
 *     code path that has to work correctly under failure.
 *   - Nothing here is on the critical path for the dashboard. If this fetch
 *     fails for any reason the panel hides itself and every other panel,
 *     including all of replay mode, is unaffected.
 *   - The refresh is MANUAL. There is no scheduler - a cron on GitHub Actions
 *     was tried and abandoned, because runners cannot reach NASA FIRMS
 *     reliably. So the age of a snapshot depends entirely on when someone last
 *     ran the command, which is why `generated_at` is surfaced prominently and
 *     `isStale` exists.
 *   - The forecast inside is issued for `now - 12h`. It is never continuously
 *     live, and the UI must not imply that it is.
 */

/** Hours after which a snapshot is shown but visibly flagged as stale. */
export const STALE_AFTER_HOURS = 6;

export interface SnapshotForecastPoint {
  timestamp: string;
  lead_hours: number;
  pm25: number;
  pm25_lower: number | null;
  pm25_upper: number | null;
  pm25_p50: number | null;
  beyond_training_range: boolean;
  extrapolation_reason: string | null;
  aqi_category: string;
  aqi_us: number;
}

export interface SnapshotInstitution {
  institution_id: string;
  institution_name: string;
  institution_type: string;
  country: string;
  city: string;
  observed_pm25: number;
  observed_category: string;
  forecast: SnapshotForecastPoint[];
  peak: SnapshotForecastPoint;
  alert: { lead_time_hours: number; forecast_peak_pm25: number; severity: string } | null;
  out_of_range_features: string[];
}

export interface LiveSnapshot {
  data_source: string;
  generated_at: string;
  issued_at: string;
  issued_offset_hours: number;
  alert_threshold_pm25: number;
  institutions: SnapshotInstitution[];
  provenance?: {
    hotspots?: { rows_after_dedup?: number; latest_detection_utc?: string };
    limitations?: string[];
  };
}

function snapshotUrl(): string | null {
  const url = process.env.NEXT_PUBLIC_HAZE_SNAPSHOT_URL?.trim();
  return url ? url : null;
}

/**
 * Minimal shape check. The publishing job gates far more thoroughly, but a file
 * served from a CDN can be truncated or replaced, and rendering half a snapshot
 * as though it were whole would be worse than rendering nothing.
 */
function looksValid(value: unknown): value is LiveSnapshot {
  if (!value || typeof value !== "object") return false;
  const s = value as Partial<LiveSnapshot>;
  if (typeof s.generated_at !== "string" || typeof s.issued_at !== "string") return false;
  if (!Array.isArray(s.institutions) || s.institutions.length === 0) return false;
  return s.institutions.every(
    (i) =>
      typeof i?.institution_id === "string"
      && typeof i?.observed_pm25 === "number"
      && Number.isFinite(i.observed_pm25)
      && Array.isArray(i?.forecast)
      && i.forecast.length > 0,
  );
}

/**
 * Returns the snapshot, or null. Never throws, and never rejects: every failure
 * mode - unset URL, network error, 404, malformed JSON, truncated file - is the
 * same outcome for the caller, which is to render nothing.
 */
export async function fetchSnapshot(): Promise<LiveSnapshot | null> {
  const url = snapshotUrl();
  if (!url) return null;

  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return null;
    const parsed: unknown = await response.json();
    return looksValid(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function ageHours(generatedAt: string, now: Date = new Date()): number | null {
  const t = Date.parse(generatedAt);
  if (Number.isNaN(t)) return null;
  return (now.getTime() - t) / 3_600_000;
}

export function isStale(generatedAt: string, now?: Date): boolean {
  const age = ageHours(generatedAt, now);
  return age === null || age > STALE_AFTER_HOURS;
}

/** "14 Aug 07:22 UTC" - always UTC, so the label cannot be misread locally. */
export function formatUtc(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d) + " UTC";
}

export function describeAge(generatedAt: string, now?: Date): string {
  const age = ageHours(generatedAt, now);
  if (age === null) return "age unknown";
  if (age < 1) return `${Math.max(1, Math.round(age * 60))} min ago`;
  if (age < 24) return `${Math.round(age)} h ago`;
  return `${Math.floor(age / 24)} d ago`;
}

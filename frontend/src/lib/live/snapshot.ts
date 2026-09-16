/**
 * The published live snapshot — now the dashboard's only data source.
 *
 * This file used to feed one below-fold panel while a FastAPI service replayed
 * a recorded September 2023 event behind the rest of the app. The replay is
 * retired; `data/live/latest.json` drives every screen.
 *
 * Things that have not changed, and must not:
 *
 *   - The refresh is MANUAL. There is no scheduler; GitHub-hosted runners
 *     cannot reach NASA FIRMS reliably (see DEVELOPMENT.md). The age of a
 *     snapshot depends entirely on when someone last ran `make refresh`, which
 *     is why `generated_at` is surfaced prominently and `isStale` exists.
 *   - The forecast inside is issued for `now - issued_offset_hours`, because
 *     the trailing hours of the satellite fire field are only partly
 *     populated. It is never continuously live, and the UI must not imply it.
 *
 * What HAS changed: failure is no longer silent. `fetchSnapshot` used to
 * collapse every failure to `null`, which was right when a missing panel meant
 * one card did not render. Now a missing snapshot means the app has no data at
 * all, so the reason is returned and every screen renders it explicitly.
 */

import type {
  Alert,
  AlertStatusResponse,
  Attribution,
  Forecast,
  ForecastPoint,
  Health,
  HotspotSummary,
  Institution,
  Observation,
  Uncertainty,
} from "@/lib/api/types";

/** Hours after which a snapshot is shown but visibly flagged as stale. */
export const STALE_AFTER_HOURS = 6;

export interface SnapshotForecastPoint extends ForecastPoint {
  beyond_training_range: boolean;
  extrapolation_reason: "band_saturated" | "feature_out_of_range" | "both" | null;
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
  alert: Alert | null;
  out_of_range_features: string[];
  /** The full institution record; `/institutions` is retired. */
  institution: Institution;
  model: { name: string; version: string; horizon_hours: number };
  current: Observation;
  attribution: Attribution;
  baselines: {
    model_mae?: number | null;
    persistence_mae?: number | null;
    climatology_mae?: number | null;
  };
  uncertainty: Uncertainty;
}

export interface LiveSnapshot {
  data_source: string;
  generated_at: string;
  issued_at: string;
  issued_offset_hours: number;
  model_version: string;
  alert_threshold_pm25: number;
  alert_trigger_percentile?: number;
  institutions: SnapshotInstitution[];
  hotspots: {
    grid: number;
    bbox: number[];
    count: number;
    cells: HotspotSummary["cells"];
  };
  provenance?: {
    hotspots?: { rows_after_dedup?: number; latest_detection_utc?: string };
    weather?: Record<string, unknown>;
    pm25?: Record<string, unknown>;
    limitations?: string[];
  };
}

/**
 * Why the app has no data. Distinguished because the remedies differ and the
 * user-facing copy differs: an unconfigured URL is a deployment mistake, an
 * unreachable file is usually transient, and a malformed one means the publish
 * gate let something through.
 */
export type SnapshotFailure = "unconfigured" | "unreachable" | "malformed";

export type SnapshotResult =
  | { ok: true; snapshot: LiveSnapshot }
  | { ok: false; reason: SnapshotFailure };

function snapshotUrl(): string | null {
  const url = process.env.NEXT_PUBLIC_HAZE_SNAPSHOT_URL?.trim();
  return url ? url : null;
}

/**
 * Shape check. The publishing gate (`scripts/08_gate_snapshot.py`) checks far
 * more thoroughly, but a file served from a CDN can be truncated or replaced,
 * and rendering half a snapshot as though it were whole would be worse than
 * rendering an error.
 *
 * This is stricter than it was: the blocks the main body needs are now
 * required, because a snapshot without them cannot drive the app at all.
 */
function looksValid(value: unknown): value is LiveSnapshot {
  if (!value || typeof value !== "object") return false;
  const s = value as Partial<LiveSnapshot>;
  if (typeof s.generated_at !== "string" || typeof s.issued_at !== "string") return false;
  if (!Array.isArray(s.institutions) || s.institutions.length === 0) return false;
  if (!s.hotspots || !Array.isArray(s.hotspots.cells)) return false;

  return s.institutions.every(
    (i) =>
      typeof i?.institution_id === "string"
      && typeof i?.observed_pm25 === "number"
      && Number.isFinite(i.observed_pm25)
      && Array.isArray(i?.forecast)
      && i.forecast.length > 0
      && !!i?.institution
      && typeof i.institution.lat === "number"
      && typeof i.institution.lon === "number"
      && !!i?.current
      && !!i?.attribution
      && !!i?.uncertainty,
  );
}

let cached: Promise<SnapshotResult> | null = null;

async function load(): Promise<SnapshotResult> {
  const url = snapshotUrl();
  if (!url) return { ok: false, reason: "unconfigured" };

  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return { ok: false, reason: "unreachable" };
    const parsed: unknown = await response.json();
    if (!looksValid(parsed)) return { ok: false, reason: "malformed" };
    return { ok: true, snapshot: parsed };
  } catch {
    return { ok: false, reason: "unreachable" };
  }
}

/**
 * Fetched once per browser session and shared by every screen. The file is one
 * request for the whole dashboard, where the API needed eleven to fourteen per
 * page, so there is no reason for each screen to fetch its own copy.
 */
export function fetchSnapshot(): Promise<SnapshotResult> {
  cached ??= load().then((result) => {
    // A failure is not memoised: navigating between screens should get another
    // chance at a transient network problem.
    if (!result.ok) cached = null;
    return result;
  });
  return cached;
}

/** Testing and manual-refresh affordance; not used by the render path. */
export function resetSnapshotCache() {
  cached = null;
}

export class SnapshotUnavailable extends Error {
  constructor(public readonly reason: SnapshotFailure) {
    super(describeFailure(reason));
    this.name = "SnapshotUnavailable";
  }
}

export function describeFailure(reason: SnapshotFailure): string {
  if (reason === "unconfigured") {
    return "No snapshot source is configured. NEXT_PUBLIC_HAZE_SNAPSHOT_URL is unset in this deployment.";
  }
  if (reason === "malformed") {
    return "The published snapshot could not be read. It is missing fields this dashboard requires, so nothing is shown rather than showing part of it.";
  }
  return "The published snapshot could not be reached. This is usually temporary — the previously published file stays in place, so retrying often succeeds.";
}

// -- adapters ---------------------------------------------------------------
// The snapshot mirrors the retired forecast response, so these are re-shapings
// rather than conversions. They exist so screens keep consuming the same types.

export function toForecast(record: SnapshotInstitution): Forecast {
  return {
    institution: record.institution,
    issued_at: record.current.timestamp,
    model: record.model,
    current: record.current,
    forecast: record.forecast,
    peak: record.peak,
    attribution: record.attribution,
    baselines: record.baselines,
    uncertainty: record.uncertainty,
  };
}

export function toAlertResponse(record: SnapshotInstitution): AlertStatusResponse {
  return {
    institution: record.institution,
    status: record.alert ? "active" : "resolved",
    alert: record.alert,
  };
}

export function toInstitutions(snapshot: LiveSnapshot): Institution[] {
  return snapshot.institutions.map((i) => i.institution);
}

export function toHotspotSummary(snapshot: LiveSnapshot): HotspotSummary {
  return {
    query: {
      start: snapshot.issued_at,
      end: snapshot.generated_at,
      bbox: snapshot.hotspots.bbox,
      min_frp: null,
    },
    grid: snapshot.hotspots.grid,
    count: snapshot.hotspots.count,
    cells: snapshot.hotspots.cells,
  };
}

/**
 * Synthesised, not fetched. `/health` is retired; the fields the shell actually
 * renders are all carried by the snapshot itself.
 */
export function toHealth(snapshot: LiveSnapshot): Health {
  return {
    status: "ok",
    mode: "live",
    data_version: snapshot.generated_at,
    model_version: snapshot.model_version,
    api_version: "static-snapshot",
    clock: snapshot.issued_at,
    data_source: snapshot.data_source,
    scenario_id: null,
  };
}

export function findInstitution(
  snapshot: LiveSnapshot,
  institutionId?: string | null,
): SnapshotInstitution | undefined {
  if (institutionId) {
    const match = snapshot.institutions.find((i) => i.institution_id === institutionId);
    if (match) return match;
  }
  return undefined;
}

// -- age / staleness --------------------------------------------------------

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
  if (age < 48) return `${Math.round(age)}h ago`;
  return `${Math.round(age / 24)} days ago`;
}

/**
 * The accumulated alert history.
 *
 * Alert History used to be assembled by asking the replay backend for `/alerts`
 * at seven past timestamps — possible only because a replay clock can be wound
 * backwards. Live data has no past to query, so history is accumulated instead:
 * `scripts/09_append_history.py` appends one compact record per published
 * snapshot (see DEVELOPMENT.md).
 *
 * **This is a sparse, irregular list, and the UI must treat it as one.**
 * Refreshes are manual. Two records may be twenty minutes apart or three weeks
 * apart, and the gap between them is not "no alert" — it is "nobody looked".
 * Nothing here interpolates or resamples, and `gapHours` exists so screens can
 * show the intervals rather than implying a continuous record.
 */

import type { Alert } from "@/lib/api/types";
import type { StatusTimelinePoint } from "@/lib/ui/timeline";

/** Trimmed alert as stored in the history file. */
export type HistoryAlert = Pick<
  Alert,
  | "alert_id"
  | "severity"
  | "status"
  | "triggered_at"
  | "forecast_peak_pm25"
  | "forecast_peak_at"
  | "lead_time_hours"
  | "threshold_pm25"
  | "transboundary"
  | "source_country"
> &
  Partial<Alert>;

export interface HistoryInstitutionState {
  observed_pm25: number | null;
  observed_category: string | null;
  peak_pm25_upper: number | null;
  peak_at: string | null;
  beyond_training_range: boolean;
  alert: HistoryAlert | null;
}

export interface HistoryRecord {
  generated_at: string;
  issued_at: string;
  issued_offset_hours?: number | null;
  model_version?: string;
  institutions: Record<string, HistoryInstitutionState>;
}

export interface AlertHistory {
  schema: number;
  max_records: number;
  records: HistoryRecord[];
}

function historyUrl(): string | null {
  const explicit = process.env.NEXT_PUBLIC_HAZE_HISTORY_URL?.trim();
  if (explicit) return explicit;

  // Derived from the snapshot URL rather than configured separately: the two
  // files are written by the same commit and always sit side by side.
  const snapshot = process.env.NEXT_PUBLIC_HAZE_SNAPSHOT_URL?.trim();
  if (!snapshot) return null;
  return snapshot.replace(/latest\.json(\?.*)?$/, "history.json$1")
      .replace(/dev-snapshot\.json(\?.*)?$/, "dev-history.json$1");
}

function looksValid(value: unknown): value is AlertHistory {
  if (!value || typeof value !== "object") return false;
  const h = value as Partial<AlertHistory>;
  if (!Array.isArray(h.records)) return false;
  return h.records.every(
    (r) => typeof r?.generated_at === "string" && !!r?.institutions,
  );
}

let cached: Promise<AlertHistory | null> | null = null;

/**
 * Returns the history, or null.
 *
 * Unlike the snapshot, a missing history is **not** a failure worth blocking
 * on: the current snapshot alone still describes the present, which is what
 * most screens need. Alert History says explicitly that it has only one
 * observation rather than refusing to render.
 */
export function fetchHistory(): Promise<AlertHistory | null> {
  cached ??= (async () => {
    const url = historyUrl();
    if (!url) return null;
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) return null;
      const parsed: unknown = await response.json();
      return looksValid(parsed) ? parsed : null;
    } catch {
      return null;
    }
  })().then((result) => {
    if (!result) cached = null;
    return result;
  });
  return cached;
}

export function resetHistoryCache() {
  cached = null;
}

/** One recorded observation, with the interval back to the previous one. */
export interface RecordedPoint extends StatusTimelinePoint {
  /** Hours since the previous (older) record. Null for the oldest. */
  gapHours: number | null;
  observedPm25: number | null;
  peakPm25Upper: number | null;
  beyondTrainingRange: boolean;
}

/**
 * The recorded states for one institution, newest first.
 *
 * `current` is folded in so the screen always reflects the snapshot on display,
 * even when it has not been appended to the history yet — which is the normal
 * state while looking at a candidate locally.
 */
export function recordedPoints(
  history: AlertHistory | null,
  institutionId: string,
  current?: { at: string; alert: Alert | null },
): RecordedPoint[] {
  const rows: { at: string; state: HistoryInstitutionState | null; alert: Alert | null }[] = [];

  if (current) {
    rows.push({ at: current.at, state: null, alert: current.alert });
  }

  for (const record of history?.records ?? []) {
    if (current && record.generated_at === current.at) continue;
    const state = record.institutions?.[institutionId];
    if (!state) continue;
    rows.push({ at: record.generated_at, state, alert: (state.alert as Alert) ?? null });
  }

  rows.sort((a, b) => Date.parse(b.at) - Date.parse(a.at));

  return rows.map((row, index) => {
    const older = rows[index + 1];
    const gapHours = older
      ? (Date.parse(row.at) - Date.parse(older.at)) / 3_600_000
      : null;
    return {
      at: row.at,
      alert: row.alert,
      gapHours,
      observedPm25: row.state?.observed_pm25 ?? null,
      peakPm25Upper: row.state?.peak_pm25_upper ?? null,
      beyondTrainingRange: Boolean(row.state?.beyond_training_range),
    };
  });
}

/** "3 days" / "18h" / "40 min" — for labelling the interval between records. */
export function describeGap(hours: number): string {
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min`;
  if (hours < 48) return `${Math.round(hours)}h`;
  return `${Math.round(hours / 24)} days`;
}

/**
 * A gap long enough that the screen should say so rather than let two entries
 * sit next to each other implying continuity. Matched to the snapshot staleness
 * threshold so the two notions of "out of date" agree.
 */
export const NOTABLE_GAP_HOURS = 6;

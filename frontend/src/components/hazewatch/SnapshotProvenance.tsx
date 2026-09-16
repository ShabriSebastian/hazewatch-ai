"use client";

import { AlertTriangle, Clock3 } from "lucide-react";
import { describeAge, formatUtc, isStale } from "@/lib/live/snapshot";

/**
 * How current the data on screen is — shown in the header of every screen.
 *
 * This replaces the "Scenario replay · 2023-09-02 16:00Z" badge, which read
 * from the retired backend's `/health`. The treatment is the one the below-fold
 * live panel used to carry alone; with the replay gone and the whole dashboard
 * driven by one manually-published file, it belongs at app level.
 *
 * Two claims, kept deliberately separate (see DEVELOPMENT.md):
 *
 *   1. `generated_at` is when someone last ran `make refresh`. There is no
 *      scheduler, so this is the only thing that says how current this is.
 *   2. The forecast inside was issued for `generated_at - offset` hours,
 *      because the trailing hours of the NRT fire field are only partly
 *      populated.
 *
 * Neither is a detail to tuck away: the dashboard is not a live feed and must
 * never read as one.
 */
export function SnapshotProvenance({
  generatedAt,
  issuedAt,
  issuedOffsetHours,
}: {
  generatedAt?: string | null;
  issuedAt?: string | null;
  issuedOffsetHours?: number | null;
}) {
  if (!generatedAt) return null;

  const stale = isStale(generatedAt);
  const offset = typeof issuedOffsetHours === "number" ? Math.abs(issuedOffsetHours) : null;

  return (
    <span
      title={
        issuedAt
          ? `Forecast issued for ${formatUtc(issuedAt)}${offset ? ` (−${offset}h)` : ""}`
          : undefined
      }
      className={`flex items-center gap-2 rounded-xl border px-4 py-3 text-xs font-semibold ${
        stale
          ? "border-amber-300 bg-amber-50 text-amber-800"
          : "border-slate-200 bg-white text-slate-600"
      }`}
    >
      {stale ? <AlertTriangle size={13} /> : <Clock3 size={13} />}
      <span>
        {stale ? "Snapshot is stale" : "Live snapshot"} · {formatUtc(generatedAt)}
        <span className="ml-1 font-bold">({describeAge(generatedAt)})</span>
      </span>
    </span>
  );
}

/**
 * The fuller explanation, for screens with room for it. Rendered below the
 * header rather than in it, so the header stays scannable.
 */
export function SnapshotStaleNotice({
  generatedAt,
  issuedAt,
  issuedOffsetHours,
}: {
  generatedAt?: string | null;
  issuedAt?: string | null;
  issuedOffsetHours?: number | null;
}) {
  if (!generatedAt || !isStale(generatedAt)) return null;
  const offset = typeof issuedOffsetHours === "number" ? Math.abs(issuedOffsetHours) : 12;

  return (
    <div className="mb-3 flex items-start gap-3 rounded-2xl border border-amber-300 bg-amber-50/70 px-4 py-3">
      <AlertTriangle size={16} className="mt-0.5 flex-none text-amber-600" />
      <p className="text-xs leading-5 text-amber-900">
        <strong>These are not current conditions.</strong> This snapshot was published{" "}
        {describeAge(generatedAt)} ({formatUtc(generatedAt)}) and has not been refreshed
        since. The figures below describe conditions as of{" "}
        {issuedAt ? formatUtc(issuedAt) : `${offset}h before that`}. Refreshing is manual —
        there is no automatic update.
      </p>
    </div>
  );
}

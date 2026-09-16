"use client";

import { Info } from "lucide-react";
import { describeGap, NOTABLE_GAP_HOURS } from "@/lib/live/history";

/**
 * Says what the history below actually is.
 *
 * Alert History used to be produced by sampling a replay clock at fixed 3-hour
 * offsets, which made it look like a regular series. It is now a list of the
 * moments someone ran `make refresh` — irregular by construction, because the
 * refresh is manual (DEVELOPMENT.md).
 *
 * That difference matters for how the screen is read. A gap between two entries
 * does not mean conditions were calm in between; it means nobody looked. This
 * notice exists so nobody reads absence of an entry as absence of haze.
 */
export function RecordedHistoryNotice({
  recordedObservations,
  spanHours,
  largestGapHours,
}: {
  recordedObservations: number;
  spanHours: number | null;
  largestGapHours: number | null;
}) {
  const single = recordedObservations <= 1;

  return (
    <div className="mb-3 flex items-start gap-3 rounded-2xl border border-blue-200 bg-blue-50/70 px-4 py-3">
      <Info size={15} className="mt-0.5 flex-none text-blue-600" />
      <div className="text-[11px] leading-5 text-slate-700">
        {single ? (
          <>
            <strong>One recorded observation.</strong> History accumulates one entry each
            time a snapshot is published, and only one has been recorded so far. There is
            no earlier state to compare against yet.
          </>
        ) : (
          <>
            <strong>
              {recordedObservations} recorded observations
              {spanHours !== null && spanHours > 0 ? ` over ${describeGap(spanHours)}` : ""}.
            </strong>{" "}
            These are the moments a snapshot was published, not a continuous record.
            {largestGapHours !== null && largestGapHours >= NOTABLE_GAP_HOURS && (
              <> The longest gap between them is {describeGap(largestGapHours)}.</>
            )}{" "}
            A gap means nothing was recorded in that interval — not that conditions were
            calm. Publishing is manual and irregular.
          </>
        )}
      </div>
    </div>
  );
}

/** The interval label shown between two adjacent entries. */
export function GapMarker({ gapHours }: { gapHours?: number | null }) {
  if (gapHours === null || gapHours === undefined || gapHours < NOTABLE_GAP_HOURS) {
    return null;
  }
  return (
    <div className="flex items-center gap-2 py-1 pl-2 text-[9px] font-semibold uppercase tracking-wide text-slate-400">
      <span className="h-px w-6 bg-slate-200" />
      {describeGap(gapHours)} with nothing recorded
      <span className="h-px flex-1 bg-slate-200" />
    </div>
  );
}

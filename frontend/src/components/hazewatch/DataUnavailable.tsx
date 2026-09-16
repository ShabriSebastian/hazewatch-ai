"use client";

import { AlertOctagon } from "lucide-react";
import { describeFailure, type SnapshotFailure } from "@/lib/live/snapshot";

/**
 * Shown whenever the dashboard has no data.
 *
 * Before the replay was retired, a failed snapshot fetch rendered nothing at
 * all — which was defensible when it cost one below-fold card, and is not now
 * that it costs the entire application. Every screen renders this instead.
 *
 * The reason is surfaced because the remedies differ: an unset URL is a
 * deployment mistake, an unreachable file is usually transient, and a malformed
 * one means the publish gate passed something it should not have.
 */
export function DataUnavailable({
  reason,
  detail,
}: {
  reason?: SnapshotFailure;
  detail?: string;
}) {
  const message = detail ?? (reason ? describeFailure(reason) : null);

  return (
    <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
      <div className="flex items-start gap-3">
        <AlertOctagon size={18} className="mt-0.5 flex-none" />
        <div>
          <strong className="text-base">No data to show.</strong>
          <p className="mt-2 leading-6">
            {message ?? "The published snapshot could not be loaded."}
          </p>
          <p className="mt-3 text-xs leading-5 text-red-700">
            The dashboard reads a single published snapshot. Nothing is shown rather than
            showing stale or partial figures as though they were current. Reloading is
            worth trying; if it persists, the snapshot needs republishing with{" "}
            <code className="rounded bg-red-100 px-1 py-0.5 font-mono">make refresh</code>.
          </p>
        </div>
      </div>
    </div>
  );
}

/** Narrow an unknown caught value to the snapshot failure reason, if it is one. */
export function failureReason(error: unknown): SnapshotFailure | undefined {
  if (error && typeof error === "object" && "reason" in error) {
    const reason = (error as { reason: unknown }).reason;
    if (reason === "unconfigured" || reason === "unreachable" || reason === "malformed") {
      return reason;
    }
  }
  return undefined;
}

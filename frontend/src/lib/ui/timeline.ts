/**
 * Alert-state timeline helpers.
 *
 * These used to live in `lib/api/hazewatch.ts` beside a function that built the
 * timeline by firing seven `/alerts?at=…` requests at past timestamps — which
 * only worked because a replay clock could be wound backwards. That endpoint
 * and that clock are retired.
 *
 * The helpers themselves are pure and survive unchanged: they describe a
 * sequence of observed alert states, wherever the sequence comes from.
 */

import type { Alert } from "@/lib/api/types";

export interface StatusTimelinePoint {
  at: string;
  alert: Alert | null;
}

/** Shift a timestamp by whole hours. */
export function shiftHours(iso: string, hours: number): string {
  return new Date(Date.parse(iso) + hours * 60 * 60 * 1000)
    .toISOString()
    .replace(/\.\d{3}Z$/, "Z");
}

/**
 * Distinct alert episodes, newest first — the oldest sample of each unbroken
 * run of alerts. Compact "recent alerts" lists use this so one continuous
 * episode reads as one entry rather than one entry per sample.
 */
export function alertOnsets(timeline: StatusTimelinePoint[]): StatusTimelinePoint[] {
  return timeline.filter((point, index) => {
    if (!point.alert) return false;
    const older = timeline[index + 1];
    return !older || !older.alert;
  });
}

/**
 * The most recent point at which the alert state actually flipped, as
 * `[previous, current]`. Null when the state held steady across every sample.
 */
export function latestTransition(
  timeline: StatusTimelinePoint[],
): [StatusTimelinePoint, StatusTimelinePoint] | null {
  const newest = timeline[0];
  if (!newest) return null;

  const changed = timeline.find((point) => Boolean(point.alert) !== Boolean(newest.alert));
  return changed ? [changed, newest] : null;
}

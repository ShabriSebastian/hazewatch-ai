import { apiGet } from "./client";
import { shiftHours } from "@/lib/replay/clock";
import type {
  Alert,
  AlertList,
  AlertStatusResponse,
  Forecast,
  Health,
  HotspotSummary,
  Institution,
  InstitutionList,
  NotificationList,
} from "./types";

/**
 * `at` overrides the replay clock and must be sent on every read that accepts
 * it. Per openapi.json that is /alerts, /institutions/{id}/{alert,forecast,
 * observation} and /notifications — NOT /institutions, /health or /replay/state,
 * which take no such parameter. Institution records are static, so this costs
 * nothing.
 *
 * /hotspots/summary is the exception worth knowing about: it has no `at`
 * either, and defaults its window to the *shared* server clock. Passing
 * explicit `start`/`end` is what keeps the map on the visitor's own clock.
 */
export type At = string | null | undefined;

export async function getHealth() {
  return apiGet<Health>("/health");
}

export async function getInstitutions() {
  return apiGet<InstitutionList>("/institutions");
}

export async function getInstitution(id: string) {
  return apiGet<Institution>(`/institutions/${encodeURIComponent(id)}`);
}

export async function getForecast(id: string, horizonHours = 24, at?: At) {
  return apiGet<Forecast>(`/institutions/${encodeURIComponent(id)}/forecast`, {
    horizon_hours: horizonHours,
    at,
  });
}

export async function getInstitutionAlert(id: string, at?: At) {
  return apiGet<AlertStatusResponse>(`/institutions/${encodeURIComponent(id)}/alert`, { at });
}

export async function getAlertsAt(at?: At) {
  return apiGet<AlertList>("/alerts", { status: "all", at });
}

export async function getNotifications(id: string, limit = 50, at?: At) {
  return apiGet<NotificationList>("/notifications", {
    institution_id: id,
    limit,
    at,
  });
}

/**
 * Hotspot detections aggregated onto a grid for map rendering. The window is
 * pinned to the visitor's clock via explicit start/end because this endpoint
 * accepts no `at` — without them the map would silently follow whatever
 * timestamp the shared server clock happens to hold.
 */
export async function getHotspotSummary(grid = 0.25, at?: At, windowHours = 24) {
  return apiGet<HotspotSummary>("/hotspots/summary", {
    grid,
    end: at,
    start: at ? shiftHours(at, -windowHours) : undefined,
  });
}

/**
 * One reconstructed status transition. `alert` is null when the institution was
 * clear at that timestamp.
 */
export interface StatusTimelinePoint {
  at: string;
  alert: Alert | null;
}

/** Hours back from the anchor clock that we sample. Newest first. */
const TIMELINE_OFFSETS_HOURS = [0, -3, -6, -9, -12, -18, -24];

/**
 * The contract has no alert-history endpoint: `/alerts` returns only the latest
 * evaluation per institution as of `at`, so filtering it to one institution
 * yields at most one row. To show how conditions changed we sample the same
 * endpoint at several past timestamps.
 *
 * Non-alert samples are reported as "clear" rather than Safe or Watch:
 * separating those two needs a forecast per timestamp, which would multiply the
 * request count for a distinction these screens do not draw.
 */
export async function getStatusTimeline(
  institutionId: string,
  anchorAt: At,
): Promise<StatusTimelinePoint[]> {
  if (!anchorAt) {
    const current = await getInstitutionAlert(institutionId);
    return [{ at: new Date().toISOString(), alert: current.alert ?? null }];
  }

  const timestamps = TIMELINE_OFFSETS_HOURS.map((offset) => shiftHours(anchorAt, offset));
  const responses = await Promise.all(timestamps.map((at) => getAlertsAt(at)));

  // Every sample is kept rather than collapsed into transitions. During a
  // sustained episode all samples read "alert", and collapsing would leave the
  // screen with a single row on exactly the bookmarks that matter most.
  return responses.map((response, index) => ({
    at: timestamps[index],
    alert: response.alerts.find((item) => item.institution_id === institutionId) ?? null,
  }));
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

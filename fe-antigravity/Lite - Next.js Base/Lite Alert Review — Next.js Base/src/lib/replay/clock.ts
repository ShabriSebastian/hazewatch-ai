import { apiGet } from "@/lib/api/client";
import type { Bookmark, ReplayState } from "@/lib/api/types";

/**
 * The visitor's own replay clock.
 *
 * The server holds a *single* in-process clock shared by every visitor, and the
 * `/replay/*` POST endpoints mutate it without authentication (DEPLOYMENT.md).
 * With two people on the link at once, one pressing play moves the clock under
 * the other. So we never call those endpoints: we hold the timestamp here and
 * pass it as `?at=` on every read instead. Each visitor is then independent.
 */

/** The bookmark we open on: the only one where all six institutions alert at once. */
export const DEFAULT_BOOKMARK_KEY = "crossborder";

let currentAt: string | null = null;
let bookmarksPromise: Promise<Bookmark[]> | null = null;

export async function getReplayState() {
  return apiGet<ReplayState>("/replay/state");
}

/**
 * Bookmark timestamps come from the API, never hardcoded — CONTRACT.md is
 * explicit that each carries a `label` and `description` written for on-screen
 * use. Cached because the scenario is static for the life of the page.
 */
export function getBookmarks(): Promise<Bookmark[]> {
  bookmarksPromise ??= getReplayState()
    .then((state) => state.bookmarks)
    .catch((error) => {
      bookmarksPromise = null;
      throw error;
    });

  return bookmarksPromise;
}

export function getCurrentAt(): string | null {
  return currentAt;
}

export function setCurrentAt(at: string | null) {
  currentAt = at;
}

/**
 * Resolve the opening clock once per session. Falls back to the live server
 * clock, then to null (which lets the server answer from its own clock) so a
 * missing bookmark never blocks the dashboard from rendering.
 */
export async function initialiseClock(): Promise<string | null> {
  if (currentAt) return currentAt;

  try {
    const state = await getReplayState();
    const opening =
      state.bookmarks.find((item) => item.key === DEFAULT_BOOKMARK_KEY) ?? state.bookmarks[0];
    currentAt = opening?.timestamp ?? state.clock ?? null;
  } catch {
    currentAt = null;
  }

  return currentAt;
}

/** Shift a timestamp by whole hours; used to reconstruct the status timeline. */
export function shiftHours(iso: string, hours: number): string {
  return new Date(Date.parse(iso) + hours * 60 * 60 * 1000).toISOString().replace(/\.\d{3}Z$/, "Z");
}

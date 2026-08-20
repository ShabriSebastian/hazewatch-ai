import { redirect } from "next/navigation";

/**
 * `/pro` has no screen of its own — Live Monitor is Pro's landing page. Without
 * this, typing the bare `/pro` URL 404s, which is a surprising dead end for a
 * mode that every other path is namespaced under.
 */
export default function ProIndexPage() {
  redirect("/pro/live-monitor");
}

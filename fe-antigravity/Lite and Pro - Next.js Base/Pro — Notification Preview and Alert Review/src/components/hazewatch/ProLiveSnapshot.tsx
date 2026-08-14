"use client";

import { AlertTriangle, Clock3, Info, Satellite } from "lucide-react";
import { useEffect, useState } from "react";
import {
  describeAge,
  fetchSnapshot,
  formatUtc,
  isStale,
  STALE_AFTER_HOURS,
  type LiveSnapshot,
} from "@/lib/live/snapshot";

/**
 * Live snapshot panel for the Pro regional monitor.
 *
 * Renders nothing at all until a valid snapshot is in hand - no skeleton, no
 * error box, no "could not load" message. The surrounding dashboard is the
 * validated replay demo and must look exactly as it does today whether or not
 * the scheduled job is healthy.
 *
 * The wording is deliberate. This is a SNAPSHOT regenerated roughly every two
 * hours, and the forecast inside it was issued for `now - 12h` because the
 * trailing hours of the satellite fire field are only partly populated. It is
 * not a continuously updating feed and must never be labelled as one.
 */
export function ProLiveSnapshot() {
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchSnapshot().then((s) => {
      if (!cancelled) setSnapshot(s);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!snapshot) return null;

  const stale = isStale(snapshot.generated_at);
  const alerting = snapshot.institutions.filter((i) => i.alert).length;
  const flagged = snapshot.institutions.filter(
    (i) => i.out_of_range_features.length > 0,
  ).length;
  const detections = snapshot.provenance?.hotspots?.rows_after_dedup;

  return (
    <section
      className={`rounded-2xl border p-4 ${
        stale ? "border-amber-300 bg-amber-50/60" : "border-slate-200 bg-white"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-3">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 flex-none place-items-center rounded-full bg-slate-100 text-slate-600">
            <Satellite size={19} />
          </span>
          <div>
            <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink">
              Live conditions snapshot
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[9px] font-bold text-slate-500">
                separate from the replay demo
              </span>
            </h3>
            <p className="mt-1 text-[10px] text-slate-500">
              The served model run against current satellite and reanalysis data.
              Regenerated roughly every 2 hours — not a continuous feed.
            </p>
          </div>
        </div>

        <div className={`text-right text-[10px] ${stale ? "text-amber-800" : "text-slate-500"}`}>
          <p className="flex items-center justify-end gap-1.5 font-extrabold">
            <Clock3 size={12} />
            {stale ? "Last successful snapshot" : "Generated"} {formatUtc(snapshot.generated_at)}
          </p>
          <p className="mt-0.5">{describeAge(snapshot.generated_at)}</p>
          <p className="mt-0.5">
            forecast issued for {formatUtc(snapshot.issued_at)} ({snapshot.issued_offset_hours}h)
          </p>
        </div>
      </div>

      {stale && (
        <p className="mt-3 flex items-start gap-1.5 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] font-semibold text-amber-800">
          <AlertTriangle size={13} className="mt-0.5 flex-none" />
          No successful run in over {STALE_AFTER_HOURS} hours. The figures below are the last
          known-good snapshot, shown with the time they were actually produced — they are not
          current conditions.
        </p>
      )}

      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
          <p className="text-[10px] text-slate-500">Institutions alerting</p>
          <p className="text-xl font-black text-slate-800">
            {alerting}<span className="text-sm font-bold text-slate-400">/{snapshot.institutions.length}</span>
          </p>
        </div>
        <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
          <p className="text-[10px] text-slate-500">Hotspot detections used</p>
          <p className="text-xl font-black text-slate-800">
            {typeof detections === "number" ? detections.toLocaleString() : "—"}
          </p>
        </div>
        <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
          <p className="text-[10px] text-slate-500">Beyond trained range</p>
          <p className="text-xl font-black text-slate-800">
            {flagged}<span className="text-sm font-bold text-slate-400">/{snapshot.institutions.length}</span>
          </p>
        </div>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-[10px]">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-3 py-2 font-bold">Institution</th>
              <th className="px-3 py-2 font-bold">Observed now</th>
              <th className="px-3 py-2 font-bold">Forecast peak (p90)</th>
              <th className="px-3 py-2 font-bold">Lead</th>
              <th className="px-3 py-2 font-bold">Reliability</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {snapshot.institutions.map((i) => {
              const beyond = i.out_of_range_features.length > 0;
              return (
                <tr key={i.institution_id} className="hover:bg-slate-50/70">
                  <td className="max-w-[190px] truncate px-3 py-2 font-semibold text-slate-700">
                    {i.institution_name}
                  </td>
                  <td className="px-3 py-2 font-bold text-slate-700">
                    {i.observed_pm25.toFixed(1)}
                  </td>
                  <td className="px-3 py-2 font-bold text-violet-600">
                    {(i.peak.pm25_upper ?? i.peak.pm25).toFixed(1)}
                  </td>
                  <td className="px-3 py-2 text-slate-600">
                    {i.alert ? `${i.alert.lead_time_hours} h` : "—"}
                  </td>
                  <td className="px-3 py-2">
                    {beyond ? (
                      <span className="rounded-full bg-amber-100 px-2 py-1 text-[9px] font-extrabold text-amber-700">
                        beyond trained range
                      </span>
                    ) : (
                      <span className="text-slate-400">in range</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="mt-3 flex items-start gap-1.5 border-t border-slate-100 pt-2 text-[9px] leading-4 text-slate-400">
        <Info size={11} className="mt-0.5 flex-none" />
        Not a validation: the forecast hours have not happened yet, so nothing here measures
        accuracy on live data. The forest cannot emit above ~90 µg/m³ and will under-read a
        severe peak. All institutions in one city share a CAMS grid cell, so their observed
        PM2.5 is identical by construction.
      </p>
    </section>
  );
}

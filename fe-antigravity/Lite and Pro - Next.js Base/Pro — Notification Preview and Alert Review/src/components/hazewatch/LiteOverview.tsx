"use client";

import Link from "next/link";
import {
  AlertTriangle,
  BellRing,
  Building2,
  ChevronRight,
  Clock3,
  Info,
  ShieldAlert,
  Wind,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { loadLiteOverviewData } from "@/lib/data/source";
import { alertOnsets, type StatusTimelinePoint } from "@/lib/api/hazewatch";
import type { Alert, Forecast, Institution } from "@/lib/api/types";
import { useSelectedInstitution } from "@/lib/ui/institutionContext";
import { attributionLine, formatLocation, localStamp, reliabilityNote } from "@/lib/ui/format";
import { getLiteRiskStatus, type LiteRiskStatus } from "@/lib/ui/status";
import { getStatusCopy } from "@/lib/ui/copy";
import { AppShell } from "./AppShell";

type ScreenData = Awaited<ReturnType<typeof loadLiteOverviewData>>;

const statusStyle: Record<LiteRiskStatus, { label: string; badge: string; panel: string; icon: string }> = {
  safe: {
    label: "SAFE",
    badge: "bg-emerald-500 text-white",
    panel: "border-emerald-200 bg-emerald-50/65",
    icon: "bg-emerald-100 text-emerald-700",
  },
  watch: {
    label: "WATCH",
    badge: "bg-amber-500 text-white",
    panel: "border-amber-200 bg-amber-50/70",
    icon: "bg-amber-100 text-amber-700",
  },
  alert: {
    label: "ALERT",
    badge: "bg-red-500 text-white",
    panel: "border-orange-300 bg-[#fff4ed]",
    icon: "bg-orange-100 text-orange-600",
  },
};

function alertPeakValue(forecast: Forecast, alert: Alert | null | undefined) {
  return alert?.forecast_peak_pm25 ?? forecast.peak.pm25_upper ?? forecast.peak.pm25;
}

function ReliabilityCard({ forecast }: { forecast: Forecast }) {
  const note = reliabilityNote(forecast);
  if (!note) return null;

  return (
    <section className="rounded-2xl border border-amber-300 bg-amber-50/80 p-5">
      <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><AlertTriangle size={16} /> Forecast reliability notice</h3>
      <p className="mt-3 max-w-[38ch] text-xs leading-5 text-slate-600">{note}</p>
    </section>
  );
}

function RecentAlerts({ timeline, institution }: { timeline: StatusTimelinePoint[]; institution: Institution }) {
  const entries = alertOnsets(timeline);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><Clock3 size={16} /> Recent Alerts</h3>
        <Link href="/lite/alert-history" className="text-[11px] font-bold text-blue-600">View all <ChevronRight className="inline" size={13} /></Link>
      </div>
      <div className="divide-y divide-slate-100">
        {entries.length === 0 ? (
          <p className="py-5 text-xs text-slate-500">No recent alerts for this institution.</p>
        ) : (
          entries.slice(0, 3).map((point) => (
            <div key={point.at} className="grid grid-cols-[58px_72px_1fr] items-center gap-2 py-3 text-[11px]">
              <span className="font-semibold text-slate-500">{localStamp(point.alert!.triggered_at, institution.country)}</span>
              <span className="rounded-full bg-red-100 px-2 py-1 text-center text-[10px] font-extrabold text-red-600">Alert</span>
              <span className="text-slate-600">Forecast alert issued with {point.alert!.lead_time_hours}h warning lead time.</span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

export function LiteOverview() {
  const { institutionId } = useSelectedInstitution();
  const [data, setData] = useState<ScreenData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);

    loadLiteOverviewData(institutionId)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load dashboard data.");
      });

    return () => {
      cancelled = true;
    };
  }, [institutionId]);

  if (error) {
    return (
      <AppShell activePage="overview">
        <main className="p-8">
          <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
            <strong>Could not load Institution Overview.</strong>
            <p className="mt-2">{error}</p>
            <p className="mt-2">For an offline demo, set NEXT_PUBLIC_HAZE_DATA_MODE=mock.</p>
          </div>
        </main>
      </AppShell>
    );
  }

  if (!data) {
    return (
      <AppShell activePage="overview">
        <main className="p-8 text-sm text-slate-500">
          Loading institution overview…
          <p className="mt-2 text-xs text-slate-400">The first request can take up to a minute if the demo server is waking from idle.</p>
        </main>
      </AppShell>
    );
  }

  return <LiteOverviewLoaded data={data} />;
}

function LiteOverviewLoaded({ data }: { data: ScreenData }) {
  const { institution, institutions, forecast, alertResponse, statusTimeline, health, at } = data;
  const status = useMemo(() => getLiteRiskStatus(forecast, alertResponse), [forecast, alertResponse]);
  const style = statusStyle[status];
  const copy = getStatusCopy(institution.type, status);
  const alert = alertResponse.alert;
  const peak = alertPeakValue(forecast, alert);
  const actions = status === "alert" ? alert?.recommended_actions ?? [] : [];
  const reliability = reliabilityNote(forecast);
  const attribution = attributionLine(forecast.attribution);
  const peakAt = alert?.forecast_peak_at ?? forecast.peak.timestamp;

  return (
    <AppShell activePage="overview" institutions={institutions} current={institution} health={health} at={at}>
      <main className="min-w-0 p-6 lg:p-8">
        <div className="mb-3">
          <h2 className="text-3xl font-extrabold tracking-tight text-ink">Institution Overview</h2>
          <p className="mt-1 text-sm text-slate-500">Clear, action-oriented haze information for your institution.</p>
        </div>

        <section className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-5 py-5 shadow-sm">
          <div className="flex items-center gap-4">
            <div className="grid h-16 w-16 place-items-center rounded-full bg-emerald-50 text-emerald-700"><Building2 size={30} /></div>
            <div>
              <h3 className="text-xl font-extrabold text-ink">{institution.name}</h3>
              <p className="mt-1 text-xs text-slate-500"><span className="capitalize">{institution.type}</span> &nbsp; ◈ &nbsp; {formatLocation(institution)}</p>
            </div>
          </div>
          <span className="rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-bold text-blue-600">Lite Mode</span>
        </section>

        <section className={`mt-3 rounded-2xl border p-5 ${style.panel}`}>
          <div className="grid grid-cols-[105px_1fr] gap-4">
            <div className="flex flex-col items-center gap-3">
              <div className={`grid h-20 w-20 place-items-center rounded-full ${style.icon}`}>
                {status === "alert" ? <AlertTriangle size={40} fill="currentColor" className="text-orange-600" /> : status === "watch" ? <BellRing size={34} /> : <Info size={34} />}
              </div>
              <span className={`rounded-full px-4 py-1.5 text-[11px] font-extrabold ${style.badge}`}>{style.label}</span>
            </div>
            <div>
              <h3 className={`text-2xl font-extrabold ${status === "alert" ? "text-orange-700" : "text-ink"}`}>{copy.title}</h3>
              <p className="mt-2 text-sm text-slate-600">{copy.body}</p>
              {status === "alert" && (
                <>
                  <p className="mt-1 text-sm text-slate-600">Highest impact is expected around <strong>{localStamp(peakAt, institution.country)}</strong>.</p>
                  <p className="mt-2 text-xs text-slate-500">Forecast peak: {peak.toFixed(1)} µg/m³ · supporting detail, not the primary decision cue.</p>
                </>
              )}
              {attribution && (
                <p className="mt-2 flex items-start gap-1.5 text-xs font-semibold text-slate-600">
                  <Wind size={13} className="mt-0.5 flex-none text-slate-400" /> {attribution}
                </p>
              )}
            </div>
          </div>

          {status === "alert" && (
            <div className="mt-5 border-t border-orange-200 pt-4">
              <h4 className="text-sm font-extrabold text-ink">What you can do now</h4>
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                {actions.map((action, index) => (
                  <div key={`${action}-${index}`} className="flex min-h-16 items-center gap-3 rounded-xl border border-orange-200 bg-white/70 px-4 py-3 text-sm font-bold text-slate-700">
                    <span className="grid h-9 w-9 flex-none place-items-center rounded-full bg-orange-100 text-orange-600">{index + 1}</span>
                    {action}
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        <div className={`mt-3 grid gap-3 ${reliability ? "lg:grid-cols-[.9fr_1.05fr_1.2fr]" : "lg:grid-cols-[1fr_1.2fr]"}`}>
          {reliability && <ReliabilityCard forecast={forecast} />}

          {status === "alert" && alert ? (
            <section className="rounded-2xl border border-red-200 bg-red-50/55 p-5">
              <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><ShieldAlert size={16} /> Alert ready for review</h3>
              <p className="mt-3 text-xs leading-5 text-slate-600">A message has been prepared for this institution&apos;s verified admin contact.</p>
              <p className="text-xs font-extrabold text-slate-700">It will not be sent until you confirm.</p>
              <div className="mt-3 border-t border-red-100 pt-3 text-[11px] text-slate-500">
                To: <strong className="text-slate-700">Verified admin contact</strong><br />{institution.name}
              </div>
              <div className="mt-4 flex gap-2">
                <Link href="/lite/alert-review" className="rounded-xl bg-orange-600 px-4 py-2 text-xs font-extrabold text-white shadow-sm hover:bg-orange-700">Review Alert</Link>
                <Link href="/lite/institution-detail" className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-extrabold text-slate-700">See details</Link>
              </div>
            </section>
          ) : (
            <section className="rounded-2xl border border-blue-200 bg-blue-50/55 p-5">
              <h3 className="text-sm font-extrabold text-ink">Monitoring only</h3>
              <p className="mt-2 text-xs leading-5 text-slate-600">No alert is waiting for review at this time.</p>
            </section>
          )}

          <RecentAlerts timeline={statusTimeline} institution={institution} />
        </div>

        <div className="mt-3 rounded-xl border border-blue-100 bg-blue-50/70 px-4 py-3 text-[11px] text-slate-600">
          ⓘ This Lite view is designed for institution staff and focuses on what they need to know and do next.
        </div>
        <p className="mt-2 text-[10px] text-slate-400">
          PM2.5 values are {forecast.current.source === "cams_reanalysis" ? "CAMS reanalysis, not ground-station measurements" : `from ${forecast.current.source.replace(/_/g, " ")}`}. Alerting uses the upper prediction band operating point defined by the frozen contract.
        </p>
      </main>
    </AppShell>
  );
}

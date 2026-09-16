"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  BellRing,
  Check,
  CheckCircle2,
  Clock3,
  Info,
  LockKeyhole,
  RotateCw,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Alert, Institution } from "@/lib/api/types";
import { loadLiteAlertHistoryData } from "@/lib/data/source";
import type { LiteStatusTimelineItem } from "@/lib/data/liteHistoryMock";
import { getLiteRiskStatus, type LiteRiskStatus } from "@/lib/ui/status";
import { AppShell } from "./AppShell";

type ScreenData = Awaited<ReturnType<typeof loadLiteAlertHistoryData>>;

type TimelineView = LiteStatusTimelineItem;

function localTime(iso: string, country: string) {
  const timeZone = country === "ID" ? "Asia/Pontianak" : "Asia/Kuching";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

function localDayKey(iso: string, country: string) {
  const timeZone = country === "ID" ? "Asia/Pontianak" : "Asia/Kuching";
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(iso));
}

function peakWindow(alert: Alert, institution: Institution) {
  const peak = new Date(alert.forecast_peak_at);
  const start = new Date(peak.getTime() - 60 * 60 * 1000).toISOString();
  const end = new Date(peak.getTime() + 60 * 60 * 1000).toISOString();
  return `${localTime(start, institution.country)}–${localTime(end, institution.country)}`;
}

function statusLabel(status: LiteRiskStatus) {
  if (status === "alert") return "Forecast Alert";
  if (status === "watch") return "Watch";
  return "Safe";
}

function statusClasses(status: LiteRiskStatus) {
  if (status === "alert") return "bg-red-100 text-red-600";
  if (status === "watch") return "bg-amber-100 text-amber-700";
  return "bg-emerald-100 text-emerald-700";
}

function statusDot(status: LiteRiskStatus) {
  if (status === "alert") return "bg-red-500";
  if (status === "watch") return "bg-amber-500";
  return "bg-emerald-500";
}

function inferApiTimeline(alerts: Alert[]): TimelineView[] {
  return alerts.map((alert) => ({
    id: alert.alert_id,
    occurredAt: alert.triggered_at,
    status: "alert",
    message: `Air quality alert issued with ${alert.lead_time_hours}h warning lead time.`,
    actionLabel: alert.status === "resolved" ? "Resolved" : "Prepared · Not sent",
  }));
}

function WhatThisMeans({ institution }: { institution: Institution }) {
  const text = institution.type === "hospital"
    ? "Hospital operations may need to be adjusted as haze conditions worsen."
    : "Outdoor activities may need to be adjusted this afternoon.";

  return (
    <section className="rounded-2xl border border-blue-200 bg-blue-50/60 p-5">
      <div className="flex items-center gap-4">
        <div className="grid h-14 w-14 flex-none place-items-center rounded-full bg-blue-100 text-blue-600">
          <Info size={27} />
        </div>
        <div>
          <p className="text-[11px] text-slate-500">What this means</p>
          <p className="mt-1 text-base font-extrabold leading-6 text-slate-700">{text}</p>
        </div>
      </div>
    </section>
  );
}

function StatusProgression({ status }: { status: LiteRiskStatus }) {
  const stages = [
    { key: "safe" as const, when: "This morning", label: "Safe", note: "Normal monitoring", icon: Check },
    { key: "watch" as const, when: "Midday", label: "Watch", note: "Conditions may worsen", icon: Info },
    { key: "alert" as const, when: "This afternoon", label: "Forecast Alert", note: "Unhealthy levels possible", icon: AlertTriangle },
  ];
  const order: Record<LiteRiskStatus, number> = { safe: 0, watch: 1, alert: 2 };

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><ArrowRight size={16} /> How conditions changed</h3>
      <div className="mt-5 grid grid-cols-[1fr_34px_1fr_34px_1fr] items-start text-center">
        {stages.map((stage, index) => {
          const Icon = stage.icon;
          const reached = order[stage.key] <= order[status];
          const classes = stage.key === "safe"
            ? "bg-emerald-100 text-emerald-700"
            : stage.key === "watch"
              ? "bg-amber-100 text-amber-700"
              : "bg-red-100 text-red-600";
          return (
            <div className="contents" key={stage.key}>
              <div className={reached ? "opacity-100" : "opacity-40"}>
                <p className="text-[10px] font-medium text-slate-500">{stage.when}</p>
                <div className={`mx-auto mt-3 grid h-14 w-14 place-items-center rounded-full ${classes}`}><Icon size={23} /></div>
                <p className="mt-3 text-[11px] font-extrabold text-slate-700">{stage.label}</p>
                <p className="mt-1 text-[10px] text-slate-500">{stage.note}</p>
              </div>
              {index < stages.length - 1 && <div className="mt-[54px] text-slate-400">→</div>}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Timeline({ items, institution }: { items: TimelineView[]; institution: Institution }) {
  const grouped = items.reduce<Record<string, TimelineView[]>>((acc, item) => {
    const key = localDayKey(item.occurredAt, institution.country);
    (acc[key] ||= []).push(item);
    return acc;
  }, {});
  const keys = Object.keys(grouped).sort((a, b) => b.localeCompare(a));
  const newestDay = keys[0];

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm lg:p-5">
      <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><Clock3 size={16} /> Recent alert timeline</h3>
      <div className="mt-3 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-[10px] text-slate-500">
        ⓘ Most recent update: conditions have worsened since this morning.
      </div>

      {items.length === 0 ? (
        <p className="py-8 text-xs text-slate-500">No recent alert records are available for this institution.</p>
      ) : (
        <div className="mt-4 space-y-4">
          {keys.map((key, groupIndex) => (
            <div key={key}>
              <p className="mb-2 text-[11px] font-extrabold text-slate-700">{key === newestDay ? "Today" : groupIndex === 1 ? "Yesterday" : key}</p>
              <div className="overflow-hidden rounded-xl border border-slate-200">
                {grouped[key].map((item) => (
                  <div key={item.id} className="grid grid-cols-[58px_12px_74px_1fr_auto] items-center gap-3 border-b border-slate-100 px-3 py-3 text-[10px] last:border-b-0 lg:grid-cols-[68px_12px_78px_1fr_auto]">
                    <span className="font-extrabold text-slate-700">{localTime(item.occurredAt, institution.country)}</span>
                    <span className={`h-2.5 w-2.5 rounded-full ${statusDot(item.status)}`} />
                    <span className={`rounded-full px-3 py-1 text-center text-[9px] font-extrabold ${statusClasses(item.status)}`}>{item.status === "alert" ? "Alert" : item.status === "watch" ? "Watch" : "Safe"}</span>
                    <span className="text-slate-600">{item.message}</span>
                    <span className={item.status === "alert" ? "text-slate-400" : item.status === "safe" ? "text-slate-400" : "font-semibold text-amber-700"}>{item.actionLabel}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function LiteAlertHistory() {
  const [data, setData] = useState<ScreenData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadLiteAlertHistoryData().then(setData).catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "Failed to load alert history.");
    });
  }, []);

  if (error) {
    return (
      <AppShell activePage="alert-history">
        <main className="p-8">
          <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
            <strong>Could not load Alert History.</strong>
            <p className="mt-2">{error}</p>
            <p className="mt-2">For an offline demo, set NEXT_PUBLIC_HAZE_DATA_MODE=mock.</p>
          </div>
        </main>
      </AppShell>
    );
  }

  if (!data) {
    return (
      <AppShell activePage="alert-history">
        <main className="p-8 text-sm text-slate-500">Loading alert history…</main>
      </AppShell>
    );
  }

  return <Loaded data={data} />;
}

function Loaded({ data }: { data: ScreenData }) {
  const { institution, forecast, alertResponse, alertHistory, statusTimeline } = data;
  const risk = useMemo(() => getLiteRiskStatus(forecast, alertResponse), [forecast, alertResponse]);
  const alert = alertResponse.alert;
  const timeline = statusTimeline ?? inferApiTimeline(alertHistory);
  const latestTime = alert ? localTime(alert.triggered_at, institution.country) : localTime(forecast.issued_at, institution.country);

  return (
    <AppShell activePage="alert-history">
      <main className="min-w-0 px-6 py-5 lg:px-7 lg:py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-[31px] font-extrabold tracking-tight text-ink">Alert History</h2>
            <p className="mt-1 text-xs text-slate-500">Review recent alerts and how conditions have changed for your institution.</p>
          </div>
          <div className="flex min-w-[310px] items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-[11px] shadow-sm">
            <span className="text-slate-500">Viewing:</span>
            <span className="ml-4 max-w-[220px] truncate font-extrabold text-slate-700">{institution.name}</span>
            <span className="ml-3">⌄</span>
          </div>
        </div>

        <div className="mt-4 grid gap-3 xl:grid-cols-3">
          <section className="rounded-2xl border border-red-200 bg-red-50/65 p-5">
            <div className="flex items-center gap-4">
              <div className="grid h-14 w-14 flex-none place-items-center rounded-full bg-red-100 text-red-600"><AlertTriangle size={28} fill="currentColor" /></div>
              <div>
                <p className="text-[10px] text-slate-500">Current status</p>
                <span className={`mt-1 inline-flex rounded-full px-2.5 py-1 text-[9px] font-extrabold ${statusClasses(risk)}`}>{statusLabel(risk)}</span>
                <p className="mt-2 text-[11px] text-slate-600">{risk === "alert" ? "Air quality is expected to worsen this afternoon." : risk === "watch" ? "Conditions are being monitored and may change." : "Air quality is normal."}</p>
              </div>
            </div>
          </section>

          <section className="rounded-2xl border border-amber-200 bg-amber-50/55 p-5">
            <div className="flex items-center gap-4">
              <div className="grid h-14 w-14 flex-none place-items-center rounded-full bg-amber-100 text-amber-600"><RotateCw size={27} /></div>
              <div>
                <p className="text-[10px] text-slate-500">Latest change</p>
                <div className="mt-2 flex items-center gap-2 text-xs font-extrabold text-slate-700">
                  {risk === "alert" ? <><span className="rounded-full bg-amber-100 px-2 py-1 text-[9px] text-amber-700">Watch</span><ArrowRight size={14}/><span className="rounded-full bg-red-100 px-2 py-1 text-[9px] text-red-600">Alert</span></> : risk === "watch" ? <><span className="rounded-full bg-emerald-100 px-2 py-1 text-[9px] text-emerald-700">Safe</span><ArrowRight size={14}/><span className="rounded-full bg-amber-100 px-2 py-1 text-[9px] text-amber-700">Watch</span></> : <span className="rounded-full bg-emerald-100 px-2 py-1 text-[9px] text-emerald-700">Safe</span>}
                </div>
                <p className="mt-2 text-[10px] text-slate-500">Updated at {latestTime}</p>
              </div>
            </div>
          </section>

          <WhatThisMeans institution={institution} />
        </div>

        <div className="mt-3 grid gap-3 xl:grid-cols-[1.2fr_1fr]">
          <Timeline items={timeline} institution={institution} />

          <div className="space-y-3">
            <StatusProgression status={risk} />

            {risk === "alert" && alert ? (
              <section className="rounded-2xl border border-red-200 bg-red-50/50 p-5">
                <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><AlertTriangle size={16} /> Latest alert details</h3>
                <dl className="mt-3 divide-y divide-red-100 text-[10px]">
                  <div className="flex justify-between gap-5 py-2.5"><dt className="text-slate-500">Institution</dt><dd className="text-right font-extrabold text-slate-700">{institution.name}</dd></div>
                  <div className="flex justify-between gap-5 py-2.5"><dt className="text-slate-500">Expected peak</dt><dd className="font-extrabold text-slate-700">{peakWindow(alert, institution)}</dd></div>
                  <div className="flex justify-between gap-5 py-2.5"><dt className="text-slate-500">Main concern</dt><dd className="font-extrabold text-slate-700">Air quality may become unhealthy</dd></div>
                  <div className="flex justify-between gap-5 py-2.5"><dt className="text-slate-500">Message status</dt><dd className="font-extrabold text-slate-700">Prepared for verified admin contact</dd></div>
                </dl>
                <p className="mt-3 flex items-center gap-1.5 border-t border-red-100 pt-3 text-[10px] font-extrabold text-red-600"><AlertTriangle size={12}/> It will not be sent until you confirm.</p>
              </section>
            ) : (
              <section className="rounded-2xl border border-blue-200 bg-blue-50/50 p-5">
                <h3 className="text-sm font-extrabold text-ink">No alert requires review</h3>
                <p className="mt-2 text-xs text-slate-600">Safe and Watch states remain informational only.</p>
              </section>
            )}

            <section className="rounded-2xl border border-violet-200 bg-violet-50/60 p-4">
              <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><CheckCircle2 size={16}/> What can you do next?</h3>
              {risk === "alert" && alert ? (
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <Link href="/lite/alert-review" className="rounded-xl bg-blue-600 px-4 py-3 text-center text-xs font-extrabold text-white">✉ Review Alert</Link>
                  <Link href="/lite/institution-detail" className="rounded-xl border border-slate-300 bg-white px-4 py-3 text-center text-xs font-extrabold text-slate-700">View Institution Detail</Link>
                </div>
              ) : (
                <p className="mt-2 text-xs text-slate-600">No action is required right now.</p>
              )}
            </section>
          </div>
        </div>

        <div className="mt-3 flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-[10px] text-slate-500">
          <LockKeyhole size={13} /> Messages are sent only to verified institution contacts. This prototype does not send messages to public or personal phone numbers.
        </div>
        <p className="mt-2 text-[9px] text-slate-400">Alert status shown here is a forecast-based state, not necessarily the current observed air-quality state.</p>
      </main>
    </AppShell>
  );
}

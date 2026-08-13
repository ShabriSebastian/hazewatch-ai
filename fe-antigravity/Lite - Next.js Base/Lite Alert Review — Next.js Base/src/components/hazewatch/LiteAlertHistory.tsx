"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  Clock3,
  Info,
  LockKeyhole,
  RotateCw,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { latestTransition, type StatusTimelinePoint } from "@/lib/api/hazewatch";
import type { Institution } from "@/lib/api/types";
import { loadLiteAlertHistoryData } from "@/lib/data/source";
import { localDayKey, localDayLabel, localTime, peakTime } from "@/lib/ui/format";
import { useSelectedInstitution } from "@/lib/ui/institutionContext";
import { getLiteRiskStatus, type LiteRiskStatus } from "@/lib/ui/status";
import { AppShell } from "./AppShell";

type ScreenData = Awaited<ReturnType<typeof loadLiteAlertHistoryData>>;

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

function WhatThisMeans({ institution }: { institution: Institution }) {
  const text = institution.type === "hospital"
    ? "Hospital operations may need to be adjusted as haze conditions worsen."
    : "Outdoor activities may need to be adjusted while conditions are elevated.";

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

/**
 * The timeline is reconstructed by sampling `/alerts?at=` at several past
 * timestamps, so the only two states it can honestly report are "alert" and
 * "clear". Separating Safe from Watch at a past instant would need a forecast
 * per sample, which this screen does not fetch.
 */
function Timeline({ items, institution }: { items: StatusTimelinePoint[]; institution: Institution }) {
  const grouped = items.reduce<Record<string, StatusTimelinePoint[]>>((acc, item) => {
    const key = localDayKey(item.at, institution.country);
    (acc[key] ||= []).push(item);
    return acc;
  }, {});
  const keys = Object.keys(grouped).sort((a, b) => b.localeCompare(a));

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm lg:p-5">
      <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><Clock3 size={16} /> Recent alert timeline</h3>
      <div className="mt-3 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-[10px] text-slate-500">
        ⓘ Reconstructed by sampling the alerts endpoint over the past 24 hours of the replay.
      </div>

      {items.length === 0 ? (
        <p className="py-8 text-xs text-slate-500">No recent alert records are available for this institution.</p>
      ) : (
        <div className="mt-4 space-y-4">
          {keys.map((key) => (
            <div key={key}>
              <p className="mb-2 text-[11px] font-extrabold text-slate-700">{localDayLabel(grouped[key][0].at, institution.country)}</p>
              <div className="overflow-hidden rounded-xl border border-slate-200">
                {grouped[key].map((item) => (
                  <div key={item.at} className="grid grid-cols-[58px_12px_74px_1fr_auto] items-center gap-3 border-b border-slate-100 px-3 py-3 text-[10px] last:border-b-0 lg:grid-cols-[68px_12px_78px_1fr_auto]">
                    <span className="font-extrabold text-slate-700">{localTime(item.at, institution.country)}</span>
                    <span className={`h-2.5 w-2.5 rounded-full ${item.alert ? "bg-red-500" : "bg-emerald-500"}`} />
                    <span className={`rounded-full px-3 py-1 text-center text-[9px] font-extrabold ${item.alert ? "bg-red-100 text-red-600" : "bg-emerald-100 text-emerald-700"}`}>
                      {item.alert ? "Alert" : "Clear"}
                    </span>
                    <span className="text-slate-600">
                      {item.alert
                        ? `Air quality alert issued with ${item.alert.lead_time_hours}h warning lead time.`
                        : "No alert in effect at this time."}
                    </span>
                    <span className="text-slate-400">{item.alert ? "Prepared · Not sent" : "No action needed"}</span>
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

/**
 * The escalation ladder, with the current state highlighted. The stage labels
 * deliberately carry no times: an earlier draft captioned them "This morning /
 * Midday / This afternoon", which the data never supported.
 */
function StatusProgression({ status }: { status: LiteRiskStatus }) {
  const stages = [
    { key: "safe" as const, label: "Safe", note: "Normal monitoring", icon: Check, classes: "bg-emerald-100 text-emerald-700" },
    { key: "watch" as const, label: "Watch", note: "Conditions may worsen", icon: Info, classes: "bg-amber-100 text-amber-700" },
    { key: "alert" as const, label: "Forecast Alert", note: "Unhealthy levels possible", icon: AlertTriangle, classes: "bg-red-100 text-red-600" },
  ];
  const order: Record<LiteRiskStatus, number> = { safe: 0, watch: 1, alert: 2 };

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><ArrowRight size={16} /> How conditions escalate</h3>
      <div className="mt-5 grid grid-cols-[1fr_34px_1fr_34px_1fr] items-start text-center">
        {stages.map((stage, index) => {
          const Icon = stage.icon;
          const reached = order[stage.key] <= order[status];
          return (
            <div className="contents" key={stage.key}>
              <div className={reached ? "opacity-100" : "opacity-40"}>
                <div className={`mx-auto grid h-14 w-14 place-items-center rounded-full ${stage.classes}`}><Icon size={23} /></div>
                <p className="mt-3 text-[11px] font-extrabold text-slate-700">{stage.label}</p>
                <p className="mt-1 text-[10px] text-slate-500">{stage.note}</p>
              </div>
              {index < stages.length - 1 && <div className="mt-[22px] text-slate-400">→</div>}
            </div>
          );
        })}
      </div>
      <p className="mt-4 border-t border-slate-100 pt-3 text-[10px] text-slate-500">
        Currently at <strong className="text-slate-700">{statusLabel(status)}</strong>.
      </p>
    </section>
  );
}

/** Shows the last real flip in state, or the steady state when there was none. */
function LatestChange({ items }: { items: StatusTimelinePoint[] }) {
  const newest = items[0];
  if (!newest) return <span className="text-[10px] font-normal text-slate-500">No recorded change.</span>;

  const chip = (isAlert: boolean) => (
    <span className={`rounded-full px-2 py-1 text-[9px] ${isAlert ? "bg-red-100 text-red-600" : "bg-emerald-100 text-emerald-700"}`}>
      {isAlert ? "Alert" : "Clear"}
    </span>
  );

  const transition = latestTransition(items);
  if (!transition) {
    return (
      <>
        {chip(Boolean(newest.alert))}
        <span className="text-[10px] font-normal text-slate-500">unchanged over the last 24h</span>
      </>
    );
  }

  const [previous, current] = transition;
  return (
    <>
      {chip(Boolean(previous.alert))}
      <ArrowRight size={14} />
      {chip(Boolean(current.alert))}
    </>
  );
}

export function LiteAlertHistory() {
  const { institutionId } = useSelectedInstitution();
  const [data, setData] = useState<ScreenData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);

    loadLiteAlertHistoryData(institutionId)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load alert history.");
      });

    return () => {
      cancelled = true;
    };
  }, [institutionId]);

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
        <main className="p-8 text-sm text-slate-500">
          Loading alert history…
          <p className="mt-2 text-xs text-slate-400">The first request can take up to a minute if the demo server is waking from idle.</p>
        </main>
      </AppShell>
    );
  }

  return <Loaded data={data} />;
}

function Loaded({ data }: { data: ScreenData }) {
  const { institution, institutions, forecast, alertResponse, statusTimeline, health, at } = data;
  const risk = useMemo(() => getLiteRiskStatus(forecast, alertResponse), [forecast, alertResponse]);
  const alert = alertResponse.alert;
  const latestTime = alert ? localTime(alert.triggered_at, institution.country) : localTime(forecast.issued_at, institution.country);

  return (
    <AppShell activePage="alert-history" institutions={institutions} current={institution} health={health} at={at}>
      <main className="min-w-0 px-6 py-5 lg:px-7 lg:py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-[31px] font-extrabold tracking-tight text-ink">Alert History</h2>
            <p className="mt-1 text-xs text-slate-500">Review recent alerts and how conditions have changed for your institution.</p>
          </div>
          <div className="flex min-w-[310px] items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-[11px] shadow-sm">
            <span className="text-slate-500">Viewing:</span>
            <span className="ml-4 max-w-[240px] truncate font-extrabold text-slate-700">{institution.name}</span>
          </div>
        </div>

        <div className="mt-4 grid gap-3 xl:grid-cols-3">
          <section className="rounded-2xl border border-red-200 bg-red-50/65 p-5">
            <div className="flex items-center gap-4">
              <div className="grid h-14 w-14 flex-none place-items-center rounded-full bg-red-100 text-red-600"><AlertTriangle size={28} fill="currentColor" /></div>
              <div>
                <p className="text-[10px] text-slate-500">Current status</p>
                <span className={`mt-1 inline-flex rounded-full px-2.5 py-1 text-[9px] font-extrabold ${statusClasses(risk)}`}>{statusLabel(risk)}</span>
                <p className="mt-2 text-[11px] text-slate-600">{risk === "alert" ? "Air quality is expected to become unhealthy." : risk === "watch" ? "Conditions are being monitored and may change." : "Air quality is normal."}</p>
              </div>
            </div>
          </section>

          <section className="rounded-2xl border border-amber-200 bg-amber-50/55 p-5">
            <div className="flex items-center gap-4">
              <div className="grid h-14 w-14 flex-none place-items-center rounded-full bg-amber-100 text-amber-600"><RotateCw size={27} /></div>
              <div>
                <p className="text-[10px] text-slate-500">Latest change</p>
                <div className="mt-2 flex items-center gap-2 text-xs font-extrabold text-slate-700">
                  <LatestChange items={statusTimeline} />
                </div>
                <p className="mt-2 text-[10px] text-slate-500">Updated at {latestTime}</p>
              </div>
            </div>
          </section>

          <WhatThisMeans institution={institution} />
        </div>

        <div className="mt-3 grid gap-3 xl:grid-cols-[1.2fr_1fr]">
          <Timeline items={statusTimeline} institution={institution} />

          <div className="space-y-3">
            <StatusProgression status={risk} />

            {risk === "alert" && alert ? (
              <section className="rounded-2xl border border-red-200 bg-red-50/50 p-5">
                <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><AlertTriangle size={16} /> Latest alert details</h3>
                <dl className="mt-3 divide-y divide-red-100 text-[10px]">
                  <div className="flex justify-between gap-5 py-2.5"><dt className="text-slate-500">Institution</dt><dd className="text-right font-extrabold text-slate-700">{institution.name}</dd></div>
                  <div className="flex justify-between gap-5 py-2.5"><dt className="text-slate-500">Expected peak</dt><dd className="font-extrabold text-slate-700">{peakTime(alert.forecast_peak_at, institution.country)}</dd></div>
                  <div className="flex justify-between gap-5 py-2.5"><dt className="text-slate-500">Warning lead time</dt><dd className="font-extrabold text-slate-700">{alert.lead_time_hours} hours</dd></div>
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
          <LockKeyhole size={13} /> Messages are sent only to an institution&apos;s verified admin contact. This prototype does not send messages to public or personal phone numbers.
        </div>
        <p className="mt-2 text-[9px] text-slate-400">Alert status shown here is a forecast-based state, not necessarily the current observed air-quality state.</p>
      </main>
    </AppShell>
  );
}

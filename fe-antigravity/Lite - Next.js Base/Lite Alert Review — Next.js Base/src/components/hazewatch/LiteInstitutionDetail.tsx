"use client";

import Link from "next/link";
import {
  AlertTriangle,
  BellRing,
  Building2,
  CheckCircle2,
  ChevronRight,
  CloudSun,
  Info,
  Leaf,
  LockKeyhole,
  ShieldCheck,
  Wind,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { alertOnsets, type StatusTimelinePoint } from "@/lib/api/hazewatch";
import type { Forecast, Institution } from "@/lib/api/types";
import { loadLiteOverviewData } from "@/lib/data/source";
import { attributionLine, formatLocation, localTime, peakTime, reliabilityNote } from "@/lib/ui/format";
import { getInstitutionDetailCopy } from "@/lib/ui/institutionDetailCopy";
import { useSelectedInstitution } from "@/lib/ui/institutionContext";
import { getLiteRiskStatus } from "@/lib/ui/status";
import { AppShell } from "./AppShell";

type ScreenData = Awaited<ReturnType<typeof loadLiteOverviewData>>;

/**
 * When the backend raised an alert it already tells us when the threshold is
 * expected to be crossed, so the client never re-derives it from a hardcoded
 * boundary. Without an alert there is no crossing to show.
 */
function thresholdCrossingAt(data: ScreenData): string | null {
  return data.alertResponse.alert?.threshold_crossed_at ?? null;
}

function ReliabilityLine({ forecast }: { forecast: Forecast }) {
  const note = reliabilityNote(forecast);
  if (!note) return null;

  return (
    <p className="mt-2 flex items-start gap-1.5 text-[11px] font-semibold text-amber-700">
      <AlertTriangle size={13} className="mt-0.5 flex-none" /> {note}
    </p>
  );
}

function RecentAlerts({ timeline, institution }: { timeline: StatusTimelinePoint[]; institution: Institution }) {
  const entries = alertOnsets(timeline);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><BellRing size={16} /> Recent alerts</h3>
        <Link href="/lite/alert-history" className="text-[11px] font-bold text-blue-600">View all alerts <ChevronRight className="inline" size={13} /></Link>
      </div>

      {entries.length === 0 ? (
        <p className="py-5 text-xs text-slate-500">No recent alerts for this institution.</p>
      ) : (
        <div className="divide-y divide-slate-100">
          {entries.slice(0, 3).map((point) => (
            <div key={point.at} className="grid grid-cols-[90px_84px_1fr_auto] items-center gap-3 py-3 text-[11px]">
              <span className="font-semibold text-slate-600">{localTime(point.alert!.triggered_at, institution.country)}</span>
              <span className="rounded-full bg-red-100 px-3 py-1 text-center text-[10px] font-extrabold text-red-600">Alert</span>
              <span className="text-slate-600">Air quality alert issued with {point.alert!.lead_time_hours}h warning lead time.</span>
              <span className="text-slate-400">Prepared · Not sent</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function LiteInstitutionDetail() {
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
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load institution detail.");
      });

    return () => {
      cancelled = true;
    };
  }, [institutionId]);

  if (error) {
    return (
      <AppShell activePage="institution-detail">
        <main className="p-8">
          <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
            <strong>Could not load Institution Detail.</strong>
            <p className="mt-2">{error}</p>
            <p className="mt-2">For an offline demo, set NEXT_PUBLIC_HAZE_DATA_MODE=mock.</p>
          </div>
        </main>
      </AppShell>
    );
  }

  if (!data) {
    return (
      <AppShell activePage="institution-detail">
        <main className="p-8 text-sm text-slate-500">
          Loading institution detail…
          <p className="mt-2 text-xs text-slate-400">The first request can take up to a minute if the demo server is waking from idle.</p>
        </main>
      </AppShell>
    );
  }

  return <Loaded data={data} />;
}

function Loaded({ data }: { data: ScreenData }) {
  const { institution, institutions, forecast, alertResponse, statusTimeline, health, at } = data;
  const status = useMemo(() => getLiteRiskStatus(forecast, alertResponse), [forecast, alertResponse]);
  const alert = alertResponse.alert;
  const copy = getInstitutionDetailCopy(institution.type);
  const crossingAt = thresholdCrossingAt(data);
  const isAlert = status === "alert";
  const reliability = reliabilityNote(forecast);
  const attribution = attributionLine(forecast.attribution);
  const peakAt = alert?.forecast_peak_at ?? forecast.peak.timestamp;

  return (
    <AppShell activePage="institution-detail" institutions={institutions} current={institution} health={health} at={at}>
      <main className="min-w-0 px-6 py-5 lg:px-7 lg:py-6">
        <Link href="/" className="text-[11px] font-bold text-blue-600">← Back to Overview</Link>

        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-[29px] font-extrabold tracking-tight text-ink">{institution.name}</h2>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
              <span>⌖ {formatLocation(institution)}</span>
              <span className="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 font-bold capitalize text-blue-600">{institution.type}</span>
              <span className="rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 font-bold text-violet-600">{institution.admin_region}</span>
            </div>
          </div>
        </div>

        {isAlert ? (
          <section className="mt-4 grid grid-cols-[80px_1fr_120px] items-center gap-5 rounded-2xl border border-red-300 bg-red-50/70 px-5 py-5">
            <div className="grid h-16 w-16 place-items-center rounded-full bg-red-100 text-red-600">
              <AlertTriangle size={35} fill="currentColor" />
            </div>
            <div>
              <span className="inline-flex rounded-full bg-red-500 px-3 py-1 text-[10px] font-extrabold text-white">FORECAST ALERT</span>
              <h3 className="mt-2 text-[23px] font-extrabold leading-tight text-red-600">Air quality is expected to become unhealthy.</h3>
              <p className="mt-2 text-xs text-slate-600">Highest impact expected around <strong>{peakTime(peakAt, institution.country)}</strong>.</p>
              {attribution && (
                <p className="mt-2 flex items-start gap-1.5 text-[11px] font-semibold text-slate-600">
                  <Wind size={13} className="mt-0.5 flex-none text-slate-400" /> {attribution}
                </p>
              )}
              <ReliabilityLine forecast={forecast} />
            </div>
            <div className="grid h-[86px] place-items-center rounded-2xl bg-white/45 text-orange-500">
              <div className="relative">
                <Building2 size={46} />
                <CloudSun className="absolute -right-6 -top-4 text-slate-400" size={31} />
              </div>
            </div>
          </section>
        ) : (
          <section className={`mt-4 rounded-2xl border px-5 py-5 ${status === "safe" ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
            <h3 className="text-base font-extrabold text-ink">{status === "safe" ? "No action is needed. Air quality is normal." : "No action is needed right now."}</h3>
            {status === "watch" && <p className="mt-1 text-xs text-slate-600">Conditions are being monitored and may change. We&rsquo;ll notify you if the status rises to Alert.</p>}
            {attribution && (
              <p className="mt-2 flex items-start gap-1.5 text-[11px] font-semibold text-slate-600">
                <Wind size={13} className="mt-0.5 flex-none text-slate-400" /> {attribution}
              </p>
            )}
          </section>
        )}

        {isAlert && alert && (
          <div className="mt-3 grid gap-3 xl:grid-cols-[1fr_1.15fr]">
            <section className="rounded-2xl border border-blue-200 bg-blue-50/55 p-5">
              <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><Info size={16} /> What this means</h3>
              <ul className="mt-3 space-y-2 pl-4 text-[11px] leading-5 text-slate-600">
                {copy.whatThisMeans.map((item) => <li key={item} className="list-disc">{item}</li>)}
              </ul>
            </section>

            <section className="rounded-2xl border border-orange-200 bg-orange-50/60 p-5">
              <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><CheckCircle2 size={16} /> What should we prepare?</h3>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {alert.recommended_actions.map((action, index) => (
                  <div key={`${action}-${index}`} className="flex min-h-[54px] items-center gap-3 rounded-xl border border-orange-200 bg-white/80 px-3 py-2.5 text-[11px] font-bold text-slate-700">
                    <span className={`grid h-8 w-8 flex-none place-items-center rounded-full ${index % 4 === 0 ? "bg-emerald-100 text-emerald-600" : index % 4 === 1 ? "bg-blue-100 text-blue-600" : index % 4 === 2 ? "bg-violet-100 text-violet-600" : "bg-orange-100 text-orange-600"}`}>
                      {index + 1}
                    </span>
                    {action}
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}

        <div className="mt-3 grid gap-3 xl:grid-cols-[1.55fr_1fr]">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><CloudSun size={16} /> Forecast outlook</h3>
            <div className="mt-5 grid grid-cols-[1fr_44px_1fr_44px_1fr] items-start text-center">
              <div>
                <p className="text-[11px] font-bold text-blue-600">Now</p>
                <div className="mx-auto mt-3 grid h-14 w-14 place-items-center rounded-full bg-blue-50 text-blue-600"><Building2 size={23} /></div>
                <p className="mt-3 text-[11px] font-extrabold text-slate-700">{forecast.current.aqi_category === "GOOD" ? "Normal monitoring" : "Conditions monitored"}</p>
                <p className="mt-1 text-[10px] leading-4 text-slate-500">Current conditions are being monitored.</p>
              </div>
              <div className="mt-12 h-px bg-slate-200" />
              <div>
                <p className="text-[11px] font-bold text-orange-600">Alert window</p>
                <div className="mx-auto mt-3 grid h-14 w-14 place-items-center rounded-full bg-orange-50 text-orange-600"><AlertTriangle size={24} /></div>
                <p className="mt-3 text-[11px] font-extrabold text-slate-700">{crossingAt ? "Unhealthy levels possible" : "No crossing forecast"}</p>
                <p className="mt-1 text-[10px] leading-4 text-slate-500">
                  {crossingAt
                    ? `Threshold expected to be crossed around ${localTime(crossingAt, institution.country)}.`
                    : "No threshold crossing is expected within the next 24 hours."}
                </p>
              </div>
              <div className="mt-12 h-px bg-slate-200" />
              <div>
                <p className="text-[11px] font-bold text-emerald-600">Later</p>
                <div className="mx-auto mt-3 grid h-14 w-14 place-items-center rounded-full bg-emerald-50 text-emerald-600"><Leaf size={24} /></div>
                <p className="mt-3 text-[11px] font-extrabold text-slate-700">Beyond the 24-hour outlook</p>
                <p className="mt-1 text-[10px] leading-4 text-slate-500">{copy.improving}</p>
              </div>
            </div>
          </section>

          <section className={`rounded-2xl border p-5 ${isAlert ? "border-violet-200 bg-violet-50/60" : "border-blue-200 bg-blue-50/50"}`}>
            {isAlert && alert ? (
              <>
                <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><ShieldCheck size={16} /> Alert ready for review</h3>
                <p className="mt-4 text-xs leading-5 text-slate-600">A message has been prepared for this institution&apos;s verified admin contact.</p>
                <p className="text-xs font-extrabold text-slate-700">It will not be sent until you confirm.</p>
                <div className="mt-5 grid grid-cols-2 gap-3">
                  <Link href="/lite/alert-review" className="rounded-xl bg-blue-600 px-4 py-3 text-center text-xs font-extrabold text-white shadow-sm hover:bg-blue-700">✉ Review Alert</Link>
                  <Link href="/lite/alert-history" className="rounded-xl border border-slate-300 bg-white px-4 py-3 text-center text-xs font-extrabold text-slate-700">View Alert History</Link>
                </div>
              </>
            ) : (
              <>
                <h3 className="text-sm font-extrabold text-ink">No alert requires review</h3>
                <p className="mt-2 text-xs leading-5 text-slate-600">Safe and Watch states remain informational only.</p>
              </>
            )}
          </section>
        </div>

        <div className="mt-3"><RecentAlerts timeline={statusTimeline} institution={institution} /></div>

        <div className="mt-3 flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-[10px] text-slate-500">
          <LockKeyhole size={13} /> Messages are sent only to an institution&apos;s verified admin contact. This prototype does not send messages to public or personal phone numbers.
        </div>

        <p className="mt-2 text-[9px] text-slate-400">
          {reliability
            ? "Reliability notice is shown because the API indicates this forecast is beyond the model's training range."
            : "Reliability notice appears only when the API indicates this forecast is beyond the model's training range."}
        </p>
      </main>
    </AppShell>
  );
}

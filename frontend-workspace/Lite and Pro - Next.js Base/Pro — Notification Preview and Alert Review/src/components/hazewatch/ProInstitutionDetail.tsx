"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CheckCircle2,
  Clock3,
  Flame,
  Gauge,
  Info,
  MapPinned,
  Send,
  ShieldCheck,
  TrendingUp,
  Users,
  Wind,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Alert, Forecast, Health, HotspotSummary, Institution } from "@/lib/api/types";
import { loadProInstitutionDetailData, PRO_HORIZON_HOURS } from "@/lib/data/source";
import { alertOnsets } from "@/lib/api/hazewatch";
import { useSelectedInstitution } from "@/lib/ui/institutionContext";
import { getRiskStatus, type LiteRiskStatus } from "@/lib/ui/status";
import { ALERT_THRESHOLD_PM25, GOOD_MAX_PM25, thresholdFor } from "@/lib/ui/threshold";
import { ProAppShell } from "./ProAppShell";

type ScreenData = Awaited<ReturnType<typeof loadProInstitutionDetailData>>;
type ViewStatus = LiteRiskStatus;

function peakTriggerValue(forecast: Forecast) {
  return forecast.peak.pm25_upper ?? forecast.peak.pm25;
}

/**
 * Status is `getRiskStatus`: alert presence decides Alert, `aqi_category`
 * decides Safe vs Watch. Comparing `peak.pm25_upper` against a local copy of
 * 35.5 would be a second implementation of the backend's alerting rule.
 */

function statusLabel(status: ViewStatus) {
  if (status === "alert") return "Alert";
  if (status === "watch") return "Watch";
  return "Safe";
}

function formatTime(iso?: string | null) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kuching",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

function warningWindow(alert: Alert | null | undefined, forecast: Forecast) {
  const trigger = thresholdFor(alert);
  const crossed = alert?.threshold_crossed_at
    ?? forecast.forecast.find((point) => (point.pm25_upper ?? point.pm25) >= trigger)?.timestamp;
  const peak = alert?.forecast_peak_at ?? forecast.peak.timestamp;
  if (!crossed) return `around ${formatTime(peak)}`;
  return `${formatTime(crossed)}–${formatTime(peak)}`;
}

function iconForType(type: Institution["type"]) {
  if (type === "hospital") return "✚";
  if (type === "authority") return "◆";
  return "🏫";
}

function typeLabel(type: Institution["type"]) {
  if (type === "hospital") return "Hospital";
  if (type === "authority") return "Authority";
  return "School";
}

function alertHeroCopy(institution: Institution, status: ViewStatus) {
  if (status === "safe") return "No significant haze impact is expected.";
  if (status === "watch") return "Haze conditions may worsen over the forecast period.";
  return "High haze impact expected";
}

function reliabilitySummary(forecast: Forecast) {
  if (forecast.uncertainty?.any_point_beyond_training_range) {
    return {
      title: "May be less reliable",
      body: "Part of this forecast is outside the model’s usual trained range.",
      tone: "warning" as const,
    };
  }
  return {
    title: "Within trained range",
    body: "No beyond-training-range flag is active for this forecast.",
    tone: "normal" as const,
  };
}

function ForecastChart({ forecast }: { forecast: Forecast }) {
  const points = forecast.forecast;
  const allValues = points.flatMap((point) => [
    point.pm25_lower ?? point.pm25,
    point.pm25_p50 ?? point.pm25,
    point.pm25_upper ?? point.pm25,
  ]);
  const maxValue = Math.max(55.4, ...allValues) * 1.12;
  const width = 620;
  const height = 250;
  const padX = 34;
  const padTop = 20;
  const padBottom = 38;
  const innerWidth = width - padX * 2;
  const innerHeight = height - padTop - padBottom;

  const x = (index: number) => padX + (index / Math.max(1, points.length - 1)) * innerWidth;
  const y = (value: number) => padTop + (1 - value / maxValue) * innerHeight;
  const poly = (selector: (p: Forecast["forecast"][number]) => number) => points.map((p, i) => `${x(i)},${y(selector(p))}`).join(" ");
  const upper = points.map((p, i) => `${x(i)},${y(p.pm25_upper ?? p.pm25)}`);
  const lower = [...points].reverse().map((p, reverseIndex) => {
    const i = points.length - 1 - reverseIndex;
    return `${x(i)},${y(p.pm25_lower ?? p.pm25)}`;
  });
  const band = [...upper, ...lower].join(" ");
  const safeY = y(GOOD_MAX_PM25);
  const alertY = y(ALERT_THRESHOLD_PM25);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-extrabold text-slate-800">PM2.5 Forecast <Info size={13} /></h3>
        <div className="flex gap-1 text-[10px] font-bold">
          <span className="rounded-lg bg-blue-600 px-3 py-1.5 text-white">{PRO_HORIZON_HOURS} Hours</span>
        </div>
      </div>
      <div className="mt-3 overflow-hidden rounded-xl border border-slate-100 bg-gradient-to-b from-red-50 via-amber-50 to-emerald-50/80">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-[250px] w-full" role="img" aria-label="PM2.5 forecast with p10 to p90 uncertainty band">
          <line x1={padX} y1={alertY} x2={width - padX} y2={alertY} stroke="#ef4444" strokeOpacity="0.25" strokeDasharray="5 5" />
          <line x1={padX} y1={safeY} x2={width - padX} y2={safeY} stroke="#f59e0b" strokeOpacity="0.25" strokeDasharray="5 5" />
          <text x="10" y={Math.max(15, alertY - 6)} fontSize="10" fontWeight="700" fill="#dc2626">ALERT</text>
          <text x="10" y={Math.max(28, safeY - 6)} fontSize="10" fontWeight="700" fill="#d97706">WATCH</text>
          <text x="10" y={height - 22} fontSize="10" fontWeight="700" fill="#059669">SAFE</text>

          <polygon points={band} fill="#7c3aed" fillOpacity="0.12" />
          <polyline points={poly((p) => p.pm25_p50 ?? p.pm25)} fill="none" stroke="#7c3aed" strokeWidth="2" strokeDasharray="5 5" />
          <polyline points={poly((p) => p.pm25)} fill="none" stroke="#ef4444" strokeWidth="3.5" strokeLinejoin="round" strokeLinecap="round" />
          {points.map((p, i) => (
            <g key={p.timestamp}>
              <circle cx={x(i)} cy={y(p.pm25)} r="4.5" fill="#ef4444" />
              <text x={x(i)} y={height - 10} textAnchor="middle" fontSize="9" fill="#64748b">+{p.lead_hours}h</text>
            </g>
          ))}
          <text x={x(Math.max(0, points.findIndex((p) => p.timestamp === forecast.peak.timestamp)))} y={Math.max(14, y(forecast.peak.pm25) - 10)} textAnchor="middle" fontSize="10" fontWeight="700" fill="#dc2626">
            {(forecast.peak.pm25_upper ?? forecast.peak.pm25).toFixed(1)}
          </text>
        </svg>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[10px]">
        <p className="font-bold text-red-600">Trend: {points.at(-1)?.pm25 && points[0]?.pm25 && points.at(-1)!.pm25 > points[0].pm25 ? "Increasing ↗" : "Variable"}</p>
        <p className="text-slate-500">Shaded band = p10–p90 · dashed = p50 · red = mean forecast</p>
      </div>
    </section>
  );
}

function SourceMap({ institution, forecast, hotspotSummary }: { institution: Institution; forecast: Forecast; hotspotSummary: HotspotSummary }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3">
        <MapPinned size={15} />
        <h3 className="text-sm font-extrabold text-slate-800">Haze Source &amp; Direction</h3>
      </div>
      <div className="relative h-[250px] overflow-hidden bg-[#bfe4f6]">
        <div className="absolute -left-[12%] top-[18%] h-[88%] w-[62%] rounded-[45%] bg-[#dce8c9]" />
        <div className="absolute right-[-12%] top-[20%] h-[85%] w-[62%] rounded-[45%] bg-[#d8efcb]" />
        <p className="absolute left-5 top-6 z-10 text-lg font-black text-slate-800">WEST KALIMANTAN</p>
        <p className="absolute right-5 top-6 z-10 text-lg font-black text-slate-800">SARAWAK</p>
        <svg className="absolute inset-0 z-[5] h-full w-full" viewBox="0 0 500 260" aria-hidden="true">
          <defs>
            <linearGradient id="detailHaze" x1="0" x2="1"><stop offset="0%" stopColor="#f4b47e" stopOpacity=".42" /><stop offset="100%" stopColor="#f35a41" stopOpacity=".85" /></linearGradient>
            <marker id="detailHead" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#f35a41" /></marker>
          </defs>
          <path d="M125 145 C230 100, 305 185, 405 135" fill="none" stroke="url(#detailHaze)" strokeWidth="30" strokeLinecap="round" markerEnd="url(#detailHead)" />
          {[{x:80,y:72},{x:105,y:100},{x:90,y:150},{x:135,y:182},{x:120,y:125}].map((dot, index) => <circle key={index} cx={dot.x} cy={dot.y} r="5" fill="#f04b32" />)}
        </svg>
        <span className="absolute bottom-4 left-4 z-20 rounded-lg bg-white px-2 py-1 text-[10px] font-bold text-red-600 shadow">🔥 {forecast.attribution.contributing_hotspot_count || hotspotSummary.count} contributing hotspots</span>
        <span className="absolute right-4 top-[43%] z-20 rounded-lg bg-white px-2 py-1 text-[10px] font-bold text-blue-600 shadow">{iconForType(institution.type)} {institution.city} · You are here</span>
      </div>
    </section>
  );
}

function RecentAlerts({ alertHistory, currentStatus }: { alertHistory: Alert[]; currentStatus: ViewStatus }) {
  const rows = alertHistory.slice(0, 3);
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-extrabold text-slate-800">Recent Alerts</h3>
        <Link href="/pro/alert-history" className="text-[10px] font-bold text-blue-600">View Alert History →</Link>
      </div>
      <div className="mt-3 space-y-2">
        {rows.length ? rows.map((alert) => (
          <div key={alert.alert_id} className="grid grid-cols-[44px_72px_1fr] items-center gap-2 rounded-lg border border-slate-100 px-2 py-2 text-[10px]">
            <span className="text-slate-500">{formatTime(alert.triggered_at)}</span>
            <span className="rounded-full bg-red-50 px-2 py-1 text-center font-bold text-red-600">Alert</span>
            <span className="text-slate-600">Forecast alert issued with {alert.lead_time_hours}h warning lead time.</span>
          </div>
        )) : (
          <div className="rounded-lg border border-slate-100 px-3 py-3 text-[10px] text-slate-500">No recorded alert entries yet. Current forecast status: <strong>{statusLabel(currentStatus)}</strong>.</div>
        )}
      </div>
    </section>
  );
}

export function ProInstitutionDetail() {
  const [data, setData] = useState<ScreenData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { institutionId } = useSelectedInstitution();

  useEffect(() => {
    let cancelled = false;
    setError(null);
    loadProInstitutionDetailData(institutionId)
      .then((result) => { if (!cancelled) setData(result); })
      .catch((err: unknown) => { if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load institution detail."); });
    return () => { cancelled = true; };
  }, [institutionId]);

  if (error) {
    return <ProAppShell activePage="institutions" scopeLabel="Institution View"><main className="p-8"><div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">{error}</div></main></ProAppShell>;
  }

  if (!data) {
    return <ProAppShell activePage="institutions" scopeLabel="Institution View"><main className="p-8"><div className="h-64 animate-pulse rounded-2xl bg-slate-100" /></main></ProAppShell>;
  }

  const { health, institutions, institution, forecast, alertResponse, statusTimeline, hotspotSummary, at } = data;
  const alert = alertResponse.alert;
  const status = getRiskStatus(forecast, alert);
  const peak = peakTriggerValue(forecast);
  const reliability = reliabilitySummary(forecast);
  const warningLead = alert?.lead_time_hours
    ?? forecast.forecast.find((p) => (p.pm25_upper ?? p.pm25) >= thresholdFor(alert))?.lead_hours
    ?? null;
  const actions = status === "alert" ? (alert?.recommended_actions ?? []) : [];
  const forecastWindow = warningWindow(alert, forecast);

  return (
    <ProAppShell activePage="institutions" scopeLabel="Institution View" forecastLabel={`Next ${PRO_HORIZON_HOURS} Hours`} institutions={institutions} current={institution} health={health} at={at}>
      <main className="min-w-0 bg-white px-5 py-5 lg:px-7">
        <div className="mx-auto max-w-[1500px]">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <Link href="/pro/live-monitor" className="text-xs font-bold text-blue-600">← Regional Overview</Link>
              <h2 className="mt-2 text-[28px] font-extrabold tracking-tight text-ink">{institution.name}</h2>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                <span>⌖ {institution.city}, {institution.admin_region}, {institution.country_name}</span>
                <span className="rounded-full bg-blue-50 px-2 py-1 font-bold text-blue-600">{typeLabel(institution.type)}</span>
                <span className="rounded-full bg-violet-50 px-2 py-1 font-bold text-violet-600">{institution.admin_region}</span>
              </div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600 shadow-sm">Viewing: <strong className="ml-2 text-slate-800">{institution.name}</strong>⌄</div>
          </div>

          <section className={`mt-3 rounded-2xl border p-5 ${status === "alert" ? "border-red-300 bg-red-50" : status === "watch" ? "border-amber-200 bg-amber-50" : "border-emerald-200 bg-emerald-50"}`}>
            <div className="grid gap-4 md:grid-cols-[72px_1fr_auto] md:items-center">
              <div className={`grid h-16 w-16 place-items-center rounded-full ${status === "alert" ? "bg-red-100 text-red-600" : status === "watch" ? "bg-amber-100 text-amber-600" : "bg-emerald-100 text-emerald-600"}`}><AlertTriangle size={34} /></div>
              <div>
                <span className={`inline-flex rounded-full px-3 py-1 text-[10px] font-extrabold uppercase ${status === "alert" ? "bg-red-500 text-white" : status === "watch" ? "bg-amber-400 text-white" : "bg-emerald-500 text-white"}`}>{statusLabel(status)}</span>
                <h3 className={`mt-2 text-[24px] font-extrabold ${status === "alert" ? "text-red-600" : status === "watch" ? "text-amber-700" : "text-emerald-700"}`}>{alertHeroCopy(institution, status)}</h3>
                <p className="mt-1 text-xs text-slate-600">Alerting is based on the upper prediction band. Peak trigger value: <strong>{peak.toFixed(1)} µg/m³</strong>.</p>
                {forecast.attribution.transboundary && <p className="mt-1 text-xs text-slate-600">Haze associated with detected hotspots in {forecast.attribution.dominant_source_region ?? "the source region"} is forecast to affect {institution.city}.</p>}
              </div>
              <div className="text-right">
                <p className="text-[10px] text-slate-500">Expected high-impact window</p>
                <p className="mt-1 flex items-center justify-end gap-1 text-sm font-extrabold text-red-600"><Clock3 size={14} /> {forecastWindow}</p>
              </div>
            </div>
          </section>

          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-2xl border border-blue-100 bg-blue-50/70 p-4"><div className="flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-full bg-blue-100 text-blue-700"><Gauge size={20} /></div><div><p className="text-[10px] text-slate-500">Current PM2.5</p><p className="text-2xl font-extrabold text-blue-700">{forecast.current.pm25.toFixed(1)}<span className="ml-1 text-sm">µg/m³</span></p><p className="text-[9px] text-slate-500">{forecast.current.source.replaceAll("_", " ")}</p></div></div></div>
            <div className="rounded-2xl border border-violet-100 bg-violet-50/70 p-4"><div className="flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-full bg-violet-100 text-violet-700"><TrendingUp size={20} /></div><div><p className="text-[10px] text-slate-500">Forecast trigger peak</p><p className="text-2xl font-extrabold text-violet-700">{peak.toFixed(1)}<span className="ml-1 text-sm">µg/m³</span></p><p className="text-[9px] text-slate-500">p90 upper prediction band</p></div></div></div>
            <div className="rounded-2xl border border-orange-100 bg-orange-50/80 p-4"><div className="flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-full bg-orange-100 text-orange-700"><Clock3 size={20} /></div><div><p className="text-[10px] text-slate-500">Warning lead time</p><p className="text-2xl font-extrabold text-orange-600">{warningLead ?? "—"}<span className="ml-1 text-sm">hours</span></p><p className="text-[9px] text-slate-500">time before threshold crossing</p></div></div></div>
            <div className="rounded-2xl border border-red-100 bg-red-50/70 p-4"><div className="flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-full bg-red-100 text-red-700"><AlertTriangle size={20} /></div><div><p className="text-[10px] text-slate-500">Forecast Status</p><p className="text-2xl font-extrabold text-red-600">{statusLabel(status)}</p><p className="text-[9px] text-slate-500">Safe ≤{GOOD_MAX_PM25} · Watch {GOOD_MAX_PM25 + 0.1}–{ALERT_THRESHOLD_PM25 - 0.1} · Alert ≥{ALERT_THRESHOLD_PM25}</p></div></div></div>
          </div>

          <div className="mt-3 grid gap-3 xl:grid-cols-[1.35fr_.9fr_1fr]">
            <ForecastChart forecast={forecast} />

            <section className="rounded-2xl border border-slate-200 bg-orange-50/50 p-4">
              <h3 className="flex items-center gap-2 text-sm font-extrabold text-slate-800">What’s Driving This Risk? <Info size={13} /></h3>
              <div className="mt-3 space-y-2">
                <div className="rounded-xl border border-orange-100 bg-white p-3"><div className="flex gap-3"><Flame className="mt-0.5 text-orange-500" size={18} /><div><p className="text-xs font-extrabold text-red-600">Fire Activity</p><p className="mt-1 text-[10px] text-slate-500">{forecast.attribution.contributing_hotspot_count || hotspotSummary.count} contributing hotspots in the source region.</p></div></div></div>
                <div className="rounded-xl border border-orange-100 bg-white p-3"><div className="flex gap-3"><Wind className="mt-0.5 text-emerald-600" size={18} /><div><p className="text-xs font-extrabold text-emerald-700">Haze Movement</p><p className="mt-1 text-[10px] text-slate-500">{forecast.attribution.transboundary ? `Cross-border transport toward ${institution.admin_region}` : `Transport within ${institution.admin_region}`}.</p>{forecast.attribution.estimated_transport_hours != null && <p className="text-[10px] text-slate-500">Estimated transport: {forecast.attribution.estimated_transport_hours} hours.</p>}</div></div></div>
                <div className="rounded-xl border border-orange-100 bg-white p-3"><div className="flex gap-3"><Gauge className="mt-0.5 text-violet-600" size={18} /><div><p className="text-xs font-extrabold text-violet-700">PM2.5 Forecast</p><p className="mt-1 text-[10px] text-slate-500">Upper-band trigger peak {peak.toFixed(1)} µg/m³.</p></div></div></div>
              </div>
              <Link href="/pro/live-monitor" className="mt-4 inline-flex items-center gap-1 text-[10px] font-bold text-blue-600">View on regional map <ArrowRight size={11} /></Link>
            </section>

            <SourceMap institution={institution} forecast={forecast} hotspotSummary={hotspotSummary} />
          </div>

          <div className="mt-3 grid gap-3 xl:grid-cols-[1.05fr_.72fr_1.08fr]">
            <section className="rounded-2xl border border-amber-200 bg-amber-50/70 p-4">
              <div className="flex items-start justify-between gap-2"><div><h3 className="text-sm font-extrabold text-slate-800">Recommended Preparedness <Info size={13} className="inline" /></h3><p className="mt-1 text-[9px] text-slate-500">Actions are supplied by the alert API. Final decisions remain with the institution.</p></div>{status === "alert" && <span className="rounded-full border border-orange-300 bg-white px-2 py-1 text-[8px] font-extrabold text-orange-600">ALERT ONLY</span>}</div>
              {status === "alert" ? (
                <>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                    {actions.slice(0, 4).map((action, index) => <div key={action} className="rounded-lg border border-orange-200 bg-white p-2 text-[9px] text-slate-600"><strong className="block text-orange-600">{String(index + 1).padStart(2, "0")}</strong>{action}</div>)}
                    {!actions.length && <div className="col-span-full rounded-lg border border-orange-200 bg-white p-3 text-[10px] text-slate-500">No recommended actions were provided by the alert endpoint.</div>}
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2"><Link href="/pro/notification-preview" className="flex items-center justify-center gap-2 rounded-lg bg-orange-500 px-3 py-2.5 text-[10px] font-extrabold text-white"><Send size={13} /> Preview Notification</Link><Link href="/pro/alert-history" className="flex items-center justify-center rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-[10px] font-extrabold text-slate-700">View Alert Details →</Link></div>
                </>
              ) : (
                <div className="mt-3 rounded-xl border border-amber-100 bg-white p-4 text-[11px] text-slate-600">{status === "safe" ? "No action is needed. Air quality is normal." : "No action is needed right now. Conditions are being monitored and may change. We’ll notify you if the status rises to Alert."}</div>
              )}
            </section>

            <section className={`rounded-2xl border p-4 ${reliability.tone === "warning" ? "border-amber-200 bg-amber-50" : "border-blue-100 bg-blue-50/70"}`}>
              <h3 className="flex items-center gap-2 text-sm font-extrabold text-slate-800">Forecast Reliability <Info size={13} /></h3>
              <p className={`mt-3 text-xl font-extrabold ${reliability.tone === "warning" ? "text-amber-700" : "text-blue-700"}`}>{reliability.title}</p>
              <p className="mt-1 text-[10px] leading-5 text-slate-500">{reliability.body}</p>
              {forecast.uncertainty && <div className="mt-4 grid grid-cols-3 gap-1"><div className="h-6 rounded-t bg-blue-300" /><div className="h-9 rounded-t bg-blue-400" /><div className="h-12 rounded-t bg-blue-500" /></div>}
              <p className="mt-2 text-[9px] text-slate-500">p{forecast.uncertainty?.lower_percentile ?? 10}–p{forecast.uncertainty?.upper_percentile ?? 90} prediction spread</p>
            </section>

            <RecentAlerts alertHistory={alertOnsets(statusTimeline).map((p) => p.alert!)} currentStatus={status} />
          </div>

          {status === "alert" && (
            <section className="mt-3 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-4">
              <div className="flex items-center gap-3"><div className="grid h-10 w-10 place-items-center rounded-full bg-white text-emerald-700"><ShieldCheck size={19} /></div><div><h3 className="text-base font-extrabold text-emerald-900">Alert Ready for Review</h3><p className="mt-1 text-[10px] text-slate-600">A notification can be prepared for this institution’s verified contact. It will not be sent until an authorized user confirms.</p></div></div>
              <Link href="/pro/notification-preview" className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-3 text-[10px] font-extrabold text-white"><Send size={13} /> Preview Notification</Link>
            </section>
          )}

          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[9px] text-slate-400">
            <span>PM2.5 source: {forecast.current.source.replaceAll("_", " ")} · replay clock {health.clock ? formatTime(health.clock) : "local"}</span>
            <span>{forecast.attribution.transboundary ? "Transboundary attribution active" : "No cross-border attribution for this institution"}</span>
          </div>
        </div>
      </main>
    </ProAppShell>
  );
}

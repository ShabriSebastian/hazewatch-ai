"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  Clock3,
  Filter,
  Gauge,
  Info,
  RotateCcw,
  ShieldAlert,
  TrendingUp,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { loadProAlertHistoryData } from "@/lib/data/source";
import type { ProHistoryEvent, ProHistoryStatus } from "@/lib/data/proAlertHistoryMock";
import { ProAppShell } from "./ProAppShell";

type ScreenData = Awaited<ReturnType<typeof loadProAlertHistoryData>>;
type FilterStatus = "all" | ProHistoryStatus;

function formatClock(iso: string) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kuching",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

function formatDay(iso: string) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kuching",
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(iso));
}

function statusLabel(status: ProHistoryStatus) {
  return status === "alert" ? "Alert" : status === "watch" ? "Watch" : "Safe";
}

function statusClasses(status: ProHistoryStatus) {
  if (status === "alert") return "bg-red-100 text-red-600";
  if (status === "watch") return "bg-amber-100 text-amber-700";
  return "bg-emerald-100 text-emerald-700";
}

function dotClass(status: ProHistoryStatus) {
  if (status === "alert") return "bg-red-500";
  if (status === "watch") return "bg-amber-500";
  return "bg-emerald-500";
}

function StatusIcon({ status, size = 18 }: { status: ProHistoryStatus; size?: number }) {
  if (status === "safe") return <Check size={size} />;
  if (status === "watch") return <span className="text-lg font-black">!</span>;
  return <AlertTriangle size={size} />;
}

function RiskTrend({ events }: { events: ProHistoryEvent[] }) {
  const points = [...events].reverse().filter((event) => event.forecastPeak != null);
  const values = points.map((event) => event.forecastPeak ?? 0);
  const max = Math.max(60, ...values) * 1.08;
  const min = 0;
  const w = 640;
  const h = 250;
  const left = 46;
  const right = 24;
  const top = 24;
  const bottom = 38;
  const plotW = w - left - right;
  const plotH = h - top - bottom;
  const xy = values.map((value, index) => ({
    x: left + (index * plotW) / Math.max(1, values.length - 1),
    y: top + ((max - value) / (max - min)) * plotH,
    value,
  }));
  const path = xy.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
  const y12 = top + ((max - 12) / (max - min)) * plotH;
  const y355 = top + ((max - 35.5) / (max - min)) * plotH;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-extrabold text-slate-800">Risk Trend</h3>
      <p className="mt-1 text-[10px] text-slate-500">Forecast trigger values and status changes over the selected period.</p>
      <div className="mt-3 overflow-hidden rounded-xl border border-slate-100 bg-slate-50/60">
        <svg viewBox={`0 0 ${w} ${h}`} className="h-[260px] w-full" role="img" aria-label="Forecast risk trend">
          <rect x={left} y={top} width={plotW} height={Math.max(0, y355 - top)} fill="#fff1f2" />
          <rect x={left} y={y355} width={plotW} height={Math.max(0, y12 - y355)} fill="#fffbeb" />
          <rect x={left} y={y12} width={plotW} height={Math.max(0, top + plotH - y12)} fill="#ecfdf5" />
          <line x1={left} x2={left + plotW} y1={y355} y2={y355} stroke="#f59e0b" strokeDasharray="5 5" opacity=".55" />
          <line x1={left} x2={left + plotW} y1={y12} y2={y12} stroke="#10b981" strokeDasharray="5 5" opacity=".55" />
          <text x={10} y={top + 12} fill="#dc2626" fontSize="10" fontWeight="700">ALERT</text>
          <text x={10} y={y355 + 14} fill="#d97706" fontSize="10" fontWeight="700">WATCH</text>
          <text x={10} y={top + plotH - 4} fill="#059669" fontSize="10" fontWeight="700">SAFE</text>
          {xy.length > 1 && <path d={path} fill="none" stroke="#ef4444" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />}
          {xy.map((point, index) => (
            <g key={`${point.x}-${point.y}`}>
              <circle cx={point.x} cy={point.y} r="5" fill="#ef4444" />
              <text x={point.x} y={point.y - 10} textAnchor="middle" fill="#64748b" fontSize="10" fontWeight="700">{point.value.toFixed(1)}</text>
              <text x={point.x} y={h - 14} textAnchor="middle" fill="#94a3b8" fontSize="9">{index + 1}</text>
            </g>
          ))}
        </svg>
      </div>
      <p className="mt-2 text-[9px] text-slate-400">Safe ≤12.0 · Watch 12.1–35.4 · Alert ≥35.5 µg/m³. Alerting uses the upper prediction band.</p>
    </section>
  );
}

function Progression({ events }: { events: ProHistoryEvent[] }) {
  const latestByStatus = ["safe", "watch", "alert"].map((status) =>
    events.find((event) => event.status === status),
  );
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4">
      <h3 className="flex items-center gap-1 text-sm font-extrabold text-slate-800">Alert Progression <Info size={13} /></h3>
      <div className="mt-6 flex items-center justify-between gap-2">
        {(["safe", "watch", "alert"] as ProHistoryStatus[]).map((status, index) => {
          const event = latestByStatus[index];
          return (
            <div key={status} className="contents">
              <div className="min-w-0 text-center">
                <div className={`mx-auto grid h-11 w-11 place-items-center rounded-full ${statusClasses(status)}`}><StatusIcon status={status} /></div>
                <p className="mt-2 text-[10px] font-extrabold uppercase text-slate-700">{statusLabel(status)}</p>
                <p className="mt-1 text-[9px] text-slate-400">{event ? formatDay(event.timestamp).replace(/ \d{4}$/, "") : "—"}</p>
              </div>
              {index < 2 && <ArrowRight size={16} className="shrink-0 text-slate-300" />}
            </div>
          );
        })}
      </div>
      <div className="mt-5 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-center text-[9px] font-bold text-red-600">↗ Current trend: worsening</div>
    </section>
  );
}

function WhatChanged({ selected, previous }: { selected: ProHistoryEvent; previous?: ProHistoryEvent }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4">
      <h3 className="flex items-center gap-1 text-sm font-extrabold text-slate-800">What Changed? <Info size={13} /></h3>
      <div className="mt-3 space-y-2 text-[10px]">
        <div className="flex justify-between gap-4"><span className="text-slate-500">Previous status</span><strong>{previous ? statusLabel(previous.status) : "—"} → {statusLabel(selected.status)}</strong></div>
        <div className="flex justify-between gap-4"><span className="text-slate-500">Forecast peak</span><strong>{previous?.forecastPeak?.toFixed(1) ?? "—"} → {selected.forecastPeak?.toFixed(1) ?? "—"} µg/m³</strong></div>
        <div className="flex justify-between gap-4"><span className="text-slate-500">Source area</span><strong className="text-right">{selected.sourceArea ?? "—"}</strong></div>
        <div className="flex justify-between gap-4"><span className="text-slate-500">Estimated transport</span><strong>{previous?.transportHours ?? "—"} → {selected.transportHours ?? "—"}</strong></div>
        <div className="flex justify-between gap-4"><span className="text-slate-500">Haze direction</span><strong>{selected.direction ?? "—"}</strong></div>
      </div>
      <div className="mt-4 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-[9px] leading-4 text-slate-600">The event summary only reflects fields available from the API or the swappable demo fixture.</div>
    </section>
  );
}

function AlertDetails({ event, institutionName }: { event: ProHistoryEvent; institutionName: string }) {
  const state = event.notificationState === "prepared" ? "Prepared · not sent" : event.notificationState === "sent" ? "Sent to verified admin contact" : event.notificationState === "monitoring" ? "Monitoring only" : "No action needed";
  return (
    <section className="rounded-2xl border border-red-200 bg-red-50/40 p-4">
      <h3 className="text-sm font-extrabold text-slate-800">Alert Details</h3>
      <div className="mt-3 flex items-center gap-3 border-b border-red-100 pb-3">
        <div className="grid h-10 w-10 place-items-center rounded-full bg-red-100 text-red-600"><ShieldAlert size={19} /></div>
        <div><p className={`inline-flex rounded-full px-2 py-1 text-[9px] font-extrabold ${statusClasses(event.status)}`}>{statusLabel(event.status)}</p><p className="mt-1 text-[9px] text-slate-500">{formatDay(event.timestamp)} · {formatClock(event.timestamp)}</p></div>
      </div>
      <div className="mt-3 space-y-2 text-[10px]">
        <div className="flex justify-between gap-4"><span className="text-slate-500">Institution</span><strong className="text-right">{institutionName}</strong></div>
        <div className="flex justify-between gap-4"><span className="text-slate-500">Forecast trigger peak</span><strong className="text-red-600">{event.forecastPeak?.toFixed(1) ?? "—"} µg/m³</strong></div>
        <div className="flex justify-between gap-4"><span className="text-slate-500">Associated source area</span><strong className="text-right">{event.sourceArea ?? "—"}</strong></div>
        <div className="flex justify-between gap-4"><span className="text-slate-500">Haze direction</span><strong>{event.direction ?? "—"}</strong></div>
        <div className="flex justify-between gap-4"><span className="text-slate-500">Notification state</span><strong className="text-right">{state}</strong></div>
      </div>
      {event.status === "alert" && <p className="mt-4 border-t border-red-100 pt-3 text-[9px] font-bold text-red-600">It will not be sent until an authorized user confirms.</p>}
      <div className="mt-4 grid grid-cols-2 gap-2">
        <Link href="/pro/institutions" className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-center text-[9px] font-extrabold text-slate-700">View Institution</Link>
        {event.status === "alert" ? <Link href="/pro/notification-preview" className="rounded-lg bg-blue-600 px-3 py-2.5 text-center text-[9px] font-extrabold text-white">Preview Notification</Link> : <span className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2.5 text-center text-[9px] font-bold text-slate-400">No send action</span>}
      </div>
    </section>
  );
}

export function ProAlertHistory() {
  const [data, setData] = useState<ScreenData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterStatus>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    loadProAlertHistoryData().then((loaded) => {
      setData(loaded);
      setSelectedId(loaded.historyEvents[0]?.id ?? null);
    }).catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  const filtered = useMemo(() => {
    if (!data) return [];
    return filter === "all" ? data.historyEvents : data.historyEvents.filter((event) => event.status === filter);
  }, [data, filter]);

  const selected = data?.historyEvents.find((event) => event.id === selectedId) ?? data?.historyEvents[0] ?? null;
  const selectedIndex = selected && data ? data.historyEvents.findIndex((event) => event.id === selected.id) : -1;
  const previous = selectedIndex >= 0 && data ? data.historyEvents[selectedIndex + 1] : undefined;

  if (error) return <ProAppShell activePage="alert-history"><main className="p-8"><div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">Unable to load alert history: {error}</div></main></ProAppShell>;
  if (!data || !selected) return <ProAppShell activePage="alert-history"><main className="p-8 text-sm text-slate-500">Loading alert history…</main></ProAppShell>;

  const currentStatus = data.historyEvents[0]?.status ?? selected.status;
  const highestPeak = Math.max(...data.historyEvents.map((event) => event.forecastPeak ?? 0));
  const latestWatch = data.historyEvents.find((event) => event.status === "watch");

  return (
    <ProAppShell activePage="alert-history" scopeLabel="Institution View" forecastLabel="Next 12 Hours">
      <main className="min-w-0 bg-white">
        <div className="px-6 py-5 xl:px-8">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div><h2 className="text-[30px] font-extrabold tracking-tight text-ink">Alert History</h2><p className="mt-1 text-xs text-slate-500">Review past alerts and changes in haze risk over time.</p></div>
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-500">Viewing: <strong className="ml-2 text-slate-800">{data.institution.name}</strong></div>
          </div>

          <section className="mt-4 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50/50 p-3">
            <span className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-[10px] font-semibold text-slate-600"><Clock3 size={13} /> Scenario window</span>
            <div className="flex flex-wrap gap-2">
              {(["all", "safe", "watch", "alert"] as FilterStatus[]).map((status) => <button key={status} onClick={() => setFilter(status)} className={`rounded-lg px-3 py-2 text-[10px] font-extrabold capitalize ${filter === status ? "bg-blue-600 text-white" : "border border-slate-200 bg-white text-slate-600"}`}>{status === "all" ? "All statuses" : statusLabel(status)}</button>)}
            </div>
            <button onClick={() => setFilter("all")} className="ml-auto flex items-center gap-1 text-[10px] font-bold text-slate-500"><RotateCcw size={12} /> Reset Filters</button>
          </section>

          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-2xl border border-blue-100 bg-blue-50/70 p-4"><div className="flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-full bg-blue-100 text-blue-700"><Filter size={19} /></div><div><p className="text-[10px] text-slate-500">Recorded Events</p><p className="text-2xl font-extrabold text-blue-700">{data.historyEvents.length}</p><p className="text-[9px] text-slate-500">in current replay scenario</p></div></div></div>
            <div className="rounded-2xl border border-red-100 bg-red-50/70 p-4"><div className="flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-full bg-red-100 text-red-700"><AlertTriangle size={19} /></div><div><p className="text-[10px] text-slate-500">Current Status</p><p className="text-2xl font-extrabold text-red-600">{statusLabel(currentStatus)}</p><p className="text-[9px] text-slate-500">forecast-based operational state</p></div></div></div>
            <div className="rounded-2xl border border-violet-100 bg-violet-50/70 p-4"><div className="flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-full bg-violet-100 text-violet-700"><TrendingUp size={19} /></div><div><p className="text-[10px] text-slate-500">Highest Trigger Peak</p><p className="text-2xl font-extrabold text-violet-700">{highestPeak.toFixed(1)}<span className="ml-1 text-sm">µg/m³</span></p><p className="text-[9px] text-slate-500">upper prediction band</p></div></div></div>
            <div className="rounded-2xl border border-orange-100 bg-orange-50/70 p-4"><div className="flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-full bg-orange-100 text-orange-700"><Gauge size={19} /></div><div><p className="text-[10px] text-slate-500">Latest Change</p><p className="text-xl font-extrabold text-orange-600">{latestWatch ? "Watch → Alert" : `→ ${statusLabel(currentStatus)}`}</p><p className="text-[9px] text-slate-500">human action only when Alert</p></div></div></div>
          </div>

          <div className="mt-3 grid gap-3 xl:grid-cols-[1.35fr_.75fr_.78fr]">
            <RiskTrend events={data.historyEvents} />
            <div className="space-y-3"><Progression events={data.historyEvents} /><WhatChanged selected={selected} previous={previous} /></div>
            <AlertDetails event={selected} institutionName={data.institution.name} />
          </div>

          <section className="mt-3 rounded-2xl border border-slate-200 bg-white p-4">
            <div className="flex items-center justify-between gap-3"><div><h3 className="text-sm font-extrabold text-slate-800">Alert Timeline</h3><p className="mt-1 text-[10px] text-slate-500">Chronological history of major forecast-state changes.</p></div><span className="text-[9px] text-slate-400">{filtered.length} shown</span></div>
            <div className="mt-3 space-y-2">
              {filtered.map((event) => (
                <button key={event.id} onClick={() => setSelectedId(event.id)} className={`grid w-full grid-cols-[58px_18px_70px_1fr_auto] items-center gap-3 rounded-xl border px-3 py-3 text-left transition ${selected.id === event.id ? "border-blue-300 bg-blue-50/50" : event.status === "alert" ? "border-red-200 bg-red-50/40" : event.status === "watch" ? "border-amber-200 bg-amber-50/40" : "border-slate-200 bg-white hover:bg-slate-50"}`}>
                  <span className="text-[10px] font-extrabold text-slate-700">{formatClock(event.timestamp)}</span>
                  <span className={`h-2.5 w-2.5 rounded-full ${dotClass(event.status)}`} />
                  <span className={`rounded-full px-2 py-1 text-center text-[9px] font-extrabold ${statusClasses(event.status)}`}>{statusLabel(event.status)}</span>
                  <span className="min-w-0"><strong className="block text-[10px] text-slate-800">{event.title}</strong><span className="mt-1 block truncate text-[9px] text-slate-500">{event.description}</span></span>
                  <span className="text-right text-[9px] font-semibold text-slate-500">{event.notificationState === "prepared" ? "Prepared · Not sent" : event.notificationState === "monitoring" ? "Monitoring only" : event.notificationState === "sent" ? "Sent to admin contact" : "No action needed"}</span>
                </button>
              ))}
            </div>
          </section>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3 text-[9px] text-slate-400"><span>PM2.5 values follow the API contract; alerting uses pm25_upper ≥35.5 µg/m³.</span><span>Safe/Watch are monitoring states only; Confirm & Send appears only for Alert.</span></div>
        </div>
      </main>
    </ProAppShell>
  );
}

"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  Flame,
  Info,
  MapPinned,
  RadioTower,
  Satellite,
  Send,
  ShieldAlert,
  SlidersHorizontal,
  UserCheck,
  Wind,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Alert, Forecast, HotspotGridCell, Institution } from "@/lib/api/types";
import { loadProLiveMonitorData, PRO_HORIZON_HOURS } from "@/lib/data/source";
import { attributionLine } from "@/lib/ui/format";
import { getStatusFromAlerts, type LiteRiskStatus } from "@/lib/ui/status";
import { ALERT_THRESHOLD_PM25, GOOD_MAX_PM25 } from "@/lib/ui/threshold";
import { ProAppShell } from "./ProAppShell";
import { ProLiveSnapshot } from "./ProLiveSnapshot";

type ScreenData = Awaited<ReturnType<typeof loadProLiveMonitorData>>;
type RegionalStatus = LiteRiskStatus;

const MAP = { lonMin: 108.4, lonMax: 113.2, latMin: -1.0, latMax: 3.3 };

function project(lon: number, lat: number) {
  const x = ((lon - MAP.lonMin) / (MAP.lonMax - MAP.lonMin)) * 100;
  const y = (1 - (lat - MAP.latMin) / (MAP.latMax - MAP.latMin)) * 100;
  return { x: Math.max(2, Math.min(98, x)), y: Math.max(3, Math.min(97, y)) };
}

/**
 * /hotspots/summary answers over the whole scenario domain (105,-5 to 116,4),
 * which is far wider than the extent this map draws. Cells outside it have to be
 * dropped rather than fed to `project()`, whose clamp would otherwise pile them
 * up on the edges as phantom hotspots.
 */
function withinMapBounds(lon: number, lat: number) {
  return lon >= MAP.lonMin && lon <= MAP.lonMax && lat >= MAP.latMin && lat <= MAP.latMax;
}

function peakUpper(forecast: Forecast) {
  return forecast.peak.pm25_upper ?? forecast.peak.pm25;
}

function currentValue(forecast: Forecast) {
  return forecast.current.pm25;
}

/**
 * Status comes from whether the backend raised an alert for this institution,
 * never from comparing a number here. Reading `peak.aqi_category` instead would
 * be wrong: it categorises the *central* estimate while alerting fires on the
 * upper band, so at the crossborder bookmark it reads MODERATE for
 * institutions that are actively alerting.
 */
function regionalStatus(forecasts: Forecast[], alerts: Alert[]): RegionalStatus {
  const statuses = forecasts.map((f) => getStatusFromAlerts(f, alerts));
  if (statuses.includes("alert")) return "alert";
  if (statuses.includes("watch")) return "watch";
  return "safe";
}

function statusBadge(status: RegionalStatus) {
  if (status === "alert") return "border-red-200 bg-red-50 text-red-600";
  if (status === "watch") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-emerald-200 bg-emerald-50 text-emerald-700";
}

function formatClock(iso?: string | null) {
  if (!iso) return "local replay";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kuching",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

function institutionTypeIcon(type: Institution["type"]) {
  if (type === "hospital") return "✚";
  if (type === "authority") return "◆";
  return "🏫";
}

function RegionalMap({ institutions, forecasts, alerts, hotspotCells }: {
  institutions: readonly Institution[];
  forecasts: Forecast[];
  alerts: Alert[];
  hotspotCells: HotspotGridCell[];
}) {
  const forecastById = new Map(forecasts.map((f) => [f.institution.id, f]));

  // Ranked by detection count, not the API's (lat, lon) ordering: taking the first
  // twelve as returned meant taking the twelve southernmost cells, every one of them
  // off this map and clamped into the corners.
  const visibleCells = hotspotCells
    .filter((cell) => withinMapBounds(cell.lon, cell.lat))
    .sort((a, b) => b.count - a.count)
    .slice(0, 12);

  // Pontianak's three institutions sit within 0.3% of each other and Kuching's within
  // 0.25%, so a fixed nudge left each cluster stacked into one readable card. Group by
  // proximity and fan each group out vertically around its shared position instead.
  //
  // Grouped greedily against a distance threshold rather than by rounding to a grid:
  // Pontianak's three round to three *different* cells (20:77, 20:78, 19:78) while
  // still overlapping, so a grid leaves them stacked. The thresholds are the card's
  // own footprint - min-w-[128px] by ~26px against a ~776x380 box.
  const CLUSTER_DX = 10;
  const CLUSTER_DY = 8;
  const clusters: { x: number; y: number; members: string[] }[] = [];
  institutions.forEach((institution) => {
    const pos = project(institution.lon, institution.lat);
    const hit = clusters.find(
      (c) => Math.abs(c.x - pos.x) < CLUSTER_DX && Math.abs(c.y - pos.y) < CLUSTER_DY,
    );
    if (hit) hit.members.push(institution.id);
    else clusters.push({ x: pos.x, y: pos.y, members: [institution.id] });
  });
  const clusterOf = new Map(
    clusters.flatMap((c) => c.members.map((id, seq) => [id, { seq, size: c.members.length }])),
  );

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <h3 className="text-sm font-extrabold text-ink">Regional Haze Forecast</h3>
        <span className="flex items-center gap-2 text-[10px] font-semibold text-slate-500"><Clock3 size={12} /> West Kalimantan + Sarawak shown together</span>
      </div>
      <div className="relative h-[380px] overflow-hidden bg-[#cfe9fb]">
        <div className="absolute -left-[7%] top-[12%] h-[88%] w-[55%] rounded-[48%_52%_38%_50%] bg-[#dfe9c9]" />
        <div className="absolute right-[-8%] top-[12%] h-[88%] w-[62%] rounded-[48%_38%_50%_45%] bg-[#d9efca]" />
        <div className="absolute left-[17%] top-[16%] z-10 text-2xl font-black tracking-tight text-slate-800/90">WEST<br />KALIMANTAN</div>
        <div className="absolute right-[13%] top-[18%] z-10 text-2xl font-black tracking-tight text-slate-800/90">SARAWAK</div>
        <div className="absolute left-[13%] bottom-[17%] z-10 text-xs font-medium text-slate-600">Pontianak</div>
        <div className="absolute right-[22%] bottom-[34%] z-10 text-xs font-medium text-slate-600">Kuching</div>

        <svg className="absolute inset-0 z-[5] h-full w-full" viewBox="0 0 1000 500" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <linearGradient id="hazeArrow" x1="0" x2="1">
              <stop offset="0%" stopColor="#f6b278" stopOpacity="0.42" />
              <stop offset="65%" stopColor="#ff7a59" stopOpacity="0.70" />
              <stop offset="100%" stopColor="#f34b2f" stopOpacity="0.88" />
            </linearGradient>
            {/*
              markerUnits defaults to "strokeWidth", which scales the whole marker
              coordinate system by the stroke width. At strokeWidth 46 this 9x6
              triangle rendered at ~414x276 units inside a 1000x500 viewBox - 41% of
              the map's width - which is the orange wedge that was covering the
              institution labels. userSpaceOnUse sizes the head independently of the
              band, and the explicit viewBox scales the path to the declared box.
            */}
            <marker id="arrowHead" viewBox="0 0 10 7" markerUnits="userSpaceOnUse" markerWidth="34" markerHeight="24" refX="9" refY="3.5" orient="auto">
              <path d="M0,0 L0,7 L10,3.5 z" fill="#f15b40" />
            </marker>
          </defs>
          <path d="M265 250 C430 190, 555 330, 785 260" fill="none" stroke="url(#hazeArrow)" strokeWidth="14" strokeLinecap="round" markerEnd="url(#arrowHead)" />
        </svg>

        <div className="absolute left-3 top-3 z-30 w-[150px] rounded-xl border border-slate-200 bg-white/95 p-3 shadow-sm backdrop-blur">
          <div className="space-y-2 text-[10px] font-semibold text-slate-600">
            <p className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-red-500" /> Hotspots</p>
            <p className="flex items-center gap-2"><ArrowRight size={11} className="text-orange-500" /> Haze direction</p>
            <p className="flex items-center gap-2"><CircleDot size={11} className="text-violet-500" /> Institutions</p>
            <div className="border-t border-slate-100 pt-2">
              <p><span className="text-emerald-500">●</span> Safe</p>
              <p><span className="text-amber-500">●</span> Watch</p>
              <p><span className="text-red-500">●</span> Alert</p>
            </div>
          </div>
        </div>

        {visibleCells.map((cell, index) => {
          const pos = project(cell.lon, cell.lat);
          const size = Math.max(8, Math.min(18, 7 + cell.count * 1.7));
          return (
            <span
              key={`${cell.lon}-${cell.lat}-${index}`}
              title={`${cell.count} hotspot detections`}
              className="absolute z-20 rounded-full bg-orange-500 shadow-[0_0_0_8px_rgba(249,115,22,.08)]"
              style={{ left: `${pos.x}%`, top: `${pos.y}%`, width: size, height: size, transform: "translate(-50%,-50%)" }}
            />
          );
        })}

        {institutions.map((institution) => {
          const forecast = forecastById.get(institution.id);
          if (!forecast) return null;
          const pos = project(institution.lon, institution.lat);
          const status = getStatusFromAlerts(forecast, alerts);
          const { seq, size } = clusterOf.get(institution.id) ?? { seq: 0, size: 1 };
          const nudgeX = 0;
          const nudgeY = seq * 26 - (size - 1) * 13;
          return (
            <div
              key={institution.id}
              className="absolute z-30 min-w-[128px] rounded-lg border bg-white px-2.5 py-2 shadow-md"
              style={{ left: `calc(${pos.x}% + ${nudgeX}px)`, top: `calc(${pos.y}% + ${nudgeY}px)`, transform: "translate(-50%,-50%)" }}
            >
              <p className="truncate text-[9px] font-extrabold text-slate-700">{institutionTypeIcon(institution.type)} {institution.name}</p>
              <p className={`mt-1 text-[9px] font-extrabold capitalize ${status === "alert" ? "text-red-600" : status === "watch" ? "text-amber-600" : "text-emerald-600"}`}>{status}</p>
            </div>
          );
        })}

        <div className="absolute bottom-3 right-3 z-30 w-[220px] rounded-xl border border-slate-200 bg-white/95 p-3 shadow-sm">
          <p className="text-[9px] font-bold text-slate-500">PM2.5 forecast scale (µg/m³)</p>
          <div className="mt-2 h-2 rounded-full bg-gradient-to-r from-emerald-400 via-amber-400 to-red-500" />
          <div className="mt-1 flex justify-between text-[8px] text-slate-400"><span>0</span><span>{GOOD_MAX_PM25}</span><span>{ALERT_THRESHOLD_PM25}</span><span>55+</span></div>
        </div>
      </div>
    </section>
  );
}

function InstitutionRiskTable({ institutions, forecasts, alerts }: { institutions: readonly Institution[]; forecasts: Forecast[]; alerts: Alert[] }) {
  const institutionById = new Map(institutions.map((i) => [i.id, i]));
  const rows = [...forecasts].sort((a, b) => peakUpper(b) - peakUpper(a));
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><Building2 size={15} /> Institutions at Risk</h3>
        <span className="text-[10px] font-bold text-blue-600">All six institutions</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[620px] text-left text-[10px]">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-3 py-2 font-bold">Institution</th>
              <th className="px-3 py-2 font-bold">Type</th>
              <th className="px-3 py-2 font-bold">Location</th>
              <th className="px-3 py-2 font-bold">Current</th>
              <th className="px-3 py-2 font-bold">Forecast Peak</th>
              <th className="px-3 py-2 font-bold">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((forecast) => {
              const institution = institutionById.get(forecast.institution.id);
              if (!institution) return null;
              const status = getStatusFromAlerts(forecast, alerts);
              return (
                <tr key={forecast.institution.id} className="hover:bg-slate-50/70">
                  <td className="max-w-[170px] truncate px-3 py-2 font-semibold text-slate-700">{institution.name}</td>
                  <td className="px-3 py-2 capitalize text-slate-500">{institution.type}</td>
                  <td className="px-3 py-2 text-slate-500">{institution.city}</td>
                  <td className="px-3 py-2 font-bold text-slate-700">{currentValue(forecast).toFixed(1)}</td>
                  <td className="px-3 py-2 font-bold text-violet-600">{peakUpper(forecast).toFixed(1)} ({forecast.peak.lead_hours}h)</td>
                  <td className="px-3 py-2"><span className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase ${status === "alert" ? "bg-red-100 text-red-600" : status === "watch" ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}>{status}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Pipeline() {
  const steps = [
    { title: "Public Satellite Data", note: "FIRMS hotspot observations", icon: Satellite, tone: "bg-blue-50 text-blue-700" },
    { title: "Distance & Wind Features", note: "Distance, wind speed & direction", icon: Wind, tone: "bg-orange-50 text-orange-700" },
    { title: "Random Forest Forecast", note: "Selected after outperforming GRU", icon: RadioTower, tone: "bg-rose-50 text-rose-700" },
    { title: "Model Range Check", note: "Flags conditions beyond training range", icon: AlertTriangle, tone: "bg-violet-50 text-violet-700" },
    { title: "Human Confirmation", note: "Staff reviews the proposed alert", icon: UserCheck, tone: "bg-emerald-50 text-emerald-700" },
    { title: "Verified Contact", note: "Sent only after confirmation", icon: Send, tone: "bg-amber-50 text-amber-700" },
  ];
  return (
    <section className="rounded-2xl border border-slate-200 bg-gradient-to-r from-white to-emerald-50/40 p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-extrabold text-ink">How HazeWatch Generates an Alert</h3>
        <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[9px] font-extrabold text-emerald-700">Human confirmation required</span>
      </div>
      <div className="mt-3 grid gap-2 xl:grid-cols-6">
        {steps.map(({ title, note, icon: Icon, tone }, index) => (
          <div key={title} className="relative flex min-h-[76px] items-center gap-3 rounded-xl border border-slate-100 bg-white/85 px-3 py-2">
            <span className={`grid h-9 w-9 flex-none place-items-center rounded-full ${tone}`}><Icon size={17} /></span>
            <div>
              <p className="text-[10px] font-extrabold leading-4 text-slate-700">{title}</p>
              <p className="mt-0.5 text-[8px] leading-3 text-slate-500">{note}</p>
            </div>
            {index < steps.length - 1 && <ChevronRight className="absolute -right-2 top-1/2 hidden -translate-y-1/2 text-slate-300 xl:block" size={15} />}
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-8 gap-y-1 border-t border-slate-100 pt-2 text-[9px] text-slate-500">
        <p><strong className="text-slate-700">Model selection:</strong> Random Forest was selected after outperforming GRU.</p>
        <p><strong className="text-slate-700">Alert delivery:</strong> Messages are simulated and require explicit human confirmation.</p>
      </div>
    </section>
  );
}

export function ProLiveMonitor() {
  const [data, setData] = useState<ScreenData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadProLiveMonitorData().then(setData).catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "Failed to load Pro dashboard data.");
    });
  }, []);

  if (error) {
    return (
      <ProAppShell activePage="live-monitor">
        <main className="p-8">
          <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
            <strong>Could not load Pro Live Monitor.</strong>
            <p className="mt-2">{error}</p>
            <p className="mt-2">For an offline demo, set NEXT_PUBLIC_HAZE_DATA_MODE=mock.</p>
          </div>
        </main>
      </ProAppShell>
    );
  }

  if (!data) {
    return (
      <ProAppShell activePage="live-monitor">
        <main className="p-8 text-sm text-slate-500">
          Loading regional monitor…
          <p className="mt-2 text-xs text-slate-400">The first request can take up to a minute if the demo server is waking from idle.</p>
        </main>
      </ProAppShell>
    );
  }

  return <Loaded data={data} />;
}

function Loaded({ data }: { data: ScreenData }) {
  const { institutions, forecasts, alerts, hotspotSummary, health, at } = data;
  const status = useMemo(() => regionalStatus(forecasts, alerts), [forecasts, alerts]);
  const sortedForecasts = useMemo(() => [...forecasts].sort((a, b) => peakUpper(b) - peakUpper(a)), [forecasts]);
  const highest = sortedForecasts[0];
  const highestInstitution = institutions.find((i) => i.id === highest?.institution.id);
  const activeAlert = alerts.find((a) => a.status === "active") ?? alerts[0];
  const atRisk = useMemo(
    () => forecasts.filter((f) => getStatusFromAlerts(f, alerts) !== "safe").length,
    [forecasts, alerts],
  );
  const transboundaryForecast = forecasts.find((f) => f.attribution.transboundary);
  const attribution = transboundaryForecast ? attributionLine(transboundaryForecast.attribution) : null;
  const sourceRegion = transboundaryForecast?.attribution.dominant_source_region ?? null;

  /**
   * Where the smoke is going: the receptor the attribution block belongs to, which is
   * the same forecast the banner above is written from. Reading `highestInstitution`
   * here instead was wrong - "highest forecast peak anywhere" is not "destination", and
   * at the crossborder bookmark that is Pontianak, inside the *source* region, which
   * rendered "West Kalimantan -> West Kalimantan".
   *
   * `forecast.institution` is an InstitutionCompact and carries no admin_region, so the
   * full record is resolved from the institutions list.
   */
  const receptorInstitution = institutions.find(
    (i) => i.id === transboundaryForecast?.institution.id,
  );
  const destinationRegion = receptorInstitution?.admin_region ?? null;

  return (
    <ProAppShell activePage="live-monitor" health={health} at={at}>
      <main className="min-w-0 bg-[#fbfcfe] p-5 lg:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-3xl font-extrabold tracking-tight text-ink">Live Haze Monitor</h2>
              <span className="mt-1 h-3 w-3 rounded-full bg-emerald-500" />
            </div>
            <p className="mt-1 text-sm text-slate-500">Monitor cross-border haze risks and short-term air-quality forecasts.</p>
          </div>
          <span className="rounded-full border border-slate-200 bg-white px-3 py-2 text-[10px] font-semibold text-slate-500">Prototype / demo dataset</span>
        </div>

        <section className={`mt-3 flex flex-wrap items-center gap-4 rounded-2xl border px-4 py-3 ${status === "alert" ? "border-red-200 bg-red-50/70" : status === "watch" ? "border-orange-300 bg-[#fff5ec]" : "border-emerald-200 bg-emerald-50/65"}`}>
          <span className={`grid h-11 w-11 flex-none place-items-center rounded-xl ${status === "alert" ? "bg-red-500 text-white" : status === "watch" ? "bg-orange-500 text-white" : "bg-emerald-500 text-white"}`}><AlertTriangle size={23} /></span>
          <div className="min-w-[280px] flex-1">
            <h3 className={`text-base font-extrabold ${status === "alert" ? "text-red-700" : status === "watch" ? "text-orange-700" : "text-emerald-700"}`}>{status === "safe" ? "No Regional Haze Alert" : "Cross-Border Haze Risk Detected"}</h3>
            <p className="mt-0.5 text-xs text-slate-600">
              {attribution ?? "No cross-border source attribution is active in the current forecast."}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[9px] font-bold uppercase tracking-wide text-slate-500">Regional Risk</p>
            <span className={`mt-1 inline-flex rounded-lg border px-3 py-1.5 text-[10px] font-extrabold uppercase ${statusBadge(status)}`}>{status}</span>
          </div>
          <Link href="/pro/institutions" className="rounded-xl border border-blue-200 bg-white px-4 py-2.5 text-xs font-extrabold text-blue-600">View Affected Institutions →</Link>
        </section>

        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <section className="rounded-2xl border border-red-100 bg-red-50/60 p-4">
            <div className="flex items-center gap-4"><span className="grid h-12 w-12 place-items-center rounded-full bg-red-100 text-red-600"><Flame size={24} /></span><div><p className="text-[10px] text-slate-500">Active Hotspots</p><p className="text-2xl font-black text-red-600">{hotspotSummary.count}</p><p className="text-[9px] text-slate-500">aggregated from FIRMS detections</p></div></div>
          </section>
          <section className="rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
            <div className="flex items-center gap-4"><span className="grid h-12 w-12 place-items-center rounded-full bg-blue-100 text-blue-600"><Building2 size={23} /></span><div><p className="text-[10px] text-slate-500">Institutions at Risk</p><p className="text-2xl font-black text-blue-700">{atRisk}</p><p className="text-[9px] text-slate-500">across Indonesia and Malaysia</p></div></div>
          </section>
          <section className="rounded-2xl border border-violet-100 bg-violet-50/65 p-4">
            <div className="flex items-center gap-4"><span className="grid h-12 w-12 place-items-center rounded-full bg-violet-100 text-violet-600"><CircleDot size={23} /></span><div><p className="text-[10px] text-slate-500">Highest Forecast PM2.5</p><p className="text-2xl font-black text-violet-700">{highest ? peakUpper(highest).toFixed(1) : "—"} <span className="text-sm">µg/m³</span></p><p className="text-[9px] text-slate-500">upper prediction band within {PRO_HORIZON_HOURS}h</p></div></div>
          </section>
          <section className="rounded-2xl border border-emerald-100 bg-emerald-50/60 p-4">
            <div className="flex items-center gap-4"><span className="grid h-12 w-12 place-items-center rounded-full bg-emerald-100 text-emerald-700"><Wind size={23} /></span><div><p className="text-[10px] text-slate-500">Haze Movement</p><p className="text-base font-black leading-5 text-emerald-700">{sourceRegion && destinationRegion ? `${sourceRegion.split(",")[0]} → ${destinationRegion}` : "No cross-border movement"}</p><p className="text-[9px] text-slate-500">cross-border source attribution</p></div></div>
          </section>
        </div>

        <div className="mt-3 grid gap-3 xl:grid-cols-[1.12fr_.78fr]">
          <RegionalMap institutions={institutions} forecasts={forecasts} alerts={alerts} hotspotCells={hotspotSummary.cells} />
          <div className="space-y-3">
            <section className="rounded-2xl border border-violet-100 bg-violet-50/60 p-4">
              <div className="flex items-center justify-between"><h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><MapPinned size={15} /> Next {PRO_HORIZON_HOURS} Hours</h3><span className="rounded-lg bg-violet-100 px-2 py-1 text-[9px] font-bold text-violet-700">Replay {formatClock(at ?? health.clock)}</span></div>
              <h4 className="mt-3 text-lg font-extrabold text-slate-800">Haze impact is expected to increase</h4>
              <div className="mt-4 grid grid-cols-3 gap-3 text-[10px]">
                <div className="border-r border-slate-200"><p className="text-slate-500">Source</p><p className="mt-1 font-extrabold text-slate-700">{sourceRegion?.split(",")[0] ?? "—"}</p></div>
                <div className="border-r border-slate-200"><p className="text-slate-500">Highest Forecast</p><p className="mt-1 font-extrabold text-violet-700">{highest ? peakUpper(highest).toFixed(1) : "—"} µg/m³</p></div>
                <div><p className="text-slate-500">Most Affected</p><p className="mt-1 font-extrabold text-slate-700">{highestInstitution ? `${highestInstitution.city}, ${highestInstitution.admin_region}` : "—"}</p></div>
              </div>
              <p className="mt-3 text-[9px] text-slate-500">Forecast values use the p90 upper band for alert triggering; the central estimate may be lower.</p>
            </section>

            <InstitutionRiskTable institutions={institutions} forecasts={forecasts} alerts={alerts} />

            {activeAlert && (
              <section className="rounded-2xl border border-red-200 bg-red-50/60 p-4">
                <h3 className="flex items-center gap-2 text-sm font-extrabold text-red-700"><ShieldAlert size={17} /> Priority Alert — {activeAlert.institution_name}</h3>
                <p className="mt-2 text-[10px] leading-4 text-slate-600">Forecast upper band reaches {activeAlert.forecast_peak_pm25.toFixed(1)} µg/m³ with {activeAlert.lead_time_hours}h warning lead time. Review preparedness recommendations before the forecast threshold crossing.</p>
                <div className="mt-3 flex gap-2">
                  <Link href="/pro/institutions" className="rounded-xl bg-red-600 px-4 py-2 text-[10px] font-extrabold text-white">View Institution →</Link>
                  <Link href="/pro/notification-preview" className="rounded-xl border border-blue-300 bg-white px-4 py-2 text-[10px] font-extrabold text-blue-600">Preview Notification →</Link>
                </div>
              </section>
            )}
          </div>
        </div>

        <div className="mt-3"><ProLiveSnapshot /></div>

        <div className="mt-3"><Pipeline /></div>
        <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[9px] text-slate-400"><Info size={11} /> PM2.5 current values are labelled by API provenance; forecasts are model outputs. Cross-border attribution is surfaced from the forecast attribution block.</p>
      </main>
    </ProAppShell>
  );
}

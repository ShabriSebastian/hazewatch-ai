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
import { attributionLine, formatCount } from "@/lib/ui/format";
import {
  CITY_LABELS,
  COASTLINE_PATH,
  MAP_ASPECT,
  project,
  REGION_LABELS,
  transportArc,
  withinMapBounds,
} from "@/lib/ui/basemap";
import { getStatusFromAlerts, type LiteRiskStatus } from "@/lib/ui/status";
import { ALERT_THRESHOLD_PM25, GOOD_MAX_PM25 } from "@/lib/ui/threshold";
import { DataUnavailable } from "./DataUnavailable";
import { ProAppShell } from "./ProAppShell";

type ScreenData = Awaited<ReturnType<typeof loadProLiveMonitorData>>;
type RegionalStatus = LiteRiskStatus;


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
  if (!iso) return "unknown";
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

  // Every cell inside the box, not a top-N slice of them.
  //
  // This used to take the twelve largest, which was a workaround for a bounding
  // box so narrow that most of the fire field fell outside it. With the box
  // covering the real extent, showing twelve would curate the map: the twelve
  // largest cells all sit in southern West Kalimantan, so Sarawak would read as
  // empty while its institutions alerted. ~375 absolutely-positioned spans is
  // nothing for the DOM, and the map is supposed to show the fire field.
  //
  // Still sorted by count, so the largest paint last and sit on top.
  const visibleCells = hotspotCells
    .filter((cell) => withinMapBounds(cell.lon, cell.lat))
    .sort((a, b) => a.count - b.count);

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
  // Where the haze is coming from and going to, as projected points. Both come
  // from the attribution block the forecast already carries - the source region's
  // country picks the origin city, and the receptor is whichever city is not it.
  const sourceCountry = forecasts.find((f) => f.attribution.transboundary)?.attribution.source_country
    ?? forecasts.find((f) => f.attribution.source_country)?.attribution.source_country
    ?? null;
  // Anchored to the REGION labels, not the city ones.
  //
  // The attribution is a statement about regions - the KPI tile beside this map
  // reads "West Kalimantan -> Sarawak" - so region anchors say what the data
  // says. They also sit in open interior, where the city anchors sat directly
  // under the institution cards and left the arc almost entirely hidden.
  const REGION_OF = { ID: "WEST KALIMANTAN", MY: "SARAWAK" } as const;
  const originRegion = REGION_OF[(sourceCountry as keyof typeof REGION_OF) ?? "ID"];
  const receptorRegion = originRegion === "SARAWAK" ? "WEST KALIMANTAN" : "SARAWAK";
  const originLabel = REGION_LABELS[originRegion as keyof typeof REGION_LABELS];
  const receptorLabel = REGION_LABELS[receptorRegion as keyof typeof REGION_LABELS];
  const transport = sourceCountry && originLabel && receptorLabel
    ? { from: { x: originLabel.x, y: originLabel.y }, to: { x: receptorLabel.x, y: receptorLabel.y } }
    : null;

  const clusterOf = new Map(
    clusters.flatMap((c) => c.members.map((id, seq) => [id, { seq, size: c.members.length }])),
  );

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <h3 className="text-sm font-extrabold text-ink">Regional Haze Forecast</h3>
        <span className="flex items-center gap-2 text-[10px] font-semibold text-slate-500"><Clock3 size={12} /> West Kalimantan + Sarawak shown together</span>
      </div>
      {/*
        Sized by aspect, not by a fixed height. The bounding box is taller than
        it is wide, so a 380px-tall box stretched longitude 1.5x and no coastline
        survives that. At MAP_ASPECT a degree of longitude and a degree of
        latitude are the same number of pixels, which is what makes one
        projection correct for the coastline, the cells and the markers at once.
        Capped so a very wide column cannot produce an absurdly tall card.
      */}
      <div
        className="relative max-h-[620px] overflow-hidden bg-[#cfe9fb]"
        style={{ aspectRatio: MAP_ASPECT }}
      >
        {/*
          viewBox 0..100 with preserveAspectRatio="none" puts SVG units in the
          same percentage space the CSS-positioned dots and cards use, so one
          coordinate system covers every layer. Strokes are non-scaling, or the
          uneven x/y scale would render them as uneven weights.
        */}
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <path d={COASTLINE_PATH} fill="#dfe9c9" stroke="#9cb389" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        </svg>

        {Object.entries(REGION_LABELS).map(([name, pos]) => (
          <div
            key={name}
            className="pointer-events-none absolute z-[14] text-center text-xl font-black leading-tight tracking-tight text-slate-800/80"
            style={{ left: `${pos.x}%`, top: `${pos.y}%`, transform: "translate(-50%,-50%)" }}
          >
            {name.split(" ").map((word) => <div key={word}>{word}</div>)}
          </div>
        ))}

        {/*
          Offset below its point rather than centred on it: the institution card
          for the same city is centred there, and the two collided.
        */}
        {Object.entries(CITY_LABELS).map(([city, pos]) => (
          <div
            key={city}
            className="pointer-events-none absolute z-[14] rounded bg-white/70 px-1 text-[10px] font-semibold text-slate-600"
            style={{ left: `${pos.x}%`, top: `${pos.y}%`, transform: "translate(-50%, 22px)" }}
          >
            {city}
          </div>
        ))}

        {/*
          Drawn between two PROJECTED points, not a fixed curve. The old path was
          a hardcoded cubic that pointed west-to-east because that is how it was
          drawn, and it kept pointing that way whatever the attribution said.
          This runs from the attributed source city to the receptor city, so if
          the transport reverses the arrow reverses with it.
        */}
        {transport && (
          <svg className="pointer-events-none absolute inset-0 z-[12] h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id="hazeArrow" x1="0" x2="1">
                <stop offset="0%" stopColor="#f6b278" stopOpacity="0.42" />
                <stop offset="65%" stopColor="#ff7a59" stopOpacity="0.70" />
                <stop offset="100%" stopColor="#f34b2f" stopOpacity="0.88" />
              </linearGradient>
              {/*
                markerUnits defaults to "strokeWidth", which scales the marker's
                whole coordinate system by the stroke width and produced an
                orange wedge covering the institution cards. userSpaceOnUse sizes
                the head independently of the band.
              */}
              <marker id="arrowHead" viewBox="0 0 10 7" markerUnits="userSpaceOnUse" markerWidth="6" markerHeight="4.2" refX="9" refY="3.5" orient="auto">
                <path d="M0,0 L0,7 L10,3.5 z" fill="#f15b40" />
              </marker>
            </defs>
            <path
              d={transportArc(transport.from, transport.to)}
              fill="none"
              stroke="url(#hazeArrow)"
              strokeWidth="11"
              strokeLinecap="butt"
              vectorEffect="non-scaling-stroke"
              markerEnd="url(#arrowHead)"
            />
          </svg>
        )}

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
          // Square-root scale against a fixed reference, not a linear ramp
          // against a cap. The old formula was tuned for twelve dots and
          // saturated almost immediately - the median in-box cell holds 14
          // detections and the linear form put that at the 18px ceiling, so
          // nearly every dot drew at maximum size and 375 of them merged into
          // one orange mass. sqrt spreads 1..900+ across a readable range, and
          // the fixed reference keeps dot sizes comparable between refreshes
          // rather than rescaling to whatever the busiest cell happens to be.
          const size = 3 + 11 * Math.min(1, Math.sqrt(cell.count / 900));
          return (
            <span
              key={`${cell.lon}-${cell.lat}-${index}`}
              title={`${formatCount(cell.count)} hotspot detections`}
              className="absolute z-[8] rounded-full bg-orange-500/85"
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
          <DataUnavailable detail={error} />
        </main>
      </ProAppShell>
    );
  }

  if (!data) {
    return (
      <ProAppShell activePage="live-monitor">
        <main className="p-8 text-sm text-slate-500">
          Loading regional monitor…
          <p className="mt-2 text-xs text-slate-400">Reading the published snapshot. This is a single static file, so it should be quick.</p>
        </main>
      </ProAppShell>
    );
  }

  return <Loaded data={data} />;
}

function Loaded({ data }: { data: ScreenData }) {
  const { institutions, forecasts, alerts, hotspotSummary, health, at, issuedAt, issuedOffsetHours } = data;
  const status = useMemo(() => regionalStatus(forecasts, alerts), [forecasts, alerts]);
  const sortedForecasts = useMemo(() => [...forecasts].sort((a, b) => peakUpper(b) - peakUpper(a)), [forecasts]);
  const highest = sortedForecasts[0];
  const highestInstitution = institutions.find((i) => i.id === highest?.institution.id);
  const activeAlert = alerts.find((a) => a.status === "active") ?? alerts[0];
  /**
   * Alerting and watching are counted separately.
   *
   * This tile used to show one number for "not safe", which was unambiguous
   * only while the replay had every institution alerting at once. On live data
   * three institutions alert and three are merely Watch, and a single "6" next
   * to "Institutions at Risk" reads as six alerts - overstating the situation
   * on exactly the screen someone would act from. Watch is a monitoring state
   * with no recommended action; it does not belong in the same number.
   */
  const { alerting, watching } = useMemo(() => {
    const states = forecasts.map((f) => getStatusFromAlerts(f, alerts));
    return {
      alerting: states.filter((s) => s === "alert").length,
      watching: states.filter((s) => s === "watch").length,
    };
  }, [forecasts, alerts]);
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
    <ProAppShell activePage="live-monitor" forecastLabel={`Next ${PRO_HORIZON_HOURS} Hours`} health={health} at={at} issuedAt={issuedAt} issuedOffsetHours={issuedOffsetHours}>
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
            <div className="flex items-center gap-4"><span className="grid h-12 w-12 place-items-center rounded-full bg-red-100 text-red-600"><Flame size={24} /></span><div><p className="text-[10px] text-slate-500">Active Hotspots</p><p className="text-2xl font-black text-red-600">{formatCount(hotspotSummary.count)}</p><p className="text-[9px] text-slate-500">aggregated from FIRMS detections</p></div></div>
          </section>
          <section className="rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
            <div className="flex items-center gap-4">
              <span className="grid h-12 w-12 place-items-center rounded-full bg-blue-100 text-blue-600"><Building2 size={23} /></span>
              <div className="min-w-0">
                <p className="text-[10px] text-slate-500">Institution status</p>
                <p className="flex items-baseline gap-3">
                  <span className="text-2xl font-black text-red-600">{alerting}</span>
                  <span className="text-[10px] font-extrabold uppercase tracking-wide text-red-600">alerting</span>
                  <span className="text-2xl font-black text-amber-600">{watching}</span>
                  <span className="text-[10px] font-extrabold uppercase tracking-wide text-amber-600">watch</span>
                </p>
                <p className="text-[9px] text-slate-500">of {institutions.length} across Indonesia and Malaysia · Watch is monitoring only</p>
              </div>
            </div>
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
              <div className="flex items-center justify-between"><h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><MapPinned size={15} /> Next {PRO_HORIZON_HOURS} Hours</h3><span className="rounded-lg bg-violet-100 px-2 py-1 text-[9px] font-bold text-violet-700">Issued {formatClock(at ?? health.clock)}</span></div>
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
                {/*
                  Two different moments, and they must be named as such. `lead_time_hours`
                  is the *onset* - the first forecast crossing of the threshold, which is the
                  time the recipient has to act. The peak comes later, at `peak_lead_hours`.
                  Pairing the peak value with the onset lead read as though the peak arrived
                  at the onset hour.
                */}
                <p className="mt-2 text-[10px] leading-4 text-slate-600">Forecast upper band crosses the {activeAlert.threshold_pm25} µg/m³ threshold in {activeAlert.lead_time_hours}h, peaking at {activeAlert.forecast_peak_pm25.toFixed(1)} µg/m³{activeAlert.peak_lead_hours != null ? ` ${activeAlert.peak_lead_hours}h out` : ""}. Review preparedness recommendations before the forecast threshold crossing.</p>
                <div className="mt-3 flex gap-2">
                  <Link href="/pro/institutions" className="rounded-xl bg-red-600 px-4 py-2 text-[10px] font-extrabold text-white">View Institution →</Link>
                  <Link href="/pro/notification-preview" className="rounded-xl border border-blue-300 bg-white px-4 py-2 text-[10px] font-extrabold text-blue-600">Preview Notification →</Link>
                </div>
              </section>
            )}
          </div>
        </div>


        <div className="mt-3"><Pipeline /></div>
        <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[9px] text-slate-400"><Info size={11} /> PM2.5 current values are labelled by API provenance; forecasts are model outputs. Cross-border attribution is surfaced from the forecast attribution block.</p>
      </main>
    </ProAppShell>
  );
}

"use client";

import {
  Bell,
  Building2,
  LayoutDashboard,
  RefreshCw,
  Send,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import type { Health, Institution } from "@/lib/api/types";
import { useSelectedInstitution } from "@/lib/ui/institutionContext";
import { BrandMark } from "./BrandMark";

export type ProNavPage = "live-monitor" | "institutions" | "alert-history" | "notification-preview";

const nav = [
  { key: "live-monitor" as const, label: "Live Monitor", icon: LayoutDashboard, href: "/pro/live-monitor" },
  { key: "institutions" as const, label: "Institutions", icon: Building2, href: "/pro/institutions" },
  { key: "alert-history" as const, label: "Alert History", icon: Bell, href: "/pro/alert-history" },
  { key: "notification-preview" as const, label: "Notification Preview", icon: Send, href: "/pro/notification-preview" },
];

function institutionIcon(type: Institution["type"]) {
  if (type === "hospital") return "🏥";
  if (type === "authority") return "🏛";
  return "🏫";
}

export function ProAppShell({
  children,
  activePage = "live-monitor",
  scopeLabel = "Regional View",
  forecastLabel = "Next 12 Hours",
  institutions = [],
  current,
  health,
  at,
}: {
  children: ReactNode;
  activePage?: ProNavPage;
  scopeLabel?: string;
  forecastLabel?: string;
  /** Present on the institution-scoped screens; the regional monitor omits it. */
  institutions?: readonly Institution[];
  current?: Institution;
  health?: Health;
  /** This visitor's pinned replay clock, shown so the demo state is legible. */
  at?: string | null;
}) {
  const { setInstitutionId } = useSelectedInstitution();
  // Only schools and hospitals are addressable; `authority` sites exist in the
  // contract but are not an institution-staff audience.
  const selectable = institutions.filter(
    (item) => item.type === "school" || item.type === "hospital",
  );
  const showSelector = selectable.length > 0 && Boolean(current);
  return (
    <div className="min-h-screen bg-[#f5f7fb]">
      <div className="min-h-screen w-full overflow-hidden bg-white">
        <header className="grid min-h-[104px] grid-cols-[270px_1fr] border-b border-slate-200 xl:grid-cols-[270px_1fr_auto]">
          <div className="flex items-center gap-4 border-r border-slate-200 px-6">
            <BrandMark />
            <div>
              <h1 className="text-[21px] font-extrabold tracking-tight text-ink">HazeWatch AI</h1>
              <p className="mt-1 text-xs leading-4 text-slate-500">Transboundary Haze<br />Monitoring</p>
            </div>
          </div>

          <div className="flex items-center gap-5 px-8">
            <div>
              <label htmlFor="pro-scope-select" className="mb-2 block text-[11px] font-bold text-slate-500">Scope</label>
              {showSelector ? (
                <div className="flex min-w-[220px] items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-sm">
                  <span aria-hidden>{institutionIcon(current!.type)}</span>
                  <select
                    id="pro-scope-select"
                    value={current!.id}
                    onChange={(event) => setInstitutionId(event.target.value)}
                    className="min-w-0 flex-1 cursor-pointer truncate bg-transparent outline-none"
                  >
                    {selectable.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name} · {item.city}
                      </option>
                    ))}
                  </select>
                </div>
              ) : (
                <div className="flex min-w-[220px] items-center rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-sm">
                  🗺️ &nbsp; {scopeLabel}
                </div>
              )}
            </div>
            <div>
              <p className="mb-2 text-[11px] font-bold text-slate-500">Forecast</p>
              <button className="flex min-w-[190px] items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-sm">
                <span>◷ &nbsp; {forecastLabel}</span><span>⌄</span>
              </button>
            </div>
          </div>

          <div className="col-span-2 flex flex-wrap items-center justify-end gap-3 border-t border-slate-100 px-6 py-4 xl:col-span-1 xl:border-t-0">
            <span className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-bold text-emerald-700">● Prototype Active</span>
            <span className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs font-semibold text-slate-600">
              ◷ {health?.data_source === "scenario_db" ? "Scenario replay" : health?.data_source === "fixtures" ? "Fixture data" : "Demo data"} · {at ? `${at.slice(0, 16).replace("T", " ")}Z` : "local replay"} <RefreshCw size={13} />
            </span>
            {/* Labels the DESTINATION, not the mode you are in: pressing it
                takes you to Lite. Mirrors the control in AppShell. */}
            <Link
              href="/"
              title="Switch to Lite mode"
              aria-label="Switch to Lite mode"
              className="rounded-xl border border-blue-200 bg-white px-4 py-3 text-xs font-extrabold text-blue-600 hover:bg-blue-50"
            >
              ✦ Lite Mode →
            </Link>
          </div>
        </header>

        <div className="grid min-h-[calc(100vh-104px)] grid-cols-[210px_1fr]">
          <aside className="flex flex-col border-r border-slate-200 bg-gradient-to-b from-slate-50 to-blue-50/40 px-3 py-6">
            <nav className="space-y-2">
              {nav.map(({ key, label, icon: Icon, href }) => {
                const active = activePage === key;
                return (
                  <Link
                    key={label}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={`flex w-full items-center gap-3 rounded-xl border px-3 py-3 text-left text-sm font-bold transition ${
                      active
                        ? "border-blue-200 bg-blue-50 text-blue-600 shadow-[inset_3px_0_0_#2563eb]"
                        : "border-transparent text-slate-700 hover:bg-white"
                    }`}
                  >
                    <span className="grid h-8 w-8 place-items-center rounded-lg border border-current/50"><Icon size={17} /></span>
                    {label}
                  </Link>
                );
              })}
            </nav>

            <div className="mt-auto rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4">
              <p className="flex items-center gap-2 text-xs font-extrabold text-emerald-800"><ShieldCheck size={15} /> Human-in-the-loop</p>
              <p className="mt-2 text-[11px] leading-5 text-slate-600">
                Every proposed alert requires staff confirmation before simulated delivery to a verified institution contact.
              </p>
            </div>
          </aside>

          {children}
        </div>
      </div>
    </div>
  );
}

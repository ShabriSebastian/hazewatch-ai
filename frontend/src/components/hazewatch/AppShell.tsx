"use client";

import { Bell, Building2, CheckSquare2, Home, RefreshCw } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import type { Health, Institution } from "@/lib/api/types";
import { useSelectedInstitution } from "@/lib/ui/institutionContext";
import { BrandMark } from "./BrandMark";

export type LiteNavPage = "overview" | "institution-detail" | "alert-history" | "alert-review";

const nav = [
  { key: "overview" as const, label: "Overview", icon: Home, href: "/" },
  { key: "institution-detail" as const, label: "Institution Detail", icon: Building2, href: "/lite/institution-detail" },
  { key: "alert-history" as const, label: "Alert History", icon: Bell, href: "/lite/alert-history" },
  { key: "alert-review" as const, label: "Alert Review", icon: CheckSquare2, href: "/lite/alert-review" },
];

function institutionIcon(type: Institution["type"]) {
  if (type === "hospital") return "🏥";
  if (type === "authority") return "🏛";
  return "🏫";
}

export function AppShell({
  children,
  activePage = "overview",
  institutions = [],
  current,
  health,
  at,
}: {
  children: ReactNode;
  activePage?: LiteNavPage;
  institutions?: readonly Institution[];
  current?: Institution;
  health?: Health;
  /** This visitor's pinned replay clock, shown so the demo state is legible. */
  at?: string | null;
}) {
  const { setInstitutionId } = useSelectedInstitution();
  // Only schools and hospitals are addressable in the Lite build; `authority`
  // sites exist in the contract but are not an institution-staff audience.
  const selectable = institutions.filter(
    (item) => item.type === "school" || item.type === "hospital",
  );

  return (
    <div className="min-h-screen bg-[#f5f7fb]">
      <div className="min-h-screen w-full overflow-hidden bg-white">
        <header className="grid min-h-[104px] grid-cols-[270px_1fr] border-b border-slate-200 xl:grid-cols-[270px_1fr_auto]">
          <div className="flex flex-col justify-center gap-1.5 border-r border-slate-200 px-6">
            <h1 className="sr-only">HazeWatch AI</h1>
            <BrandMark />
            <p className="text-xs leading-4 text-slate-500">Transboundary Haze<br />Monitoring</p>
          </div>

          <div className="flex items-center px-8">
            <div>
              <label htmlFor="institution-select" className="mb-2 block text-[11px] font-bold text-slate-500">
                Institution
              </label>
              <div className="flex min-w-[220px] items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-sm">
                <span aria-hidden>{institutionIcon(current?.type ?? "school")}</span>
                <select
                  id="institution-select"
                  value={current?.id ?? ""}
                  onChange={(event) => setInstitutionId(event.target.value)}
                  disabled={selectable.length === 0}
                  className="min-w-0 flex-1 cursor-pointer truncate bg-transparent outline-none disabled:cursor-not-allowed"
                >
                  {selectable.length === 0 ? (
                    <option value="">Loading institutions…</option>
                  ) : (
                    selectable.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name} · {item.city}
                      </option>
                    ))
                  )}
                </select>
              </div>
            </div>
          </div>

          <div className="col-span-2 flex flex-wrap items-center justify-end gap-3 border-t border-slate-100 px-6 py-4 xl:col-span-1 xl:border-t-0">
            <span className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-bold text-emerald-700">● Prototype Active</span>
            <span className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs font-semibold text-slate-600">
              ◷ {health?.data_source === "scenario_db" ? "Scenario replay" : health?.data_source === "fixtures" ? "Fixture data" : "Demo data"} · {at ? `${at.slice(0, 16).replace("T", " ")}Z` : "local replay"} <RefreshCw size={13} />
            </span>
            {/* Labels the DESTINATION, not the mode you are in: pressing it
                takes you to Pro. The mirror control in ProAppShell says "Lite
                Mode" for the same reason. */}
            <Link
              href="/pro/live-monitor"
              title="Switch to Pro mode"
              aria-label="Switch to Pro mode"
              className="rounded-xl border border-blue-200 bg-white px-4 py-3 text-xs font-extrabold text-blue-600 hover:bg-blue-50"
            >
              ✦ Pro Mode →
            </Link>
          </div>
        </header>

        <div className="grid min-h-[790px] grid-cols-[210px_1fr]">
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

            <div className="mt-auto rounded-2xl border border-blue-200 bg-blue-50/75 p-4">
              <p className="text-xs font-extrabold text-blue-700">Trusted &amp; Secure</p>
              <p className="mt-2 text-[11px] leading-5 text-slate-600">
                Alerts are prepared carefully and sent only to an institution&apos;s verified admin
                contact. Not for public broadcast.
              </p>
            </div>
          </aside>

          {children}
        </div>
      </div>
    </div>
  );
}

"use client";

import { Bell, Building2, CheckSquare2, Home, RefreshCw } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { BrandMark } from "./BrandMark";

export type LiteNavPage = "overview" | "institution-detail" | "alert-history" | "alert-review";

const nav = [
  { key: "overview" as const, label: "Overview", icon: Home, href: "/" },
  { key: "institution-detail" as const, label: "Institution Detail", icon: Building2, href: "/lite/institution-detail" },
  { key: "alert-history" as const, label: "Alert History", icon: Bell, href: "/lite/alert-history" },
  { key: "alert-review" as const, label: "Alert Review", icon: CheckSquare2, href: "/lite/alert-review" },
];

export function AppShell({
  children,
  activePage = "overview",
}: {
  children: ReactNode;
  activePage?: LiteNavPage;
}) {
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

          <div className="flex items-center px-8">
            <div>
              <p className="mb-2 text-[11px] font-bold text-slate-500">Scope</p>
              <button className="flex min-w-[220px] items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-sm">
                <span>🏫 &nbsp; Institution View</span><span>⌄</span>
              </button>
            </div>
          </div>

          <div className="col-span-2 flex flex-wrap items-center justify-end gap-3 border-t border-slate-100 px-6 py-4 xl:col-span-1 xl:border-t-0">
            <span className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-bold text-emerald-700">● Prototype Active</span>
            <span className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs font-semibold text-slate-600">
              ◷ Demo data · local replay <RefreshCw size={13} />
            </span>
            <button className="rounded-xl border border-blue-200 bg-white px-4 py-3 text-xs font-extrabold text-blue-600">✦ Lite Mode</button>
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
                Alerts are prepared carefully and sent only to verified institution contacts.
              </p>
            </div>
          </aside>

          {children}
        </div>
      </div>
    </div>
  );
}

"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCircle2,
  Copy,
  Info,
  LockKeyhole,
  MessageCircle,
  Send,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Alert, Channel, Forecast, Institution, Notification } from "@/lib/api/types";
import {
  confirmProNotification,
  loadProNotificationPreviewData,
  PRO_HORIZON_HOURS,
} from "@/lib/data/source";
import { getLiteRiskStatus } from "@/lib/ui/status";
import { useSelectedInstitution } from "@/lib/ui/institutionContext";
import { ProAppShell } from "./ProAppShell";

type ScreenData = Awaited<ReturnType<typeof loadProNotificationPreviewData>>;

function localTime(iso: string, country: string) {
  const timeZone = country === "ID" ? "Asia/Pontianak" : "Asia/Kuching";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

/**
 * A standalone timestamp needs its date. Bare HH:MM on the message header and
 * footer read as "today" while the replay clock sits days away - the same defect
 * fixed on Institution Detail and Alert History. The peak *window* below is a
 * start-end range inside one forecast, where bare times are still right.
 */
function localStamp(iso: string, country: string) {
  const timeZone = country === "ID" ? "Asia/Pontianak" : "Asia/Kuching";
  const day = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    day: "2-digit",
    month: "short",
  }).format(new Date(iso));
  return `${day} ${localTime(iso, country)}`;
}

/**
 * The recommended-action sentence stays in English in every language.
 *
 * `alert.recommended_actions` comes from RECOMMENDED_ACTIONS in rules.py, which
 * is keyed by institution type and severity and has no language dimension at
 * all, so there is nothing to select a translation from. Rather than substitute
 * different copy or invent translations, the message keeps the English action
 * and the UI says so - see the untranslated-action note below the preview.
 */

function peakWindow(alert: Alert, institution: Institution) {
  const peakDate = new Date(alert.forecast_peak_at);
  const start = new Date(peakDate.getTime() - 60 * 60 * 1000).toISOString();
  const end = new Date(peakDate.getTime() + 60 * 60 * 1000).toISOString();
  return `${localTime(start, institution.country)}–${localTime(end, institution.country)}`;
}

function languageLabel(code: string) {
  if (code === "ms") return "Malay";
  if (code === "id") return "Indonesian";
  if (code === "en") return "English";
  return code.toUpperCase();
}

function preparedMessage(alert: Alert, institution: Institution, language: string) {
  const expectedWindow = peakWindow(alert, institution);
  const firstAction = alert.recommended_actions[0];

  if (language === "ms") {
    return [
      "AMARAN JEREBU",
      `Kualiti udara di sekitar ${institution.name} dijangka bertambah buruk hari ini.`,
      `Kesan tertinggi dijangka sekitar ${expectedWindow}.`,
      firstAction
        ? `Sila semak tindakan kesiapsiagaan institusi. Tindakan utama: ${firstAction}.`
        : "Sila semak kesiapsiagaan institusi dan kurangkan aktiviti luar yang tidak perlu dalam tempoh terjejas.",
    ].join("\n\n");
  }

  if (language === "id") {
    return [
      "PERINGATAN KABUT ASAP",
      `Kualitas udara di sekitar ${institution.name} diperkirakan memburuk hari ini.`,
      `Dampak tertinggi diperkirakan sekitar ${expectedWindow}.`,
      firstAction
        ? `Tinjau kesiapsiagaan institusi. Tindakan utama: ${firstAction}.`
        : "Tinjau kesiapsiagaan institusi dan kurangi aktivitas luar yang tidak perlu selama periode terdampak.",
    ].join("\n\n");
  }

  return [
    "HAZE ALERT",
    `Air quality around ${institution.name} is expected to worsen today.`,
    `The highest impact is expected around ${expectedWindow}.`,
    firstAction
      ? `Please review your institution's preparedness actions. Recommended first action: ${firstAction}.`
      : "Please review your institution's preparedness actions and reduce unnecessary outdoor activity during the affected period.",
  ].join("\n\n");
}

function ReliabilityIndicator({ forecast }: { forecast: Forecast }) {
  if (!forecast.uncertainty) {
    return (
      <div className="flex items-start gap-2 text-[10px] text-slate-600">
        <Info size={14} className="mt-0.5 flex-none text-slate-500" />
        <div>
          <p className="font-extrabold text-slate-700">Forecast reliability</p>
          <p>Reliability detail is unavailable for this replay.</p>
        </div>
      </div>
    );
  }

  if (forecast.uncertainty.any_point_beyond_training_range) {
    return (
      <div className="flex items-start gap-2 text-[10px] text-amber-800">
        <AlertTriangle size={14} className="mt-0.5 flex-none" />
        <div>
          <p className="font-extrabold">This forecast may be less reliable than usual.</p>
          <p className="mt-0.5 text-amber-700">Part of the forecast is outside the model's usual training range.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2 text-[10px] text-emerald-800">
      <ShieldCheck size={14} className="mt-0.5 flex-none" />
      <div>
        <p className="font-extrabold">Forecast is within the model's trained range.</p>
        <p className="mt-0.5 text-emerald-700">No beyond-training-range flag is active.</p>
      </div>
    </div>
  );
}

function EmptyPreview({ institutionName }: { institutionName: string }) {
  return (
    <ProAppShell activePage="notification-preview" scopeLabel="Institution View" forecastLabel={`Next ${PRO_HORIZON_HOURS} Hours`}>
      <main className="min-w-0 bg-white px-6 py-5 xl:px-8">
        <h2 className="text-[30px] font-extrabold tracking-tight text-ink">Institution Notification Preview</h2>
        <p className="mt-1 text-xs text-slate-500">Preview a prepared institution alert before simulated delivery.</p>
        <section className="mt-5 rounded-2xl border border-emerald-200 bg-emerald-50 p-7">
          <div className="flex items-start gap-4">
            <div className="grid h-12 w-12 place-items-center rounded-full bg-emerald-100 text-emerald-700"><CheckCircle2 /></div>
            <div>
              <h3 className="text-lg font-extrabold text-slate-800">No alert requires confirmation</h3>
              <p className="mt-2 max-w-2xl text-sm text-slate-600">{institutionName} is currently in Safe or Watch. These are monitoring states only, so no notification is prepared and Confirm &amp; Send is unavailable.</p>
              <Link href="/pro/institutions" className="mt-5 inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-xs font-extrabold text-slate-700">
                <ArrowLeft size={14} /> Back to Institution Detail
              </Link>
            </div>
          </div>
        </section>
      </main>
    </ProAppShell>
  );
}

export function ProNotificationPreview() {
  const [data, setData] = useState<ScreenData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { institutionId } = useSelectedInstitution();

  useEffect(() => {
    setError(null);
    loadProNotificationPreviewData(institutionId).then(setData).catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "Failed to load Notification Preview.");
    });
  }, [institutionId]);

  if (error) {
    return (
      <ProAppShell activePage="notification-preview" scopeLabel="Institution View" forecastLabel={`Next ${PRO_HORIZON_HOURS} Hours`}>
        <main className="p-8"><div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700"><strong>Could not load Notification Preview.</strong><p className="mt-2">{error}</p><p className="mt-2">For an offline demo, set NEXT_PUBLIC_HAZE_DATA_MODE=mock.</p></div></main>
      </ProAppShell>
    );
  }

  if (!data) {
    return <ProAppShell activePage="notification-preview" scopeLabel="Institution View" forecastLabel={`Next ${PRO_HORIZON_HOURS} Hours`}><main className="p-8 text-sm text-slate-500">
          Loading notification preview…
          <p className="mt-2 text-xs text-slate-400">The first request can take up to a minute if the demo server is waking from idle.</p>
        </main></ProAppShell>;
  }

  const risk = getLiteRiskStatus(data.forecast, data.alertResponse);
  if (risk !== "alert" || !data.alertResponse.alert) {
    return <EmptyPreview institutionName={data.institution.name} />;
  }

  return <ActivePreview data={data} alert={data.alertResponse.alert} />;
}

function ActivePreview({ data, alert }: { data: ScreenData; alert: Alert }) {
  const { institution, forecast } = data;
  const availableChannels: Channel[] = institution.contact_channels.length > 0
    ? institution.contact_channels
    : ["whatsapp"];
  const [channel, setChannel] = useState<Channel>(availableChannels.includes("whatsapp") ? "whatsapp" : availableChannels[0]);
  const [language, setLanguage] = useState(institution.languages[0] ?? "en");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [sent, setSent] = useState<Notification | null>(null);
  const [copied, setCopied] = useState(false);

  const message = useMemo(() => preparedMessage(alert, institution, language), [alert, institution, language]);
  const expectedWindow = peakWindow(alert, institution);
  const sourceArea = forecast.attribution.dominant_source_region ?? alert.source_country ?? "Not available";
  const affectedArea = `${institution.city}, ${institution.admin_region}`;

  async function copyPreview() {
    try {
      await navigator.clipboard.writeText(message);
      setCopied(true);
      globalThis.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  /**
   * Purely local. No request is made — the backend has no endpoint this should
   * write to, and the demo must behave identically with the server stopped.
   */
  function doConfirm() {
    setSent(
      confirmProNotification({
        institution,
        alertId: alert.alert_id,
        channel,
        language,
        previewMessage: message,
      }),
    );
    setConfirmOpen(false);
  }

  return (
    <ProAppShell activePage="notification-preview" scopeLabel="Institution View" forecastLabel={`Next ${PRO_HORIZON_HOURS} Hours`} institutions={data.institutions} current={institution} health={data.health} at={data.at}>
      <main className="min-w-0 bg-white">
        <div className="px-6 py-5 xl:px-8">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-[30px] font-extrabold tracking-tight text-ink">Institution Notification Preview</h2>
              <p className="mt-1 text-xs text-slate-500">Preview how the current institution-level haze alert could be sent to its verified institution contact.</p>
            </div>
            <div className="text-right">
              <span className="inline-flex rounded-xl border border-violet-200 bg-violet-50 px-4 py-2 text-[10px] font-extrabold text-violet-700">Prototype Simulation</span>
              <p className="mt-1 text-[9px] text-slate-400">Confirmation and delivery are simulated. No external message is sent.</p>
            </div>
          </div>

          <section className="mt-3 grid items-center gap-3 rounded-2xl border border-red-200 bg-red-50/55 p-4 xl:grid-cols-[1.55fr_.72fr_.72fr_.7fr_auto]">
            <div className="flex min-w-0 items-center gap-3">
              <span className="grid h-7 w-7 flex-none place-items-center rounded-full bg-red-600 text-[11px] font-extrabold text-white">1</span>
              <div className="grid h-11 w-11 flex-none place-items-center rounded-full bg-red-100 text-red-600"><AlertTriangle size={23} fill="currentColor" /></div>
              <div className="min-w-0"><p className="text-[17px] font-extrabold text-red-600">Alert — High haze impact expected</p><p className="mt-1 truncate text-[9px] text-slate-500">{institution.name}</p></div>
            </div>
            <div className="border-l border-red-100 pl-4"><p className="text-[9px] text-slate-500">Forecast trigger peak</p><p className="mt-1 text-lg font-extrabold text-red-600">{alert.forecast_peak_pm25.toFixed(1)} <span className="text-xs">µg/m³</span></p></div>
            <div className="border-l border-red-100 pl-4"><p className="text-[9px] text-slate-500">Expected peak</p><p className="mt-1 text-lg font-extrabold text-orange-600">{expectedWindow}</p></div>
            <div className="border-l border-red-100 pl-4"><p className="text-[9px] text-slate-500">Warning lead time</p><p className="mt-1 text-lg font-extrabold text-slate-800">{alert.lead_time_hours}h</p></div>
            <Link href="/pro/institutions" className="justify-self-end text-[9px] font-extrabold text-red-600">View Institution Alert →</Link>
          </section>

          <div className="mt-3 grid gap-3 xl:grid-cols-[.77fr_1.33fr]">
            <section className="rounded-2xl border border-blue-100 bg-blue-50/55 p-4">
              <div className="flex items-center gap-2"><span className="grid h-6 w-6 place-items-center rounded-full bg-blue-600 text-[10px] font-extrabold text-white">2</span><h3 className="text-sm font-extrabold text-slate-800">Notification Setup</h3></div>
              <div className="mt-4 space-y-3 text-[10px]">
                <label className="grid grid-cols-[105px_1fr] items-center gap-3"><span className="font-semibold text-slate-500">Institution</span><span className="rounded-xl border border-slate-200 bg-white px-3 py-3 font-semibold text-slate-700">{institution.name}</span></label>
                <label className="grid grid-cols-[105px_1fr] items-center gap-3"><span className="font-semibold text-slate-500">Delivery target</span><span className="rounded-xl border border-slate-200 bg-white px-3 py-3 font-semibold text-slate-700">Verified institution contact</span></label>
                <div className="grid grid-cols-[105px_1fr] items-center gap-3"><span className="font-semibold text-slate-500">Channel</span><div className="grid grid-cols-2 gap-2">{availableChannels.map((item) => <button key={item} type="button" onClick={() => setChannel(item)} className={`rounded-xl border px-3 py-3 text-[10px] font-extrabold ${channel === item ? "border-emerald-300 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-white text-slate-500"}`}>{item === "whatsapp" ? "WhatsApp" : "SMS"}</button>)}</div></div>
                <label className="grid grid-cols-[105px_1fr] items-center gap-3"><span className="font-semibold text-slate-500">Preview language</span><select value={language} onChange={(event) => setLanguage(event.target.value)} className="rounded-xl border border-slate-200 bg-white px-3 py-3 font-semibold text-slate-700 outline-none">{institution.languages.map((item) => <option key={item} value={item}>{languageLabel(item)}</option>)}</select></label>
              </div>

              <div className="mt-4 rounded-xl border border-blue-100 bg-white/70 p-3">
                <p className="text-[10px] font-extrabold text-slate-600">Current status guide</p>
                <div className="mt-3 grid grid-cols-3 gap-2 text-[9px]">
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-2"><strong className="text-emerald-700">✓ Safe</strong><p className="mt-1 text-slate-500">Monitoring only</p></div>
                  <div className="rounded-lg border border-amber-200 bg-amber-50 p-2"><strong className="text-amber-700">● Watch</strong><p className="mt-1 text-slate-500">Monitoring only</p></div>
                  <div className="rounded-lg border-2 border-red-300 bg-red-50 p-2"><strong className="text-red-600">▲ Alert</strong><p className="mt-1 text-red-500">Confirmation available</p></div>
                </div>
                <p className="mt-3 text-[9px] leading-4 text-slate-500">Status comes from the forecast. Safe and Watch do not create a send action; only Alert can be confirmed.</p>
              </div>
            </section>

            <section className="rounded-2xl border border-emerald-100 bg-emerald-50/45 p-4">
              <div className="flex items-center justify-between gap-3"><div className="flex items-center gap-2"><span className="grid h-6 w-6 place-items-center rounded-full bg-emerald-600 text-[10px] font-extrabold text-white">3</span><h3 className="text-sm font-extrabold text-slate-800">{channel === "whatsapp" ? "WhatsApp" : "SMS"} Preview</h3></div><span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[9px] font-bold text-emerald-700">Based on current alert</span></div>

              <div className="mx-auto mt-4 max-w-[680px] overflow-hidden rounded-[28px] border-[5px] border-slate-800 bg-[#efe6d6] shadow-xl">
                <div className="flex items-center gap-3 bg-white px-4 py-3"><ArrowLeft size={16} /><div className="grid h-8 w-8 place-items-center rounded-full bg-teal-400 text-white"><MessageCircle size={15} /></div><div><p className="text-[11px] font-extrabold text-slate-800">Haze Alert Preview</p><p className="text-[8px] text-slate-400">Prototype message</p></div></div>
                <div className="p-6">
                  <p className="mx-auto mb-4 w-fit rounded-full bg-white/80 px-3 py-1 text-[8px] text-slate-400">Preview · {localStamp(alert.triggered_at, institution.country)}</p>
                  <div className="mx-auto max-w-[520px] whitespace-pre-line rounded-xl bg-white p-4 text-[10px] leading-5 text-slate-700 shadow-sm">{message}<p className="mt-4 font-extrabold text-slate-600">Updated: {localStamp(alert.triggered_at, institution.country)}</p></div>
                </div>
              </div>

              {/*
                Shown only when the preview is not English. The message body is
                localised but the recommended-action sentence is not: the API
                serves that copy in English only. Saying so is better than a
                message that looks fully translated and is not.
              */}
              {language !== "en" && (
                <p className="mt-3 flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[9px] leading-4 text-amber-800">
                  <AlertTriangle size={11} className="mt-0.5 flex-none" />
                  <span>The recommended action is shown in English. The alert API serves that copy in English only, so it is not translated for this preview — the rest of the message is in {languageLabel(language)}.</span>
                </p>
              )}

              <div className="mt-4 flex flex-wrap items-center justify-between gap-2"><p className="flex items-center gap-1 text-[9px] text-slate-400"><Info size={11} /> Preview only — no recipients will be contacted until confirmation, and delivery remains simulated.</p><div className="flex gap-2"><button type="button" onClick={() => setChannel(channel === "whatsapp" && availableChannels.includes("sms") ? "sms" : "whatsapp")} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[9px] font-extrabold text-blue-600">Switch Preview</button><button type="button" onClick={copyPreview} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[9px] font-extrabold text-blue-600">{copied ? <Check size={12} /> : <Copy size={12} />}{copied ? "Copied" : "Copy Preview"}</button></div></div>
            </section>
          </div>

          <section className="mt-3 rounded-2xl border border-violet-100 bg-violet-50/55 p-4">
            <div className="flex items-center gap-2"><span className="grid h-6 w-6 place-items-center rounded-full bg-violet-600 text-[10px] font-extrabold text-white">4</span><h3 className="text-sm font-extrabold text-slate-800">Why This Notification?</h3><p className="text-[9px] text-slate-500">This preview is based on the current institution-level haze forecast.</p></div>
            <div className="mt-3 grid gap-2 md:grid-cols-5">
              <div className="rounded-xl border border-violet-100 bg-white p-3"><p className="text-[9px] text-slate-500">Alert status</p><p className="mt-2 text-sm font-extrabold text-red-600">Alert</p></div>
              <div className="rounded-xl border border-violet-100 bg-white p-3"><p className="text-[9px] text-slate-500">Forecast trigger peak</p><p className="mt-2 text-sm font-extrabold text-red-600">{alert.forecast_peak_pm25.toFixed(1)} µg/m³</p></div>
              <div className="rounded-xl border border-violet-100 bg-white p-3"><p className="text-[9px] text-slate-500">Expected peak</p><p className="mt-2 text-sm font-extrabold text-orange-600">{expectedWindow}</p></div>
              <div className="rounded-xl border border-violet-100 bg-white p-3"><p className="text-[9px] text-slate-500">Associated source area</p><p className="mt-2 text-sm font-extrabold text-violet-700">{sourceArea}</p></div>
              <div className="rounded-xl border border-violet-100 bg-white p-3"><p className="text-[9px] text-slate-500">Affected area</p><p className="mt-2 text-sm font-extrabold text-blue-700">{affectedArea}</p></div>
            </div>
            <p className="mt-3 flex items-center gap-1 text-[9px] text-slate-400"><Info size={11} /> Forecasts may change as new environmental data becomes available.</p>
          </section>

          <section className="mt-3 rounded-2xl border border-blue-200 bg-blue-50/55 p-4">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div className="flex min-w-0 items-start gap-4"><div className="grid h-11 w-11 flex-none place-items-center rounded-full bg-blue-100 text-blue-600"><Send size={20} fill="currentColor" /></div><div><h3 className="text-sm font-extrabold text-ink">Ready to proceed?</h3><p className="mt-1 text-[10px] text-slate-600">Human-in-the-loop: an authorized institution user reviews and confirms the alert before it enters the simulated notification feed.</p></div></div>
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center"><div className="rounded-xl border border-white/80 bg-white/70 px-3 py-2"><ReliabilityIndicator forecast={forecast} /></div><div className="flex flex-none gap-2"><Link href="/pro/alert-history" className="inline-flex items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-3 text-[10px] font-extrabold text-slate-700">Back to Alert History</Link><button type="button" onClick={() => setConfirmOpen(true)} disabled={Boolean(sent)} className="inline-flex min-w-[128px] items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-3 text-[10px] font-extrabold text-white shadow-sm disabled:cursor-not-allowed disabled:bg-emerald-600">{sent ? <><Check size={14} /> Confirmed</> : <><Send size={14} /> Confirm &amp; Send</>}</button></div></div>
            </div>
            
            {sent && <p className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-[10px] font-semibold text-emerald-700">Simulation recorded as {sent.status}. Sent to: {institution.name} admin contact · {sent.channel.toUpperCase()} · simulated: {String(sent.simulated ?? true)}.</p>}
          </section>

          <div className="mt-3 flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-[9px] text-slate-500"><LockKeyhole size={12} /> This prototype simulates alert confirmation and delivery without connecting to external messaging services. Messages are associated only with verified institution contacts.</div>
        </div>
      </main>

      {confirmOpen && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/45 p-4" role="dialog" aria-modal="true" aria-labelledby="pro-confirm-title">
          <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3"><div className="grid h-10 w-10 flex-none place-items-center rounded-full bg-blue-100 text-blue-600"><Send size={18} /></div><div><h3 id="pro-confirm-title" className="text-lg font-extrabold text-slate-800">Confirm simulated delivery?</h3><p className="mt-1 text-xs leading-5 text-slate-600">This records a simulated notification for the verified institution contact at {institution.name}. No external SMS or WhatsApp message will be delivered.</p></div></div>
              <button type="button" onClick={() => setConfirmOpen(false)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100" aria-label="Close confirmation"><X size={18} /></button>
            </div>
            <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-3 text-[11px] text-slate-600"><p><strong>Channel:</strong> {channel === "whatsapp" ? "WhatsApp" : "SMS"}</p><p className="mt-1"><strong>Language:</strong> {languageLabel(language)}</p><p className="mt-1"><strong>Recipient:</strong> Verified institution contact</p><p className="mt-1"><strong>Prototype:</strong> Simulated delivery only</p></div>
            
            <div className="mt-6 flex justify-end gap-2"><button type="button" onClick={() => setConfirmOpen(false)} className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-xs font-extrabold text-slate-700">Cancel</button><button type="button" onClick={doConfirm} className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-extrabold text-white"><Send size={14} /> Confirm &amp; Send</button></div>
          </div>
        </div>
      )}
    </ProAppShell>
  );
}

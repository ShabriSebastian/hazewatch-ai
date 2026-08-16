"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCircle2,
  CircleUserRound,
  Info,
  LockKeyhole,
  MessageCircle,
  Send,
  Smartphone,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Alert, Channel, Forecast, Institution, Notification } from "@/lib/api/types";
import { confirmLiteNotification, loadLiteOverviewData } from "@/lib/data/source";
import { getWhatThisMeansLine } from "@/lib/ui/copy";
import { localStamp, peakTime, reliabilityNote } from "@/lib/ui/format";
import { useSelectedInstitution } from "@/lib/ui/institutionContext";
import { getLiteRiskStatus } from "@/lib/ui/status";
import { AppShell } from "./AppShell";

type ScreenData = Awaited<ReturnType<typeof loadLiteOverviewData>>;

/** The closing line of the prepared message, worded for the audience. */
function closingFor(type: Institution["type"], firstAction: string | undefined) {
  switch (type) {
    case "hospital":
      return firstAction
        ? `Please review operational readiness. Recommended first action: ${firstAction}.`
        : `Please review indoor filtration and respiratory-service readiness during the affected period.`;
    case "authority":
      return firstAction
        ? `Please review district advisory plans. Recommended first action: ${firstAction}.`
        : `Please review public advisory and coordination plans for the affected period.`;
    case "school":
      return firstAction
        ? `Please follow your school's instructions. Recommended first action: ${firstAction}.`
        : `Please reduce unnecessary outdoor activity during the affected period.`;
    default:
      return firstAction
        ? `Please review your preparedness plans. Recommended first action: ${firstAction}.`
        : `Please reduce unnecessary exposure during the affected period.`;
  }
}

function previewMessage(alert: Alert, institution: Institution) {
  const peak = peakTime(alert.forecast_peak_at, institution.country);

  return [
    `HAZE ALERT`,
    `Air quality around ${institution.name} is expected to worsen.`,
    `The highest impact is expected around ${peak}, about ${alert.lead_time_hours} hours from now.`,
    closingFor(institution.type, alert.recommended_actions[0]),
  ].join("\n\n");
}

/**
 * Only the beyond-training-range caveat is rendered. An earlier draft also
 * showed a green "within the model's usual operating range" panel, which
 * amounts to inventing the reassuring half of a confidence scale the backend
 * never defines. Absence of the flag is not a positive signal.
 */
function ReliabilityIndicator({ forecast }: { forecast: Forecast }) {
  const note = reliabilityNote(forecast);
  if (!note) return null;

  return (
    <div className="flex max-w-[330px] items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] text-amber-800">
      <AlertTriangle size={14} className="mt-0.5 flex-none" />
      <div>
        <p className="font-extrabold">This forecast may be less reliable than usual.</p>
        <p className="mt-0.5 text-amber-700">{note}</p>
      </div>
    </div>
  );
}

function EmptyReview({ data }: { data: ScreenData }) {
  const { institution, institutions, health, at } = data;

  return (
    <AppShell activePage="alert-review" institutions={institutions} current={institution} health={health} at={at}>
      <main className="min-w-0 px-6 py-5 lg:px-7 lg:py-6">
        <h2 className="text-[31px] font-extrabold tracking-tight text-ink">Alert Review</h2>
        <p className="mt-1 text-xs text-slate-500">Review prepared alerts before sending them to your institution&apos;s verified admin contact.</p>

        <section className="mt-5 rounded-2xl border border-emerald-200 bg-emerald-50 p-7">
          <div className="flex items-start gap-4">
            <div className="grid h-12 w-12 place-items-center rounded-full bg-emerald-100 text-emerald-700"><CheckCircle2 /></div>
            <div>
              <h3 className="text-lg font-extrabold text-slate-800">No alert requires review</h3>
              <p className="mt-2 text-sm text-slate-600">{institution.name} is currently in an informational Safe or Watch state. Confirm &amp; Send is available only when the forecast reaches Alert.</p>
              <Link href="/lite/institution-detail" className="mt-5 inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-xs font-extrabold text-slate-700">
                <ArrowLeft size={14} /> Back to Institution Detail
              </Link>
            </div>
          </div>
        </section>
      </main>
    </AppShell>
  );
}

export function LiteAlertReview() {
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
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load Alert Review.");
      });

    return () => {
      cancelled = true;
    };
  }, [institutionId]);

  if (error) {
    return (
      <AppShell activePage="alert-review">
        <main className="p-8">
          <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
            <strong>Could not load Alert Review.</strong>
            <p className="mt-2">{error}</p>
            <p className="mt-2">For an offline demo, set NEXT_PUBLIC_HAZE_DATA_MODE=mock.</p>
          </div>
        </main>
      </AppShell>
    );
  }

  if (!data) {
    return (
      <AppShell activePage="alert-review">
        <main className="p-8 text-sm text-slate-500">
          Loading alert review…
          <p className="mt-2 text-xs text-slate-400">The first request can take up to a minute if the demo server is waking from idle.</p>
        </main>
      </AppShell>
    );
  }

  return <Loaded data={data} />;
}

function Loaded({ data }: { data: ScreenData }) {
  const { forecast, alertResponse } = data;
  const risk = useMemo(() => getLiteRiskStatus(forecast, alertResponse), [forecast, alertResponse]);
  const alert = alertResponse.alert;

  if (risk !== "alert" || !alert) {
    return <EmptyReview data={data} />;
  }

  return <ActiveAlertReview data={data} alert={alert} />;
}

function ActiveAlertReview({ data, alert }: { data: ScreenData; alert: Alert }) {
  const { institution, institutions, forecast, health, at } = data;
  const availableChannels = institution.contact_channels.length > 0 ? institution.contact_channels : (["whatsapp"] as Channel[]);
  const initialChannel: Channel = availableChannels.includes("whatsapp") ? "whatsapp" : availableChannels[0];
  const [channel, setChannel] = useState<Channel>(initialChannel);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [sent, setSent] = useState<Notification | null>(null);
  const message = useMemo(() => previewMessage(alert, institution), [alert, institution]);
  const language = institution.languages[0] ?? "en";

  /**
   * Purely local. No request is made — the backend has no endpoint this should
   * write to, and the demo must behave identically with the server stopped.
   */
  function doConfirm() {
    setSent(
      confirmLiteNotification({
        institution,
        channel,
        language,
        previewMessage: message,
      }),
    );
    setConfirmOpen(false);
  }

  return (
    <AppShell activePage="alert-review" institutions={institutions} current={institution} health={health} at={at}>
      <main className="min-w-0 px-6 py-5 lg:px-7 lg:py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-[31px] font-extrabold tracking-tight text-ink">Alert Review</h2>
            <p className="mt-1 text-xs text-slate-500">Review the prepared alert before sending it to your institution&apos;s verified admin contact.</p>
          </div>
          <div className="flex min-w-[310px] items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-[11px] shadow-sm">
            <span className="text-slate-500">Viewing:</span>
            <span className="ml-4 max-w-[240px] truncate font-extrabold text-slate-700">{institution.name}</span>
          </div>
        </div>

        <div className="mt-4 grid gap-3 xl:grid-cols-3">
          <section className="rounded-2xl border border-red-200 bg-red-50/65 p-5">
            <div className="flex items-center gap-4">
              <div className="grid h-14 w-14 flex-none place-items-center rounded-full bg-red-100 text-red-600"><AlertTriangle size={29} fill="currentColor" /></div>
              <div>
                <p className="text-[10px] text-slate-500">Current forecast status <span className="ml-2 rounded-full bg-red-100 px-2 py-1 text-[9px] font-extrabold text-red-600">Forecast Alert</span></p>
                <p className="mt-2 text-[17px] font-extrabold leading-tight text-slate-800">Air quality is expected to worsen, with {alert.lead_time_hours}h warning.</p>
              </div>
            </div>
          </section>

          <section className="rounded-2xl border border-blue-200 bg-blue-50/55 p-5">
            <div className="flex items-center gap-4">
              <div className="grid h-14 w-14 flex-none place-items-center rounded-full bg-blue-100 text-blue-600"><CircleUserRound size={29} fill="currentColor" /></div>
              <div>
                <p className="text-[10px] text-slate-500">Delivery target</p>
                <p className="mt-1 text-[17px] font-extrabold text-slate-800">Verified admin contact</p>
                <p className="mt-1 text-[10px] text-slate-500">{institution.name}</p>
              </div>
            </div>
          </section>

          <section className="rounded-2xl border border-orange-200 bg-orange-50/60 p-5">
            <div className="flex items-center gap-4">
              <div className="grid h-14 w-14 flex-none place-items-center rounded-full bg-orange-100 text-orange-600"><Info size={28} /></div>
              <div>
                <p className="text-[10px] text-slate-500">What this means</p>
                <p className="mt-1 text-[16px] font-extrabold leading-tight text-slate-800">{getWhatThisMeansLine(institution.type)}</p>
              </div>
            </div>
          </section>
        </div>

        <div className="mt-3 grid gap-3 xl:grid-cols-[1.28fr_1fr]">
          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-extrabold text-ink">Prepared message</h3>

            <div className="mt-4 grid grid-cols-2 gap-2">
              {(["whatsapp", "sms"] as Channel[]).map((item) => {
                const enabled = availableChannels.includes(item);
                const active = channel === item;
                return (
                  <button
                    key={item}
                    type="button"
                    disabled={!enabled}
                    onClick={() => enabled && setChannel(item)}
                    className={`rounded-xl border px-4 py-2.5 text-[11px] font-extrabold transition ${
                      active
                        ? item === "whatsapp"
                          ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                          : "border-blue-300 bg-blue-50 text-blue-700"
                        : enabled
                          ? "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                          : "cursor-not-allowed border-slate-100 bg-slate-50 text-slate-300"
                    }`}
                  >
                    {item === "whatsapp" ? <MessageCircle className="mr-1 inline" size={13} /> : <Smartphone className="mr-1 inline" size={13} />}
                    {item === "whatsapp" ? "WhatsApp Preview" : "SMS Preview"}
                  </button>
                );
              })}
            </div>

            <div className="mt-5 rounded-[26px] border-[5px] border-slate-800 bg-[#eee8dc] shadow-sm">
              <div className="flex items-center gap-3 rounded-t-[20px] bg-white px-5 py-4">
                <ArrowLeft size={18} className="text-slate-700" />
                <div className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-blue-400 to-emerald-300 text-white">≈</div>
                <div>
                  <p className="text-xs font-extrabold text-slate-800">Haze Alert</p>
                  <p className="text-[9px] text-slate-400">{sent ? "Simulated · not actually sent" : "Preview · not yet sent"}</p>
                </div>
              </div>
              <div className="p-8">
                <div className="max-w-[92%] rounded-2xl bg-white p-4 text-[10px] leading-5 text-slate-700 shadow-sm">
                  {message.split("\n\n").map((part, index) => (
                    <p key={`${part}-${index}`} className={index === 0 ? "font-extrabold text-slate-800" : "mt-3"}>{index === 0 ? `⚠ ${part}` : part}</p>
                  ))}
                  <p className="mt-3 font-bold text-slate-600">Updated: {localStamp(alert.triggered_at, institution.country)}</p>
                </div>
              </div>
            </div>
            <p className="mt-4 flex items-center gap-1.5 text-[10px] text-slate-500"><Info size={12} /> {sent ? "This alert was confirmed. Delivery is simulated; nothing was sent." : "This alert is prepared but not yet sent."}</p>
          </section>

          <div className="space-y-3">
            <section className="rounded-2xl border border-violet-200 bg-violet-50/60 p-5">
              <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><CheckCircle2 size={16} /> Before you send</h3>
              <div className="mt-3 divide-y divide-violet-100">
                {alert.recommended_actions.map((action, index) => (
                  <div key={`${action}-${index}`} className="flex items-center gap-3 py-3 text-[10px] text-slate-600">
                    <span className="grid h-7 w-7 flex-none place-items-center rounded-full bg-violet-100 text-violet-600"><Check size={14} /></span>
                    {action}
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-red-200 bg-red-50/50 p-5">
              <h3 className="flex items-center gap-2 text-sm font-extrabold text-ink"><AlertTriangle size={16} /> Alert details</h3>
              <dl className="mt-3 divide-y divide-red-100 text-[10px]">
                <div className="flex justify-between gap-5 py-2.5"><dt className="text-slate-500">Institution</dt><dd className="text-right font-extrabold text-slate-700">{institution.name}</dd></div>
                <div className="flex justify-between gap-5 py-2.5"><dt className="text-slate-500">Expected peak</dt><dd className="font-extrabold text-slate-700">{localStamp(alert.forecast_peak_at, institution.country)}</dd></div>
                <div className="flex justify-between gap-5 py-2.5"><dt className="text-slate-500">Warning lead time</dt><dd className="font-extrabold text-slate-700">{alert.lead_time_hours} hours</dd></div>
                <div className="flex justify-between gap-5 py-2.5"><dt className="text-slate-500">Message status</dt><dd className="font-extrabold text-slate-700">{sent ? "Confirmed · simulated delivery" : "Prepared for verified admin contact"}</dd></div>
              </dl>
              <p className={`mt-3 flex items-center gap-1.5 border-t border-red-100 pt-3 text-[10px] font-extrabold ${sent ? "text-emerald-700" : "text-red-600"}`}>
                {sent ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
                {sent ? "Confirmation recorded. No external SMS or WhatsApp was sent." : "It will not be sent until you confirm."}
              </p>
            </section>
          </div>
        </div>

        <section className="mt-3 rounded-2xl border border-blue-200 bg-blue-50/65 px-5 py-4">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div className="flex min-w-0 items-start gap-4">
              <div className="grid h-11 w-11 flex-none place-items-center rounded-full bg-blue-100 text-blue-600"><Send size={20} fill="currentColor" /></div>
              <div>
                <h3 className="text-sm font-extrabold text-ink">Ready to proceed?</h3>
                <p className="mt-1 text-[10px] text-slate-600">Human-in-the-loop: an authorized institution staff member reviews and confirms the alert before it is sent.</p>
              </div>
            </div>

            <div className="flex flex-col gap-3 md:flex-row md:items-center">
              <ReliabilityIndicator forecast={forecast} />
              <div className="flex flex-none gap-2">
                <Link href="/lite/institution-detail" className="inline-flex items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-3 text-[10px] font-extrabold text-slate-700">Back to Institution Detail</Link>
                <button
                  type="button"
                  onClick={() => setConfirmOpen(true)}
                  disabled={Boolean(sent)}
                  className="inline-flex min-w-[128px] items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-3 text-[10px] font-extrabold text-white shadow-sm disabled:cursor-not-allowed disabled:bg-emerald-600"
                >
                  {sent ? <><Check size={14} /> Confirmed</> : <><Send size={14} /> Confirm &amp; Send</>}
                </button>
              </div>
            </div>
          </div>

          {sent && (
            <p className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-[10px] font-semibold text-emerald-700">
              Sent to: {institution.name} admin contact — {localStamp(sent.sent_at, institution.country)} · {sent.channel.toUpperCase()} · simulated: {String(sent.simulated ?? true)}.
            </p>
          )}
        </section>

        <div className="mt-3 flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-[10px] text-slate-500">
          <LockKeyhole size={13} /> Messages are sent only to an institution&apos;s verified admin contact. This prototype does not send messages to public or personal phone numbers.
        </div>
        <p className="mt-2 text-[9px] text-slate-400">MVP note: authentication is not implemented, and delivery is simulated end to end — Confirm &amp; Send records the confirmation in this browser only and contacts no external service.</p>
      </main>

      {confirmOpen && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/45 p-4" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
          <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="grid h-10 w-10 flex-none place-items-center rounded-full bg-blue-100 text-blue-600"><Send size={18} /></div>
                <div>
                  <h3 id="confirm-title" className="text-lg font-extrabold text-slate-800">Confirm alert delivery?</h3>
                  <p className="mt-1 text-xs leading-5 text-slate-600">This records a simulated notification for the verified admin contact at {institution.name}. No external message will be delivered.</p>
                </div>
              </div>
              <button type="button" onClick={() => setConfirmOpen(false)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100" aria-label="Close confirmation"><X size={18} /></button>
            </div>

            <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-3 text-[11px] text-slate-600">
              <p><strong>Channel:</strong> {channel === "whatsapp" ? "WhatsApp" : "SMS"}</p>
              <p className="mt-1"><strong>Recipient:</strong> Verified institution admin contact</p>
              <p className="mt-1"><strong>Prototype:</strong> Simulated delivery only</p>
            </div>

            <div className="mt-6 flex justify-end gap-2">
              <button type="button" onClick={() => setConfirmOpen(false)} className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-xs font-extrabold text-slate-700">Cancel</button>
              <button type="button" onClick={doConfirm} className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-extrabold text-white">
                <Send size={14} /> Confirm &amp; Send
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}

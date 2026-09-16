/**
 * The Confirm & Send record.
 *
 * Moved out of `lib/data/mock.ts` when mock mode was removed: this is the one
 * thing in that module that ran in every mode, because Confirm & Send is
 * simulated locally in both Lite and Pro regardless of where data comes from.
 */

import type { Channel, Institution, Notification } from "@/lib/api/types";

/**
 * Builds the record shown after Confirm & Send. Purely local — nothing is sent,
 * and `simulated` is always true, which the UI is required to surface.
 */
export function createLocalNotification({
  institution,
  channel,
  message,
  language,
  alertId,
}: {
  institution: Institution;
  channel: Channel;
  message: string;
  language: string;
  alertId?: string;
}): Notification {
  const sentAt = new Date().toISOString();

  return {
    notification_id: `local-${Date.parse(sentAt)}`,
    // No alert to attach to is a legitimate state: staff can preview a message
    // for an institution that is not currently alerting.
    alert_id: alertId ?? `local-preview-${institution.id}`,
    institution_id: institution.id,
    institution_name: institution.name,
    country: institution.country,
    channel,
    recipient_group: institution.recipient_group ?? "verified-admin-contact",
    recipient_count: 1,
    language,
    sent_at: sentAt,
    status: "sent",
    message,
    simulated: true,
  };
}

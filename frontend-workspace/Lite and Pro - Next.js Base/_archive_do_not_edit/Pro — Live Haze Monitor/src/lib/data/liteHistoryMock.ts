export type LiteStatusTimelineItem = {
  id: string;
  occurredAt: string;
  status: "safe" | "watch" | "alert";
  message: string;
  actionLabel: string;
};

/**
 * Demo-only timeline snapshots for the offline mock experience.
 * Kept outside API contract types so these UI snapshots can be replaced
 * without inventing backend fields.
 */
export const mockLiteStatusTimeline: LiteStatusTimelineItem[] = [
  {
    id: "today-alert",
    occurredAt: "2023-09-02T14:10:00Z",
    status: "alert",
    message: "Air quality expected to worsen this afternoon.",
    actionLabel: "Prepared · Not sent",
  },
  {
    id: "today-watch",
    occurredAt: "2023-09-02T12:45:00Z",
    status: "watch",
    message: "Conditions may worsen later today.",
    actionLabel: "Monitoring only",
  },
  {
    id: "today-safe",
    occurredAt: "2023-09-02T10:20:00Z",
    status: "safe",
    message: "Normal monitoring.",
    actionLabel: "No action needed",
  },
  {
    id: "yesterday-watch",
    occurredAt: "2023-09-01T18:30:00Z",
    status: "watch",
    message: "Conditions may worsen tomorrow morning.",
    actionLabel: "Monitoring only",
  },
  {
    id: "yesterday-safe",
    occurredAt: "2023-09-01T09:15:00Z",
    status: "safe",
    message: "Normal monitoring.",
    actionLabel: "No action needed",
  },
];

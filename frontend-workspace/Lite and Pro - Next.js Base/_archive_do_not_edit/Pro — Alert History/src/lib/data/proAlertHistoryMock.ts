export type ProHistoryStatus = "safe" | "watch" | "alert";

export interface ProHistoryEvent {
  id: string;
  timestamp: string;
  status: ProHistoryStatus;
  title: string;
  description: string;
  forecastPeak?: number;
  previousPeak?: number;
  sourceArea?: string;
  direction?: string;
  transportHours?: string;
  notificationState?: "not-needed" | "monitoring" | "prepared" | "sent";
}

export const proMockHistoryEvents: ProHistoryEvent[] = [
  {
    id: "hist-alert-1",
    timestamp: "2023-09-02T16:00:00Z",
    status: "alert",
    title: "Forecast upgraded to Alert",
    description: "Upper-band PM2.5 forecast crossed the validated 35.5 µg/m³ operating threshold.",
    forecastPeak: 57.7,
    previousPeak: 33.8,
    sourceArea: "West Kalimantan, Indonesia",
    direction: "West → Northeast",
    transportHours: "18h",
    notificationState: "prepared",
  },
  {
    id: "hist-watch-1",
    timestamp: "2023-09-02T13:45:00Z",
    status: "watch",
    title: "Cross-border haze approaching",
    description: "Forecast conditions moved into Watch while transport from West Kalimantan toward Sarawak strengthened.",
    forecastPeak: 33.8,
    previousPeak: 26.2,
    sourceArea: "West Kalimantan, Indonesia",
    direction: "West → Northeast",
    transportHours: "20h",
    notificationState: "monitoring",
  },
  {
    id: "hist-safe-1",
    timestamp: "2023-09-02T10:20:00Z",
    status: "safe",
    title: "Normal monitoring",
    description: "No significant forecast impact was expected around this institution.",
    forecastPeak: 11.6,
    notificationState: "not-needed",
  },
  {
    id: "hist-watch-2",
    timestamp: "2023-09-01T18:30:00Z",
    status: "watch",
    title: "PM2.5 forecast increased",
    description: "Short-term PM2.5 levels moved above the Safe range and continued to be monitored.",
    forecastPeak: 28.9,
    previousPeak: 18.4,
    notificationState: "monitoring",
  },
  {
    id: "hist-safe-2",
    timestamp: "2023-09-01T09:15:00Z",
    status: "safe",
    title: "Normal monitoring",
    description: "Forecast remained within the Safe range.",
    forecastPeak: 10.2,
    notificationState: "not-needed",
  },
];

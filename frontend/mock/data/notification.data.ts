// mock/data/notification.data.ts — background analysis alerts for the header bell.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : A fixed set of notifications covering every severity level.
// where : Served by the notifications route.
// how   : Fixed rather than generated so all four severities are always visible during review — a random
//         feed would sometimes contain no critical alert and the critical styling would go unverified.

import type { AerisNotification } from "@/features/notifications/types/notification.types";

const REFERENCE_TIME_MS = Date.parse("2026-08-26T09:00:00.000Z");
const MINUTE_MS = 60_000;

export const MOCK_NOTIFICATIONS: readonly AerisNotification[] = [
  {
    id: "ntf_001",
    title: "Change detected — Sundarbans Delta",
    body: "Monitoring mission flagged a 6.1% water extent increase against baseline. Confidence 89%.",
    severity: "critical",
    createdAt: new Date(REFERENCE_TIME_MS - 4 * MINUTE_MS).toISOString(),
    missionId: "msn_0002",
  },
  {
    id: "ntf_002",
    title: "Analysis complete — Mumbai Coastal Belt",
    body: "Built-up change quantification finished. 14.2 ha of new built-up surface.",
    severity: "success",
    createdAt: new Date(REFERENCE_TIME_MS - 26 * MINUTE_MS).toISOString(),
    missionId: "msn_0001",
  },
  {
    id: "ntf_003",
    title: "SegFormer-B4 degraded",
    body: "Segmentation latency is elevated at 6.5 s median. Queue depth 11.",
    severity: "warning",
    createdAt: new Date(REFERENCE_TIME_MS - 52 * MINUTE_MS).toISOString(),
    missionId: null,
  },
  {
    id: "ntf_004",
    title: "12 scenes ingested",
    body: "Sentinel-2 batch for the Mekong Delta corridor finished preprocessing.",
    severity: "info",
    createdAt: new Date(REFERENCE_TIME_MS - 3 * 60 * MINUTE_MS).toISOString(),
    missionId: null,
  },
];

export const MOCK_UNREAD_NOTIFICATION_COUNT = 3;

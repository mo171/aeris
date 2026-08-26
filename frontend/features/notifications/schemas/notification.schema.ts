// features/notifications/schemas/notification.schema.ts — contract for background analysis alerts.
//
// what  : Zod schema for a single notification and the collection endpoint response.
// where : Parsed by notification.service.ts; the inferred types drive the header bell on every page.
// how   : Notifications are their own feature rather than part of Mission Command because all seven AERIS
//         surfaces show the same bell — a completed background analysis must reach the operator wherever
//         they are. Severity is an enum rather than a boolean because the bell colour and the pulse
//         behaviour differ per level.

import { z } from "zod";

import { isoTimestampSchema } from "@/features/missionCommand/schemas/shared.schema";

export const notificationSeveritySchema = z.enum(["info", "success", "warning", "critical"]);

export const notificationSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  body: z.string(),
  severity: notificationSeveritySchema,
  createdAt: isoTimestampSchema,
  /** Set when the alert originated from a monitoring mission, so the bell can deep-link to it. */
  missionId: z.string().nullable(),
});

export const notificationCollectionSchema = z.object({
  notifications: z.array(notificationSchema),
  unreadCount: z.number().int().nonnegative(),
});

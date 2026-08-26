// features/notifications/types/notification.types.ts — notification types, inferred from the Zod schemas.
//
// what  : TypeScript types for a notification, its severity, and the collection payload.
// where : Imported by the notification service, hook and bell component.
// how   : Inferred from the schema so the validator and the type cannot drift apart.

import type { z } from "zod";

import type {
  notificationCollectionSchema,
  notificationSchema,
  notificationSeveritySchema,
} from "../schemas/notification.schema";

export type NotificationSeverity = z.infer<typeof notificationSeveritySchema>;
export type AerisNotification = z.infer<typeof notificationSchema>;
export type NotificationCollection = z.infer<typeof notificationCollectionSchema>;

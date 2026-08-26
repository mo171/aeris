// features/notifications/services/notification.service.ts — fetches background analysis alerts.
//
// what  : Retrieves the operator's current notification list and unread count.
// where : Called by use-notifications.ts only.
// how   : Polling interval and caching live in the hook. In Phase 2 this feed becomes a WebSocket push
//         with incremental cache mutation; keeping the fetch isolated here means that change touches this
//         file and the hook, and no component.

import { apiClient } from "@/lib/axios/axios-client";
import { parseApiResponse } from "@/lib/axios/parse-api-response";
import { REST_API } from "@/lib/constants/rest.api";

import { notificationCollectionSchema } from "../schemas/notification.schema";
import type { NotificationCollection } from "../types/notification.types";

export async function fetchNotifications(signal?: AbortSignal): Promise<NotificationCollection> {
  const response = await apiClient.get(REST_API.notifications.list, { signal });

  return parseApiResponse(notificationCollectionSchema, response.data, "the notification feed");
}

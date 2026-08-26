// features/notifications/hooks/use-notifications.ts — background alert feed for the header bell.
//
// what  : Fetches notifications and derives the unread count relative to the operator's acknowledgement.
// where : Consumed by NotificationBell.
// how   : Polls on a slow interval in Phase 1. In Phase 2 this becomes a WebSocket subscription with
//         incremental cache mutation — the swap touches this hook and the service, and no component,
//         because the component only ever sees the derived list and count.
//
//         The unread count is computed against a locally stored acknowledgement time rather than a
//         server-side read flag, so dismissing the popover feels instant and does not need a round trip.

"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { QUERY_KEYS } from "@/lib/constants/query-keys";
import { useNotificationStore } from "@/store/notification-store";

import { fetchNotifications } from "../services/notification.service";
import type { AerisNotification } from "../types/notification.types";

const NOTIFICATION_POLL_INTERVAL_MS = 60_000;

interface NotificationsResult {
  notifications: AerisNotification[];
  unreadCount: number;
  hasCriticalUnread: boolean;
  isLoading: boolean;
}

export function useNotifications(): NotificationsResult {
  const lastAcknowledgedAt = useNotificationStore((state) => state.lastAcknowledgedAt);

  const query = useQuery({
    queryKey: QUERY_KEYS.notifications.list(),
    queryFn: ({ signal }) => fetchNotifications(signal),
    refetchInterval: NOTIFICATION_POLL_INTERVAL_MS,
  });

  const notifications = useMemo(() => query.data?.notifications ?? [], [query.data]);

  const { unreadCount, hasCriticalUnread } = useMemo(() => {
    if (!lastAcknowledgedAt) {
      return {
        unreadCount: query.data?.unreadCount ?? 0,
        hasCriticalUnread: notifications.some((item) => item.severity === "critical"),
      };
    }

    const acknowledgedAtMs = Date.parse(lastAcknowledgedAt);
    const unread = notifications.filter(
      (item) => Date.parse(item.createdAt) > acknowledgedAtMs,
    );

    return {
      unreadCount: unread.length,
      hasCriticalUnread: unread.some((item) => item.severity === "critical"),
    };
  }, [lastAcknowledgedAt, notifications, query.data]);

  return {
    notifications,
    unreadCount,
    hasCriticalUnread,
    isLoading: query.isLoading,
  };
}

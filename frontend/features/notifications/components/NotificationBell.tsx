// features/notifications/components/NotificationBell.tsx — the header alert control.
//
// what  : A bell with an unread badge that opens a popover listing recent background analysis alerts.
// where : Passed into AppShell as a header action by each surface that wants it.
// how   : It lives in the notifications feature rather than in the shared app shell because it fetches
//         data, and shared UI is not permitted to. The shell accepts it through a slot, which keeps the
//         dependency pointing the correct way: feature depends on shared UI, never the reverse.
//
//         The badge pulses only when something critical is unread. A control that always pulses stops
//         meaning anything within a day.

"use client";

import { Bell, Inbox } from "lucide-react";

import { EmptyState } from "@/components/sharedUI/functionalComponent/feedback/EmptyState";
import { GlowDot, type GlowDotTone } from "@/components/sharedUI/dumbComponent/GlowDot";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SHELL_COPY } from "@/lib/constants/app";
import { formatRelativeTime } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import { useNotificationStore } from "@/store/notification-store";

import { useNotifications } from "../hooks/use-notifications";
import type { NotificationSeverity } from "../types/notification.types";

const SEVERITY_TONE: Record<NotificationSeverity, GlowDotTone> = {
  info: "blue",
  success: "green",
  warning: "amber",
  critical: "red",
};

export function NotificationBell() {
  const { notifications, unreadCount, hasCriticalUnread, isLoading } = useNotifications();
  const isPopoverOpen = useNotificationStore((state) => state.isPopoverOpen);
  const setPopoverOpen = useNotificationStore((state) => state.setPopoverOpen);
  const acknowledgeAll = useNotificationStore((state) => state.acknowledgeAll);

  const handleOpenChange = (isOpen: boolean) => {
    setPopoverOpen(isOpen);
    if (isOpen) {
      acknowledgeAll();
    }
  };

  return (
    <Popover open={isPopoverOpen} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label={`${SHELL_COPY.notificationsLabel}${unreadCount > 0 ? `, ${unreadCount} unread` : ""}`}
          className="relative"
        >
          <Bell />
          {unreadCount > 0 ? (
            <span
              className={cn(
                "absolute -top-0.5 -right-0.5 flex min-w-3.5 items-center justify-center rounded-full px-1 font-mono text-[9px] leading-3.5 text-aeris-black",
                hasCriticalUnread ? "bg-aeris-red text-white" : "bg-aeris-teal",
                hasCriticalUnread && "animate-pulse-glow",
              )}
            >
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          ) : null}
        </Button>
      </PopoverTrigger>

      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex h-8 items-center justify-between border-b border-border px-3">
          <span className="aeris-technical">{SHELL_COPY.notificationsLabel}</span>
          <span className="font-mono text-[10px] text-muted-foreground">
            {notifications.length}
          </span>
        </div>

        <ScrollArea className="max-h-80">
          {!isLoading && notifications.length === 0 ? (
            <EmptyState
              icon={Inbox}
              title="No alerts"
              description="Completed background analyses and monitoring alerts will appear here."
            />
          ) : (
            <ul className="divide-y divide-border-soft">
              {notifications.map((notification) => (
                <li key={notification.id} className="flex gap-2.5 px-3 py-2.5">
                  <GlowDot
                    tone={SEVERITY_TONE[notification.severity]}
                    isPulsing={notification.severity === "critical"}
                    className="mt-1.5"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[11px] font-medium text-foreground">
                      {notification.title}
                    </p>
                    <p className="mt-0.5 text-[10px] leading-relaxed text-muted-foreground">
                      {notification.body}
                    </p>
                    <p className="mt-1 font-mono text-[9px] tracking-wide text-muted-foreground/70 uppercase">
                      {formatRelativeTime(notification.createdAt)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}

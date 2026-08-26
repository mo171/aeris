// store/notification-store.ts — read state for the header alert bell. Holds no server data.
//
// what  : Tracks whether the notification popover is open and when the operator last acknowledged alerts.
// where : Used by the header's NotificationBell.
// how   : The notification list itself is server state and lives in TanStack Query; only the "have I seen
//         these yet" fact is client state, which is why it is the only thing stored here. Duplicating the
//         list into Zustand would violate the server-state/UI-state separation the architecture requires.

import { create } from "zustand";

interface NotificationState {
  isPopoverOpen: boolean;
  lastAcknowledgedAt: string | null;
  setPopoverOpen: (isOpen: boolean) => void;
  acknowledgeAll: () => void;
}

export const useNotificationStore = create<NotificationState>((set) => ({
  isPopoverOpen: false,
  lastAcknowledgedAt: null,
  setPopoverOpen: (isOpen) => set({ isPopoverOpen: isOpen }),
  acknowledgeAll: () => set({ lastAcknowledgedAt: new Date().toISOString() }),
}));

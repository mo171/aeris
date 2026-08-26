// store/ui-store.ts — global shell state: rail, panels, palette, boot. Shared by every AERIS page.
//
// what  : Zustand store holding the layout state of the application shell plus operator preferences.
// where : Read by AppShell, NavigationRail, PanelContainer, CommandPalette and the interface commands.
//         It is global rather than feature-scoped because all seven surfaces inherit the same shell.
// how   : Preferences persist to localStorage, but hydration is deliberately deferred (skipHydration).
//         Rehydrating during render would make the server HTML and the first client render disagree,
//         which shows up as a visible layout snap — AppShell rehydrates in an effect instead.
//         Consumers must select narrow slices (useUiStore((s) => s.isDataPanelOpen)); selecting the whole
//         store re-renders the entire shell on any change.

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { STORAGE_KEYS } from "@/lib/constants/storage-keys";

/** Panel width bounds, in pixels. Kept here because both the store and the drag handle need them. */
export const PANEL_WIDTH_LIMITS = {
  minimum: 260,
  maximum: 520,
  defaultDataPanel: 320,
  defaultAssistantPanel: 384,
} as const;

interface UiState {
  isNavigationRailExpanded: boolean;
  isDataPanelOpen: boolean;
  isAssistantPanelOpen: boolean;
  isCommandPaletteOpen: boolean;
  dataPanelWidth: number;
  assistantPanelWidth: number;
  /** Flips once the entrance choreography has played, so it never replays on client-side navigation. */
  hasPlayedBootSequence: boolean;

  toggleNavigationRail: () => void;
  toggleDataPanel: (isOpen?: boolean) => void;
  toggleAssistantPanel: (isOpen?: boolean) => void;
  setCommandPaletteOpen: (isOpen: boolean) => void;
  setDataPanelWidth: (width: number) => void;
  setAssistantPanelWidth: (width: number) => void;
  markBootSequencePlayed: () => void;
}

function clampPanelWidth(width: number): number {
  return Math.max(PANEL_WIDTH_LIMITS.minimum, Math.min(PANEL_WIDTH_LIMITS.maximum, width));
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      isNavigationRailExpanded: false,
      isDataPanelOpen: true,
      isAssistantPanelOpen: true,
      isCommandPaletteOpen: false,
      dataPanelWidth: PANEL_WIDTH_LIMITS.defaultDataPanel,
      assistantPanelWidth: PANEL_WIDTH_LIMITS.defaultAssistantPanel,
      hasPlayedBootSequence: false,

      toggleNavigationRail: () =>
        set((state) => ({ isNavigationRailExpanded: !state.isNavigationRailExpanded })),
      toggleDataPanel: (isOpen) =>
        set((state) => ({ isDataPanelOpen: isOpen ?? !state.isDataPanelOpen })),
      toggleAssistantPanel: (isOpen) =>
        set((state) => ({ isAssistantPanelOpen: isOpen ?? !state.isAssistantPanelOpen })),
      setCommandPaletteOpen: (isOpen) => set({ isCommandPaletteOpen: isOpen }),
      setDataPanelWidth: (width) => set({ dataPanelWidth: clampPanelWidth(width) }),
      setAssistantPanelWidth: (width) => set({ assistantPanelWidth: clampPanelWidth(width) }),
      markBootSequencePlayed: () => set({ hasPlayedBootSequence: true }),
    }),
    {
      name: STORAGE_KEYS.uiPreferences,
      storage: createJSONStorage(() => localStorage),
      skipHydration: true,
      partialize: (state) => ({
        isNavigationRailExpanded: state.isNavigationRailExpanded,
        isDataPanelOpen: state.isDataPanelOpen,
        isAssistantPanelOpen: state.isAssistantPanelOpen,
        dataPanelWidth: state.dataPanelWidth,
        assistantPanelWidth: state.assistantPanelWidth,
      }),
    },
  ),
);

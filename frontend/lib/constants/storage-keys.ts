// lib/constants/storage-keys.ts — namespaced localStorage keys. Prevents key collisions and typos.
//
// what  : String keys for anything AERIS persists in the browser.
// where : Used by Zustand persist middleware in store/ and by panel layout persistence.
// how   : Every key is prefixed so AERIS state is trivially identifiable and clearable in DevTools.

const STORAGE_NAMESPACE = "aeris";

export const STORAGE_KEYS = {
  uiPreferences: `${STORAGE_NAMESPACE}:ui-preferences`,
  panelLayout: `${STORAGE_NAMESPACE}:panel-layout`,
  assistantSession: `${STORAGE_NAMESPACE}:assistant-session`,
} as const;

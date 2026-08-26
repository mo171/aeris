/**
 * @file lib/constants/theme.ts
 * @description Centralized UI theme constants matching the design report
 */

export const AERIS_THEME = {
  colors: {
    background: {
      black: "#0A0D14",
      obsidian: "#141824",
    },
    primary: {
      teal: "#00E5FF",
      blue: "#3B82F6",
    },
    status: {
      warning: "#F59E0B",
      critical: "#EF4444",
      success: "#10B981",
    },
    text: {
      primary: "#F3F4F6",
      secondary: "#9CA3AF",
    },
  },
} as const;

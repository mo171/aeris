// components/sharedUI/functionalComponent/appShell/AppShell.tsx — the frame every AERIS surface renders inside.
//
// what  : Composes the navigation rail, the global header, the command palette and the keyboard-shortcut
//         layer around a full-height content area, and rehydrates persisted layout preferences.
// where : Wrapped around the content of each of the seven surfaces. Mission Command is the first consumer.
// how   : Preference rehydration happens here, in an effect, rather than during render. Zustand's persist
//         middleware is configured with skipHydration precisely so the server HTML and the first client
//         render agree; reading localStorage during render would make them disagree and produce a visible
//         snap as panels jump to their stored widths. One frame of default layout is the correct trade.
//
//         The shell owns no page content. Surfaces pass their own zones as children, which is why the same
//         shell can host a globe-centred command centre and a document-centred evidence explorer.

"use client";

import { useEffect, type ReactNode } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";
import { useCommandShortcuts } from "@/hooks/use-command-shortcuts";
import { useShellCommands } from "@/hooks/use-shell-commands";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/store/ui-store";

import { AppHeader } from "./AppHeader";
import { CommandPalette } from "./CommandPalette";
import { NavigationRail } from "./NavigationRail";

interface AppShellProps {
  children: ReactNode;
  /** Feature-owned header controls, e.g. the notification bell. */
  headerActionsSlot?: ReactNode;
  className?: string;
}

export function AppShell({ children, headerActionsSlot, className }: AppShellProps) {
  useShellCommands();
  useCommandShortcuts();

  useEffect(() => {
    void useUiStore.persist.rehydrate();
  }, []);

  return (
    <TooltipProvider delayDuration={220}>
      <div className={cn("flex h-dvh w-full overflow-hidden bg-background", className)}>
        <NavigationRail />

        <div className="flex min-w-0 flex-1 flex-col">
          <AppHeader actionsSlot={headerActionsSlot} />
          <main className="relative min-h-0 flex-1 overflow-hidden">{children}</main>
        </div>
      </div>

      <CommandPalette />
    </TooltipProvider>
  );
}

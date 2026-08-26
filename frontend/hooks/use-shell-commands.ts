// hooks/use-shell-commands.ts — registers the shell's own commands: navigation and panel control.
//
// what  : Defines and registers the `nav.*` and `interface.*` commands with the command bus.
// where : Called once by AppShell, so every surface gets the same shell commands and shortcuts.
// how   : Navigation is registered twice on purpose. One palette-visible command per available surface
//         gives the operator a direct "go to X" entry, while a single parameterised `nav.goto` — hidden
//         from the palette, because a palette cannot collect arguments — gives the agent one command that
//         can reach any surface. Both paths run the same navigate function, so they can never diverge.

"use client";

import { useRouter } from "next/navigation";
import { useMemo } from "react";
import { z } from "zod";

import { defineCommand, useRegisterCommands } from "@/lib/command-bus";
import { COMMAND_IDS } from "@/lib/constants/commands";
import { NAVIGATION_ITEMS } from "@/lib/constants/navigation";
import { useUiStore } from "@/store/ui-store";

export function useShellCommands(): void {
  const router = useRouter();
  const toggleNavigationRail = useUiStore((state) => state.toggleNavigationRail);
  const toggleDataPanel = useUiStore((state) => state.toggleDataPanel);
  const toggleAssistantPanel = useUiStore((state) => state.toggleAssistantPanel);
  const setCommandPaletteOpen = useUiStore((state) => state.setCommandPaletteOpen);

  const availableNavigationItems = useMemo(
    () => NAVIGATION_ITEMS.filter((item) => item.isAvailable),
    [],
  );

  const commands = useMemo(() => {
    const navigateToSurface = (surfaceId: string) => {
      const target = NAVIGATION_ITEMS.find((item) => item.id === surfaceId);
      if (target?.isAvailable) {
        router.push(target.href);
      }
    };

    const perSurfaceCommands = availableNavigationItems.map((item) =>
      defineCommand({
        id: `${COMMAND_IDS.navigation.goto}.${item.id}`,
        title: `Go to ${item.label}`,
        description: item.description,
        group: "navigation",
        keywords: ["open", "navigate", item.label],
        icon: item.icon,
        paramsSchema: z.void(),
        handler: () => navigateToSurface(item.id),
      }),
    );

    return [
      ...perSurfaceCommands,
      defineCommand({
        id: COMMAND_IDS.navigation.goto,
        title: "Navigate to a surface",
        description:
          "Open one of the AERIS surfaces by its identifier. Valid identifiers are the ids listed in the navigation registry.",
        group: "navigation",
        isPaletteVisible: false,
        paramsSchema: z.object({
          surfaceId: z.enum(
            NAVIGATION_ITEMS.map((item) => item.id) as [string, ...string[]],
          ),
        }),
        handler: ({ surfaceId }) => navigateToSurface(surfaceId),
      }),
      defineCommand({
        id: COMMAND_IDS.interface.openPalette,
        title: "Open command palette",
        description: "Show the searchable list of every command the interface can run.",
        group: "interface",
        keywords: ["search", "command", "palette"],
        shortcut: ["ctrl", "k"],
        paramsSchema: z.void(),
        handler: () => setCommandPaletteOpen(true),
      }),
      defineCommand({
        id: COMMAND_IDS.interface.toggleDataPanel,
        title: "Toggle data panel",
        description: "Show or hide the left panel containing imagery intake, catalogue and missions.",
        group: "interface",
        keywords: ["left", "panel", "imagery", "hide"],
        shortcut: ["ctrl", "b"],
        paramsSchema: z.void(),
        handler: () => toggleDataPanel(),
      }),
      defineCommand({
        id: COMMAND_IDS.interface.toggleAssistantPanel,
        title: "Toggle assistant panel",
        description: "Show or hide the right panel containing the AERIS assistant and execution traces.",
        group: "interface",
        keywords: ["right", "panel", "assistant", "chat", "hide"],
        shortcut: ["ctrl", "j"],
        paramsSchema: z.void(),
        handler: () => toggleAssistantPanel(),
      }),
      defineCommand({
        id: COMMAND_IDS.interface.toggleNavigationRail,
        title: "Toggle navigation labels",
        description: "Expand or collapse the navigation rail on the far left.",
        group: "interface",
        keywords: ["sidebar", "rail", "navigation", "collapse"],
        paramsSchema: z.void(),
        handler: () => toggleNavigationRail(),
      }),
    ];
  }, [
    availableNavigationItems,
    router,
    setCommandPaletteOpen,
    toggleAssistantPanel,
    toggleDataPanel,
    toggleNavigationRail,
  ]);

  useRegisterCommands(commands);
}

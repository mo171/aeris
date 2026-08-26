// lib/command-bus/use-register-commands.ts — React binding that keeps the registry in sync with mounted UI.
//
// what  : Registers a feature's commands while its screen is mounted and removes them on unmount.
// where : Called once per feature from features/&ast;/hooks/use-&ast;-commands.ts.
// how   : Handlers are closures that capture fresh render state, so re-registering on every render would
//         thrash the store. Instead the effect registers stable proxy handlers that read the newest
//         definitions from a ref. The effect therefore only re-runs when the SET of command ids changes,
//         while the behaviour always reflects the current render.

"use client";

import { useEffect, useMemo, useRef } from "react";

import { registerCommands } from "./registry";
import type { RegisteredCommand } from "./types";

export function useRegisterCommands(commands: readonly RegisteredCommand[]): void {
  const latestCommands = useRef(commands);

  // Declared before the registration effect so the mirror is always current by the time a proxy handler
  // can be invoked. Runs after every render on purpose: handlers close over fresh state each time.
  useEffect(() => {
    latestCommands.current = commands;
  });

  const commandIdSignature = useMemo(
    () => commands.map((command) => command.id).join("|"),
    [commands],
  );

  useEffect(() => {
    const proxies: RegisteredCommand[] = latestCommands.current.map((command) => ({
      ...command,
      handler: (parameters: unknown) => {
        const current = latestCommands.current.find((entry) => entry.id === command.id);
        return current?.handler(parameters);
      },
      isEnabled: () => {
        const current = latestCommands.current.find((entry) => entry.id === command.id);
        return current?.isEnabled ? current.isEnabled() : true;
      },
    }));

    return registerCommands(proxies);
  }, [commandIdSignature]);
}

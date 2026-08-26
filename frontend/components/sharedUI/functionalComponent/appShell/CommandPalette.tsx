// components/sharedUI/functionalComponent/appShell/CommandPalette.tsx — the operator's view of the command bus.
//
// what  : A searchable dialog listing every palette-visible registered command, grouped by domain, that
//         dispatches the selected command through the same bus the agent will use.
// where : Mounted once by AppShell.
// how   : This component renders the registry; it contains no command definitions of its own. That is the
//         point of the architecture — a feature adds a capability by registering a command, and it appears
//         here, gains its keyboard shortcut, and becomes agent-invocable, with no change to this file.
//
//         Only commands that take no parameters are offered here, because a palette has nowhere to collect
//         arguments. Parameterised commands (globe.flyTo, imagery.select) stay agent- and code-invocable;
//         they are surfaced to the operator through the UI control that already has the argument in hand.

"use client";

import { useMemo } from "react";
import { toast } from "sonner";

import { KeyboardHint } from "@/components/sharedUI/dumbComponent/KeyboardHint";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { dispatchCommand, useRegisteredCommands } from "@/lib/command-bus";
import { COMMAND_GROUP_LABEL, type CommandGroup as CommandGroupId } from "@/lib/constants/commands";
import { useUiStore } from "@/store/ui-store";

export function CommandPalette() {
  const isOpen = useUiStore((state) => state.isCommandPaletteOpen);
  const setCommandPaletteOpen = useUiStore((state) => state.setCommandPaletteOpen);
  const commands = useRegisteredCommands();

  const groupedCommands = useMemo(() => {
    const groups = new Map<CommandGroupId, typeof commands>();

    for (const command of commands) {
      if (command.isPaletteVisible === false) {
        continue;
      }
      const existing = groups.get(command.group) ?? [];
      existing.push(command);
      groups.set(command.group, existing);
    }

    return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [commands]);

  const handleSelect = async (commandId: string) => {
    setCommandPaletteOpen(false);
    const result = await dispatchCommand(commandId, undefined);

    if (result.status === "invalid-params") {
      toast.error("That command needs more information", { description: result.message });
    } else if (result.status === "failed") {
      toast.error("The command did not complete");
    } else if (result.status === "disabled") {
      toast.warning("That command is not available right now");
    }
  };

  return (
    <CommandDialog
      open={isOpen}
      onOpenChange={setCommandPaletteOpen}
      title="AERIS command palette"
      description="Search and run any interface or analysis command"
      className="max-w-xl border-border bg-popover"
    >
      <Command>
        <CommandInput placeholder="Run a command…" />
        <CommandList className="max-h-[min(24rem,60vh)]">
          <CommandEmpty>No matching command.</CommandEmpty>

          {groupedCommands.map(([group, groupCommands]) => (
            <CommandGroup key={group} heading={COMMAND_GROUP_LABEL[group]}>
              {groupCommands.map((command) => {
                const isEnabled = command.isEnabled ? command.isEnabled() : true;
                const Icon = command.icon;

                return (
                  <CommandItem
                    key={command.id}
                    value={`${command.title} ${command.description} ${(command.keywords ?? []).join(" ")}`}
                    disabled={!isEnabled}
                    onSelect={() => void handleSelect(command.id)}
                    className="gap-2"
                  >
                    {Icon ? (
                      <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                    ) : null}
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate text-xs">{command.title}</span>
                      <span className="truncate text-[10px] text-muted-foreground">
                        {command.description}
                      </span>
                    </span>
                    {command.shortcut ? (
                      <KeyboardHint keys={command.shortcut} className="ml-auto shrink-0" />
                    ) : null}
                  </CommandItem>
                );
              })}
            </CommandGroup>
          ))}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}

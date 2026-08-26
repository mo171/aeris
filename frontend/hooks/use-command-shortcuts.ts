// hooks/use-command-shortcuts.ts — turns every registered command's `shortcut` into a live key binding.
//
// what  : A single global keydown listener that matches key combinations against the command registry
//         and dispatches the corresponding command.
// where : Mounted once by the application shell.
// how   : One listener for all shortcuts rather than one per component: shortcuts are declared as data on
//         the command itself, so adding a binding never means touching this file. Keystrokes are ignored
//         while focus is in a text field, except for combinations that include a modifier — otherwise
//         typing "g" in the assistant composer would fly the camera somewhere.

"use client";

import { useEffect } from "react";

import { dispatchCommand, useRegisteredCommands } from "@/lib/command-bus";

const EDITABLE_ELEMENT_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

function isTypingContext(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return EDITABLE_ELEMENT_TAGS.has(target.tagName) || target.isContentEditable;
}

function buildEventSignature(event: KeyboardEvent): string {
  const parts: string[] = [];
  if (event.ctrlKey || event.metaKey) parts.push("ctrl");
  if (event.altKey) parts.push("alt");
  if (event.shiftKey) parts.push("shift");
  parts.push(event.key.toLowerCase());
  return parts.join("+");
}

function normaliseShortcut(shortcut: readonly string[]): string {
  return shortcut.map((key) => key.toLowerCase()).join("+");
}

export function useCommandShortcuts(): void {
  const commands = useRegisteredCommands();

  useEffect(() => {
    const bindings = new Map<string, string>();
    for (const command of commands) {
      if (command.shortcut && command.shortcut.length > 0) {
        bindings.set(normaliseShortcut(command.shortcut), command.id);
      }
    }

    if (bindings.size === 0) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      const signature = buildEventSignature(event);
      const commandId = bindings.get(signature);
      if (!commandId) {
        return;
      }

      const usesModifier = event.ctrlKey || event.metaKey || event.altKey;
      if (!usesModifier && isTypingContext(event.target)) {
        return;
      }

      event.preventDefault();
      void dispatchCommand(commandId, undefined);
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [commands]);
}

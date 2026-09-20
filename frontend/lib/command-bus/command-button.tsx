// lib/command-bus/command-button.tsx — the permanent fix for click/agent drift.
//
// what  : A button that IS a command dispatch, not a button that happens to do
//         the same thing as one. Clicks and agent orders execute the identical
//         code path (registry → Zod validation → handler), so a control the
//         operator can press is a control AERIS can press, by construction.
// where : Use for any control that changes workspace state. Purely local chrome
//         (text drafts, expand/collapse of a legend) stays a plain <button>.
// how   : Dispatches on click after running any extra onClick the caller passed
//         (cancel it with preventDefault to suppress the dispatch). Reflects the
//         command's isEnabled() as the disabled attribute, mirroring the palette.

"use client";

import { forwardRef, type ButtonHTMLAttributes, type MouseEvent } from "react";

import { dispatchCommand, useRegisteredCommands } from "@/lib/command-bus";
import type { CommandDispatchResult } from "./types";

export interface CommandButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  commandId: string;
  params?: unknown;
  onResult?: (result: CommandDispatchResult) => void;
}

export const CommandButton = forwardRef<HTMLButtonElement, CommandButtonProps>(
  function CommandButton({ commandId, params, onResult, onClick, disabled, ...rest }, ref) {
    const commands = useRegisteredCommands();
    const registered = commands.find((command) => command.id === commandId);
    const enabled = !registered?.isEnabled || registered.isEnabled();

    const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
      onClick?.(event);
      if (event.defaultPrevented) return;
      console.log(`[AERIS UI] click → ${commandId}`, params ?? {});
      void dispatchCommand(commandId, params).then((result) => {
        if (result.status !== "completed") {
          console.warn(`[AERIS UI] click ${commandId} -> ${result.status}`, result);
        }
        onResult?.(result);
      });
    };

    return (
      <button
        ref={ref}
        type="button"
        disabled={disabled || !enabled}
        onClick={handleClick}
        {...rest}
      />
    );
  },
);

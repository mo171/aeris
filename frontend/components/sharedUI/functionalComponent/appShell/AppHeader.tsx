// components/sharedUI/functionalComponent/appShell/AppHeader.tsx — the global top bar.
//
// what  : Brand mark, the universal command bar trigger, a system status readout, and slots for
//         feature-owned actions, e.g. a mission-status control or a user menu.
// where : Rendered by AppShell on every surface.
// how   : The command bar is a button, not an input. Typing happens inside the command palette dialog,
//         which owns focus, keyboard navigation and results — duplicating that in an inline field would
//         mean two search implementations that drift apart. Feature-specific controls arrive through the
//         `actionsSlot` prop so this shared component never imports feature code, which is the boundary
//         rule that keeps components/sharedUI reusable.

"use client";

import { Search } from "lucide-react";
import type { ReactNode } from "react";

import { BrandLogo } from "@/components/sharedUI/dumbComponent/BrandLogo";
import { GlowDot } from "@/components/sharedUI/dumbComponent/GlowDot";
import { KeyboardHint } from "@/components/sharedUI/dumbComponent/KeyboardHint";
import { SHELL_COPY } from "@/lib/constants/app";
import { COMMAND_IDS } from "@/lib/constants/commands";
import { dispatchCommand } from "@/lib/command-bus";
import { cn } from "@/lib/utils";

interface AppHeaderProps {
  /** Feature-owned controls rendered on the right. Surfaces supply their own; the shell stays generic. */
  actionsSlot?: ReactNode;
  className?: string;
}

export function AppHeader({ actionsSlot, className }: AppHeaderProps) {
  return (
    <header
      className={cn(
        "z-30 flex h-12 shrink-0 items-center gap-3 border-b border-border bg-aeris-black/85 px-3 backdrop-blur-md",
        className,
      )}
    >
      <BrandLogo />

      <div className="mx-auto flex w-full max-w-xl justify-center px-4">
        <button
          type="button"
          onClick={() => void dispatchCommand(COMMAND_IDS.interface.openPalette, undefined)}
          className="group/commandbar flex h-8 w-full items-center gap-2 rounded-md border border-border bg-surface-2/60 px-2.5 text-left transition-colors duration-fast hover:border-aeris-teal/40 hover:bg-surface-3/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <Search className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className="truncate text-xs text-muted-foreground">
            {SHELL_COPY.commandBarPlaceholder}
          </span>
          <KeyboardHint keys={["Ctrl", "K"]} className="ml-auto shrink-0" />
        </button>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <span className="hidden items-center gap-1.5 rounded-md border border-border bg-muted/30 px-2 py-1 lg:flex">
          <GlowDot tone="green" isPulsing />
          <span className="font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
            {SHELL_COPY.systemStatusNominal}
          </span>
        </span>
        {actionsSlot}
      </div>
    </header>
  );
}

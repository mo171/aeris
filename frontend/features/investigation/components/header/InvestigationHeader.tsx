// features/investigation/components/header/InvestigationHeader.tsx — the investigation identity strip.
//
// what  : Names the investigation and its area of interest, lists the scenes it is built on, exposes the
//         trace id, and carries the present-mode and report actions.
// where : The top of InvestigationScreen, below the application header.
// how   : The trace id is small, permanent and copyable, and it is deliberately the most technical thing
//         on the strip. It is the product claim rendered as a single element: everything on this screen is
//         re-executable, and any number in the eventual report walks back to pixels through this id. A
//         system that cannot show its provenance identity is asking to be trusted rather than checked.
//
//         The strip is a page element rather than content injected into the application header. The shell
//         header belongs to every surface; investigation identity belongs to this one, and pushing it up
//         there would couple the shell to a feature it should know nothing about.

"use client";

import { ArrowLeft, Check, Copy, FileText, Presentation } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { dispatchCommand } from "@/lib/command-bus";
import { COMMAND_IDS } from "@/lib/constants/commands";
import { ROUTES } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";

import { useInvestigationStore } from "../../store/investigation-store";
import type { Investigation, InvestigationSceneSlot } from "../../types/investigation.types";
import { SceneSlotChips } from "./SceneSlotChips";

const COPY_FEEDBACK_MS = 1_400;

interface InvestigationHeaderProps {
  investigation: Investigation;
  onFocusScene: (slot: InvestigationSceneSlot) => void;
}

export function InvestigationHeader({
  investigation,
  onFocusScene,
}: InvestigationHeaderProps) {
  const isPresentMode = useInvestigationStore((state) => state.isPresentMode);
  const [hasCopiedTraceId, setHasCopiedTraceId] = useState(false);

  const copyTraceId = async () => {
    try {
      await navigator.clipboard.writeText(investigation.traceId);
      setHasCopiedTraceId(true);
      window.setTimeout(() => setHasCopiedTraceId(false), COPY_FEEDBACK_MS);
    } catch {
      // Clipboard access can be denied outright. The id is visible either way, so failing silently is
      // better than an error toast about a convenience.
    }
  };

  return (
    <header className="pointer-events-auto flex items-start gap-3 rounded-md border border-border bg-surface-2/80 px-3 py-2 backdrop-blur-md">
      <Button type="button" size="icon-sm" variant="ghost" asChild aria-label="Back to Mission Command">
        <Link href={ROUTES.MISSION_COMMAND}>
          <ArrowLeft />
        </Link>
      </Button>

      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-baseline gap-2">
          <h1 className="truncate text-sm font-medium text-foreground">{investigation.name}</h1>
          <span className="truncate font-mono text-[10px] text-muted-foreground">
            {investigation.areaOfInterestName}
          </span>
        </div>

        <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          <SceneSlotChips sceneSlots={investigation.sceneSlots} onFocusScene={onFocusScene} />

          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => void copyTraceId()}
                className="flex items-center gap-1 rounded-sm font-mono text-[10px] text-muted-foreground/70 transition-colors duration-fast hover:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                trace {investigation.traceId}
                {hasCopiedTraceId ? (
                  <Check className="size-2.5 text-aeris-teal" aria-hidden="true" />
                ) : (
                  <Copy className="size-2.5" aria-hidden="true" />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              Copy the provenance id. Every claim here is re-executable from it.
            </TooltipContent>
          </Tooltip>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              aria-label="Present mode"
              aria-pressed={isPresentMode}
              onClick={() => void dispatchCommand(COMMAND_IDS.investigation.togglePresentMode)}
              className={cn(isPresentMode && "text-aeris-teal")}
            >
              <Presentation />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">Hide the panels and orbit the scene</TooltipContent>
        </Tooltip>

        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void dispatchCommand(COMMAND_IDS.investigation.openReport)}
        >
          <FileText />
          Report
        </Button>
      </div>
    </header>
  );
}

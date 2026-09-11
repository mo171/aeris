// features/investigation/components/viewer/DrawToolbar.tsx — the geometry and measurement palette.
//
// what  : Four ways to define an area of interest — rectangle, polygon, freehand, circle — and three
//         measurement tools: distance, area, bearing.
// where : Rendered into the centre column of InvestigationScreen, above the tool cluster.
// how   : Four shapes rather than one because they answer different questions. A rectangle is fastest for
//         "this block". A polygon traces an administrative or physical boundary. Freehand follows a
//         coastline without fighting vertex-by-vertex clicking. A circle asks "within N metres of here",
//         which is how buffer questions are actually posed. Offering only a rectangle forces every
//         question into the wrong shape, and the backend then crops to that wrong shape.
//
//         Measurement is separated from drawing by a divider because the two commit different things: a
//         region scopes the next question, a measurement is an answer in itself and leaves a label on the
//         scene.
//
//         The armed tool shows its own instructions. A polygon that needs a double-click to close is not
//         discoverable, and an analyst who does not know how to finish a shape will conclude the tool is
//         broken — which is exactly what happened before this existed.

"use client";

import { Circle, Hexagon, MoveUpRight, PenLine, Ruler, Shapes, Square } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { DRAW_TOOL_COPY } from "@/lib/constants/draw";
import { cn } from "@/lib/utils";

import type { StageDrawTool } from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";

const SHAPE_TOOLS: readonly { id: StageDrawTool; icon: typeof Square }[] = [
  { id: "rectangle", icon: Square },
  { id: "polygon", icon: Hexagon },
  { id: "freehand", icon: PenLine },
  { id: "circle", icon: Circle },
];

const MEASURE_TOOLS: readonly { id: StageDrawTool; icon: typeof Ruler }[] = [
  { id: "distance", icon: Ruler },
  { id: "area", icon: Shapes },
  { id: "bearing", icon: MoveUpRight },
];

interface DrawToolbarProps {
  activeTool: StageDrawTool | null;
  onSelectTool: (tool: StageDrawTool) => void;
}

export function DrawToolbar({ activeTool, onSelectTool }: DrawToolbarProps) {
  return (
    <div className="pointer-events-auto flex flex-col items-center gap-1">
      <div className="flex items-center gap-1 rounded-md border border-border bg-surface-2/80 p-1 backdrop-blur-md">
        {SHAPE_TOOLS.map(({ id, icon: Icon }) => (
          <ToolButton
            key={id}
            id={id}
            isActive={activeTool === id}
            onSelect={onSelectTool}
            icon={<Icon />}
          />
        ))}

        <span className="mx-0.5 h-4 w-px bg-border" aria-hidden="true" />

        {MEASURE_TOOLS.map(({ id, icon: Icon }) => (
          <ToolButton
            key={id}
            id={id}
            isActive={activeTool === id}
            onSelect={onSelectTool}
            icon={<Icon />}
            tone="amber"
          />
        ))}
      </div>

      {activeTool ? (
        <p className="rounded-sm bg-surface-2/90 px-2 py-0.5 font-mono text-[10px] whitespace-nowrap text-muted-foreground backdrop-blur-md">
          {DRAW_TOOL_COPY[activeTool].hint} · Esc cancels
        </p>
      ) : null}
    </div>
  );
}

interface ToolButtonProps {
  id: StageDrawTool;
  isActive: boolean;
  onSelect: (tool: StageDrawTool) => void;
  icon: ReactNode;
  tone?: "teal" | "amber";
}

function ToolButton({ id, isActive, onSelect, icon, tone = "teal" }: ToolButtonProps) {
  const copy = DRAW_TOOL_COPY[id];

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          aria-label={copy.label}
          aria-pressed={isActive}
          onClick={() => onSelect(id)}
          className={cn(
            isActive && (tone === "amber" 
              ? "bg-aeris-amber/15 text-aeris-amber hover:bg-aeris-amber/25 hover:text-aeris-amber" 
              : "bg-aeris-teal/15 text-aeris-teal hover:bg-aeris-teal/25 hover:text-aeris-teal"),
          )}
        >
          {icon}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="top">
        <span className="font-medium">{copy.label}</span>
        <span className="block text-muted-foreground">{copy.hint}</span>
      </TooltipContent>
    </Tooltip>
  );
}

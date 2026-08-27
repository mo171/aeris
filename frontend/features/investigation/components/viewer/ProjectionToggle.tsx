// features/investigation/components/viewer/ProjectionToggle.tsx — globe, 2.5D or flat map.
//
// what  : Switches the scene between the 3D globe, the Columbus 2.5D view and a flat 2D map.
// where : Rendered into the centre column of InvestigationScreen, beside the tool cluster.
// how   : 2D is not a convenience — it is the projection an analyst digitises in. In perspective every
//         polygon edge is foreshortened by an amount that depends on where it sits on screen, so tracing
//         a boundary accurately becomes guesswork. Flat nadir removes that entirely, which is why the
//         backend gets better geometry out of it.
//
//         Columbus sits between the two: a flat map that still honours height, so extruded change stays
//         readable without perspective distortion.
//
//         It is the same scene, the same layers and the same evidence throughout — only the projection
//         changes. Nothing is reloaded, which is what makes switching cheap enough to do reflexively.

"use client";

import { Box, Globe, Map } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import type { StageProjection } from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";

const PROJECTIONS: readonly {
  id: StageProjection;
  label: string;
  hint: string;
  icon: typeof Globe;
}[] = [
  { id: "3D", label: "3D", hint: "Globe — terrain and perspective", icon: Globe },
  { id: "columbus", label: "2.5D", hint: "Flat map that still honours height", icon: Box },
  { id: "2D", label: "2D", hint: "Flat nadir — the projection to digitise in", icon: Map },
];

interface ProjectionToggleProps {
  projection: StageProjection;
  onChange: (projection: StageProjection) => void;
}

export function ProjectionToggle({ projection, onChange }: ProjectionToggleProps) {
  return (
    <div className="pointer-events-auto flex items-center gap-0.5 rounded-md border border-border bg-surface-2/80 p-1 backdrop-blur-md">
      {PROJECTIONS.map(({ id, label, hint, icon: Icon }) => (
        <Tooltip key={id}>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-pressed={projection === id}
              onClick={() => onChange(id)}
              className={cn(
                "h-6 gap-1 px-1.5 font-mono text-[10px] tracking-wide",
                projection === id ? "bg-aeris-teal/15 text-aeris-teal" : "text-muted-foreground",
              )}
            >
              <Icon className="size-3" />
              {label}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top">{hint}</TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}

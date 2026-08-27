// features/investigation/components/inputsPanel/AcquisitionList.tsx — the acquisition history over this area.
//
// what  : Every dated observation of the area of interest, with its quicklook, cloud cover, and the
//         actions to open it in its own window or bind it into a comparison role.
// where : A section of InputsPanel.
// how   : An investigation is not a pair of images, it is a time series that a pair is currently selected
//         from. Showing the whole stack is what lets an analyst notice that the acquisition they were
//         handed is 40% cloud and the one three weeks later is clean — a judgement no automatic pairing
//         can make for them.
//
//         Unusable acquisitions are shown, not hidden. A gap in coverage is information: an operator who
//         cannot see that the archive has nothing usable for 2021 will read a change over that period as
//         a finding rather than as an artefact of what was available.
//
//         The quicklook is a real picture of the place at that date, so scanning the column is how the
//         operator forms an opinion before loading anything heavy.

"use client";

import { ExternalLink, Radar, Satellite } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatAbsoluteDate } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import type { Acquisition, SceneRole } from "../../types/investigation.types";

interface AcquisitionListProps {
  acquisitions: Acquisition[];
  /** Which scene occupies which role, so the list can show what is currently bound. */
  roleBySceneId: Record<string, SceneRole>;
  openSceneIds: readonly string[];
  onOpenScene: (sceneId: string) => void;
}

const ROLE_LABEL: Record<SceneRole, string> = { t0: "T0", t1: "T1", sar: "SAR", aux: "AUX" };

export function AcquisitionList({
  acquisitions,
  roleBySceneId,
  openSceneIds,
  onOpenScene,
}: AcquisitionListProps) {
  return (
    <ul className="flex flex-col gap-1">
      {acquisitions.map((acquisition) => {
        const SensorIcon = acquisition.modality === "sar" ? Radar : Satellite;
        const role = roleBySceneId[acquisition.sceneId];
        const isOpen = openSceneIds.includes(acquisition.sceneId);

        return (
          <li key={acquisition.id}>
            <div
              className={cn(
                "flex items-center gap-2 rounded-md border px-1.5 py-1.5 transition-colors duration-fast",
                role
                  ? "border-aeris-teal/50 bg-aeris-teal/5"
                  : "border-border-soft bg-surface-2/40",
                !acquisition.isAvailable && "opacity-60",
              )}
            >
              <button
                type="button"
                onClick={() => onOpenScene(acquisition.sceneId)}
                title="Open this scene in its own window"
                className="size-10 shrink-0 overflow-hidden rounded-sm border border-border-soft bg-surface-2 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                {acquisition.quicklookUrl ? (
                  // Plain img rather than next/image: the tile host is not known at build time, and the
                  // thumbnail is already the size it is displayed at.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={acquisition.quicklookUrl}
                    alt=""
                    className="size-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <SensorIcon className="m-auto size-4 text-muted-foreground" aria-hidden="true" />
                )}
              </button>

              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5">
                  <SensorIcon
                    className={cn(
                      "size-3 shrink-0",
                      acquisition.modality === "sar" ? "text-aeris-blue" : "text-aeris-teal",
                    )}
                    aria-hidden="true"
                  />
                  <span className="truncate font-mono text-[11px] text-foreground">
                    {formatAbsoluteDate(acquisition.capturedAt)}
                  </span>
                  {role ? (
                    <span className="shrink-0 rounded-sm bg-aeris-teal/15 px-1 font-mono text-[9px] text-aeris-teal">
                      {ROLE_LABEL[role]}
                    </span>
                  ) : null}
                </span>
                <span className="block truncate font-mono text-[10px] text-muted-foreground">
                  {acquisition.sensorPlatform}
                  {" · "}
                  {acquisition.cloudCoverPercentage === null
                    ? "cloud n/a"
                    : `${Math.round(acquisition.cloudCoverPercentage)}% cloud`}
                  {!acquisition.isAvailable ? " · unusable" : ""}
                </span>
              </span>

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    aria-label={`Open ${formatAbsoluteDate(acquisition.capturedAt)} in a window`}
                    onClick={() => onOpenScene(acquisition.sceneId)}
                    className={cn(isOpen && "text-aeris-teal")}
                  >
                    <ExternalLink />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="left">
                  {isOpen ? "Focus the open window" : "Open in its own window"}
                </TooltipContent>
              </Tooltip>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

// features/investigation/components/viewer/TimelineTrack.tsx — one sensing modality's row on the timeline.
//
// what  : Draws every acquisition of one modality as a mark positioned by its date, styled by whether it
//         is usable, currently selected, or cited by the answer on screen.
// where : Rendered once per lane by TimelineScrubber, inside the shared positioning container.
// how   : Unusable acquisitions are drawn, not filtered out. A hollow mark where a pass exists but is too
//         cloudy to analyse is the difference between "the archive has nothing here" and "the archive has
//         something here you cannot use" — and an operator who cannot tell those apart will read a change
//         across the gap as a finding rather than as an artefact of what was available.
//
//         Marks are absolutely positioned against the same container the handles use, so a mark and a
//         handle at the same date land on the same pixel. Giving each lane its own scale would let them
//         disagree by a few pixels, which on a date axis is a wrong date.

"use client";

import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { TIMELINE_LAYOUT } from "@/lib/constants/timeline";
import { cn } from "@/lib/utils";

import { isSelectable, positionForTime, type TimelineDomain } from "../../lib/timeline-geometry";
import type { Acquisition } from "../../types/investigation.types";

interface TimelineTrackProps {
  label: string;
  /** Hidden when every sensor shares one rule, where a lane name would be a lie. */
  showLabel?: boolean;
  /** Colours radar apart from optical. Needed only on the merged rule, where the lane cannot say it. */
  colorByModality?: boolean;
  acquisitions: Acquisition[];
  domain: TimelineDomain;
  cloudCeilingPercentage: number;
  selectedSceneIds: readonly (string | null)[];
  citedSceneIds: ReadonlySet<string>;
  onSelectAcquisition: (acquisition: Acquisition) => void;
}

export function TimelineTrack({
  label,
  showLabel = true,
  colorByModality = false,
  acquisitions,
  domain,
  cloudCeilingPercentage,
  selectedSceneIds,
  citedSceneIds,
  onSelectAcquisition,
}: TimelineTrackProps) {
  return (
    <div
      className="relative w-full"
      style={{ height: TIMELINE_LAYOUT.laneHeightPx }}
      role="group"
      aria-label={`${label} acquisitions`}
    >
      {showLabel ? (
        <span className="absolute inset-y-0 -left-1 flex items-center">
          <span className="aeris-technical -translate-x-full pr-2 text-[9px] whitespace-nowrap text-muted-foreground/70">
            {label}
          </span>
        </span>
      ) : null}

      {/* The lane rule. Sits behind the marks so a dense run still reads as one continuous archive. */}
      <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border-soft" aria-hidden="true" />

      {acquisitions.map((acquisition) => {
        const usable = isSelectable(acquisition, cloudCeilingPercentage);
        const isSelected = selectedSceneIds.includes(acquisition.sceneId);
        const isCited = citedSceneIds.has(acquisition.sceneId);
        const position = positionForTime(Date.parse(acquisition.capturedAt), domain);
        const isRadar = acquisition.modality === "sar";

        const cloudLabel =
          acquisition.cloudCoverPercentage === null
            ? "radar"
            : `${Math.round(acquisition.cloudCoverPercentage)}% cloud`;

        return (
          <HoverCard key={acquisition.id} openDelay={200} closeDelay={100}>
            <HoverCardTrigger asChild>
              <button
                type="button"
                onClick={() => onSelectAcquisition(acquisition)}
                aria-label={`${acquisition.capturedAt.slice(0, 10)}, ${acquisition.sensorPlatform}, ${cloudLabel}`}
                aria-pressed={isSelected}
                className="group absolute top-1/2 -translate-x-1/2 -translate-y-1/2 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                style={{ left: `${position * 100}%`, width: TIMELINE_LAYOUT.markerWidthPx * 4 }}
              >
                <span
                  className={cn(
                    "mx-auto block rounded-[1px] border transition-all duration-300 group-hover:scale-125 group-hover:shadow-[0_0_8px_rgba(255,255,255,0.4)]",
                    isSelected
                      ? "border-aeris-teal bg-aeris-teal shadow-[0_0_10px_var(--color-aeris-teal)]"
                      : !usable
                        ? "border-aeris-amber/60 bg-transparent"
                        : colorByModality && isRadar
                          ? "border-aeris-blue/70 bg-aeris-blue/45 group-hover:border-aeris-blue group-hover:bg-aeris-blue/70"
                          : "border-foreground/50 bg-foreground/35 group-hover:border-aeris-teal group-hover:bg-aeris-teal/60",
                  )}
                  style={{
                    width: TIMELINE_LAYOUT.markerWidthPx,
                    height: isSelected ? TIMELINE_LAYOUT.laneHeightPx - 2 : TIMELINE_LAYOUT.laneHeightPx - 6,
                  }}
                />
                {/* An underline marks the dates the answer on screen actually drew from. */}
                {isCited ? (
                  <span
                    className="absolute inset-x-0 -bottom-0.5 mx-auto h-px bg-aeris-blue"
                    style={{ width: TIMELINE_LAYOUT.markerWidthPx }}
                    aria-hidden="true"
                  />
                ) : null}
              </button>
            </HoverCardTrigger>
            <HoverCardContent side="top" className="w-52 p-0 overflow-hidden bg-surface-2/95 backdrop-blur-md border-border/60 shadow-xl shadow-black/40">
              {acquisition.quicklookUrl && (
                <div className="w-full h-28 relative bg-surface-1 border-b border-border/50">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={acquisition.quicklookUrl} alt="Quicklook" className="absolute inset-0 w-full h-full object-cover" />
                </div>
              )}
              <div className="p-3 text-xs flex flex-col gap-1.5">
                <span className="font-mono text-aeris-teal tracking-wide">{acquisition.capturedAt.slice(0, 10)}</span>
                <span className="text-foreground font-medium">{acquisition.sensorPlatform}</span>
                <span className={cn("text-muted-foreground", !usable && "text-aeris-amber")}>
                  {cloudLabel}{usable ? "" : " · not usable"}
                </span>
              </div>
            </HoverCardContent>
          </HoverCard>
        );
      })}
    </div>
  );
}

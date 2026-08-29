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
          <button
            key={acquisition.id}
            type="button"
            onClick={() => onSelectAcquisition(acquisition)}
            title={`${acquisition.capturedAt.slice(0, 10)} · ${acquisition.sensorPlatform} · ${cloudLabel}${usable ? "" : " · not usable"}`}
            aria-label={`${acquisition.capturedAt.slice(0, 10)}, ${acquisition.sensorPlatform}, ${cloudLabel}`}
            aria-pressed={isSelected}
            className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            style={{ left: `${position * 100}%`, width: TIMELINE_LAYOUT.markerWidthPx * 2 }}
          >
            <span
              className={cn(
                "mx-auto block rounded-[1px] border transition-colors duration-fast",
                isSelected
                  ? "border-aeris-teal bg-aeris-teal"
                  : !usable
                    ? // Hollow: catalogued, but nothing here can answer a question.
                      "border-aeris-amber/60 bg-transparent"
                    : colorByModality && isRadar
                      ? // On the merged rule the mark is the only thing that can say which sensor it is.
                        "border-aeris-blue/70 bg-aeris-blue/45 hover:border-aeris-blue hover:bg-aeris-blue/70"
                      : "border-foreground/50 bg-foreground/35 hover:border-aeris-teal hover:bg-aeris-teal/60",
              )}
              style={{
                width: TIMELINE_LAYOUT.markerWidthPx,
                height: isSelected ? TIMELINE_LAYOUT.laneHeightPx - 4 : TIMELINE_LAYOUT.laneHeightPx - 8,
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
        );
      })}
    </div>
  );
}

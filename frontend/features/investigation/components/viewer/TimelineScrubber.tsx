// features/investigation/components/viewer/TimelineScrubber.tsx — choosing which two observations are being compared.
//
// what  : The dated axis of everything the archive holds over this area, with two handles that select the
//         baseline and the comparison, coverage holes drawn in, play-through of the series, and a standing
//         verdict on whether the chosen pair can honestly be compared.
// where : The bottom of the centre column in InvestigationScreen, beneath the comparator labels.
// how   : This is the input selector for the entire investigation, not a playback widget. Change detection
//         needs a pair, and until now that pair was chosen by clicking rows in a list that never showed
//         time — the single decision that determines the answer, made through the interface least able to
//         inform it. Two handles on a dated axis make it the thing being looked at.
//
//         Handles SNAP to acquisitions. A handle resting between two passes would imply imagery that does
//         not exist, and a date with nothing behind it is not something the operator can be shown.
//
//         Unusable acquisitions stay on the axis as hollow marks and coverage holes are drawn explicitly,
//         because a gap is information. An operator who cannot see that the archive has nothing analysable
//         across 2021 will read a change spanning it as a finding rather than as an artefact of what was
//         available — which is the most common way a change-detection result is quietly wrong.
//
//         The verdict under the track is the other half of that. Comparing March against September over
//         farmland produces a large, real, uninteresting difference: the crop cycle. Saying so at
//         selection time is what separates an analysis from a phenology artefact wearing its confidence.

"use client";

import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { useCallback, useRef } from "react";

import { Chip } from "@/components/sharedUI/dumbComponent/Chip";
import { Button } from "@/components/ui/button";
import { TIMELINE_LAYOUT, TIMELINE_PLAYBACK } from "@/lib/constants/timeline";
import { cn } from "@/lib/utils";

import { isSelectable, positionForTime } from "../../lib/timeline-geometry";
import type { TimelineRole } from "../../hooks/use-timeline";
import type { Acquisition } from "../../types/investigation.types";
import type { CoverageGap, PairRecommendation } from "../../types/catalogue.types";
import { ArchiveQueryPopover } from "./ArchiveQueryPopover";
import { TimelineTrack } from "./TimelineTrack";
import type { useTimeline } from "../../hooks/use-timeline";

type TimelineControls = ReturnType<typeof useTimeline>;

interface TimelineScrubberProps {
  timeline: TimelineControls;
  /** Archive query state, so the query surface and the axis it changes sit in one control. */
  archive: {
    isSearching: boolean;
    error: Error | null;
    coverageGaps: CoverageGap[];
    recommendation: PairRecommendation | null;
    advisory: string | null;
    onSearch: (window: {
      from: string;
      to: string;
      modalities: import("../../types/catalogue.types").AcquisitionModality[];
      cloudCeilingPercentage: number;
    }) => void;
    onDismissRecommendation: () => void;
  };
}

const VERDICT_TONE = {
  clean: "green",
  degraded: "amber",
  unusable: "red",
} as const;

export function TimelineScrubber({ timeline, archive }: TimelineScrubberProps) {
  const {
    lanes,
    domain,
    gaps,
    baseline,
    comparison,
    assessment,
    cloudCeilingPercentage,
    isPlaying,
    playbackRate,
    citedSceneIds,
  } = timeline;

  const trackRef = useRef<HTMLDivElement | null>(null);
  const draggingRoleRef = useRef<TimelineRole | null>(null);

  const baselinePosition = domain && baseline
    ? positionForTime(Date.parse(baseline.capturedAt), domain)
    : null;
  const comparisonPosition = domain && comparison
    ? positionForTime(Date.parse(comparison.capturedAt), domain)
    : null;

  /** Which handle a gesture at this position is reaching for. Nearest wins; an empty side always wins. */
  const roleNearest = useCallback(
    (position: number): TimelineRole => {
      if (baselinePosition === null) {
        return "baseline";
      }
      if (comparisonPosition === null) {
        return "comparison";
      }
      return Math.abs(position - baselinePosition) <= Math.abs(position - comparisonPosition)
        ? "baseline"
        : "comparison";
    },
    [baselinePosition, comparisonPosition],
  );

  const positionFromClientX = useCallback((clientX: number): number | null => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) {
      return null;
    }
    return Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
  }, []);

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const position = positionFromClientX(event.clientX);
      if (position === null) {
        return;
      }

      // Taking hold of a handle is an act of control, so it ends the automatic play-through rather than
      // fighting it for the same selection.
      if (isPlaying) {
        timeline.setPlaying(false);
      }

      const role = roleNearest(position);
      draggingRoleRef.current = role;
      event.currentTarget.setPointerCapture(event.pointerId);
      timeline.selectNearest(role, position);
    },
    [isPlaying, positionFromClientX, roleNearest, timeline],
  );

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const role = draggingRoleRef.current;
      if (!role) {
        return;
      }
      const position = positionFromClientX(event.clientX);
      if (position !== null) {
        timeline.selectNearest(role, position);
      }
    },
    [positionFromClientX, timeline],
  );

  const endDrag = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    draggingRoleRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const handleSelectAcquisition = useCallback(
    (acquisition: Acquisition) => {
      if (!isSelectable(acquisition, cloudCeilingPercentage) || !domain) {
        return;
      }
      const position = positionForTime(Date.parse(acquisition.capturedAt), domain);
      timeline.select(roleNearest(position), acquisition);
    },
    [cloudCeilingPercentage, domain, roleNearest, timeline],
  );

  if (!domain || lanes.length === 0) {
    return null;
  }

  const lanesHeight =
    lanes.length * TIMELINE_LAYOUT.laneHeightPx + (lanes.length - 1) * TIMELINE_LAYOUT.laneGapPx;

  const selectedSceneIds = [baseline?.sceneId ?? null, comparison?.sceneId ?? null];
  const bandStart = Math.min(baselinePosition ?? 0, comparisonPosition ?? 0);
  const bandEnd = Math.max(baselinePosition ?? 0, comparisonPosition ?? 0);
  const hasBand = baselinePosition !== null && comparisonPosition !== null;

  return (
    <div className="pointer-events-auto w-full max-w-3xl rounded-md border border-border bg-surface-2/70 px-3 py-2 backdrop-blur-md">
      {/* ── What is selected, and what the archive thinks of it ────────────────────────────────── */}
      <div className="flex items-center gap-2">
        <span className="aeris-technical shrink-0">Archive</span>

        <Chip tone={VERDICT_TONE[assessment.quality]} title={assessment.notes.join(" ")}>
          {assessment.headline}
        </Chip>

        {assessment.separationDays !== null ? (
          <span className="font-mono text-[10px] tabular-nums whitespace-nowrap text-muted-foreground">
            {assessment.separationDays.toLocaleString()} days apart
          </span>
        ) : null}

        <span className="flex-1" />

        <div className="flex items-center gap-0.5">
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            aria-label="Previous acquisition"
            onClick={() => timeline.step("comparison", -1)}
          >
            <ChevronLeft />
          </Button>
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            aria-label={isPlaying ? "Pause the archive play-through" : "Play through the archive"}
            onClick={() => timeline.setPlaying(!isPlaying)}
            className={cn(isPlaying && "text-aeris-teal")}
          >
            {isPlaying ? <Pause /> : <Play />}
          </Button>
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            aria-label="Next acquisition"
            onClick={() => timeline.step("comparison", 1)}
          >
            <ChevronRight />
          </Button>

          {TIMELINE_PLAYBACK.rates.map((rate) => (
            <button
              key={rate}
              type="button"
              onClick={() => timeline.setPlaybackRate(rate)}
              aria-pressed={playbackRate === rate}
              className={cn(
                "rounded-sm px-1 font-mono text-[10px] transition-colors duration-fast",
                playbackRate === rate
                  ? "text-aeris-teal"
                  : "text-muted-foreground/60 hover:text-foreground",
              )}
            >
              {rate}×
            </button>
          ))}
        </div>

        <ArchiveQueryPopover
          from={new Date(domain.startMs).toISOString()}
          to={new Date(domain.endMs).toISOString()}
          modalities={lanes.map((lane) => lane.modality)}
          cloudCeilingPercentage={cloudCeilingPercentage}
          isSearching={archive.isSearching}
          error={archive.error}
          coverageGaps={archive.coverageGaps}
          recommendation={archive.recommendation}
          advisory={archive.advisory}
          onSearch={archive.onSearch}
          onApplyRecommendation={(recommendation) => {
            timeline.applyPair(recommendation.t0SceneId, recommendation.t1SceneId);
            archive.onDismissRecommendation();
          }}
          onDismissRecommendation={archive.onDismissRecommendation}
        />
      </div>

      {/* ── The axis ───────────────────────────────────────────────────────────────────────────── */}
      <div
        className="relative mt-2 ml-14 touch-none select-none"
        style={{ height: lanesHeight, paddingInline: 0 }}
        ref={trackRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        {/* Coverage holes sit behind everything: the operator should read them as absence, not as content. */}
        {gaps.map((gap) => {
          const start = positionForTime(gap.startMs, domain);
          const end = positionForTime(gap.endMs, domain);
          return (
            <span
              key={gap.id}
              title={`${gap.days} days with no usable acquisition`}
              aria-hidden="true"
              className="absolute inset-y-0 bg-[repeating-linear-gradient(135deg,transparent,transparent_3px,var(--color-aeris-amber)_3px,var(--color-aeris-amber)_4px)] opacity-20"
              style={{ left: `${start * 100}%`, width: `${(end - start) * 100}%` }}
            />
          );
        })}

        {/* The interval the current pair spans — the window the answer is actually about. */}
        {hasBand ? (
          <span
            aria-hidden="true"
            className="absolute inset-y-0 border-x border-aeris-teal/30 bg-aeris-teal/8"
            style={{ left: `${bandStart * 100}%`, width: `${(bandEnd - bandStart) * 100}%` }}
          />
        ) : null}

        <div className="flex flex-col" style={{ gap: TIMELINE_LAYOUT.laneGapPx }}>
          {lanes.map((lane) => (
            <TimelineTrack
              key={lane.modality}
              label={lane.label}
              acquisitions={lane.acquisitions}
              domain={domain}
              cloudCeilingPercentage={cloudCeilingPercentage}
              selectedSceneIds={selectedSceneIds}
              citedSceneIds={citedSceneIds}
              onSelectAcquisition={handleSelectAcquisition}
            />
          ))}
        </div>

        {baselinePosition !== null ? (
          <ScrubHandle
            role="baseline"
            label="T0"
            acquisition={baseline}
            position={baselinePosition}
            onStep={timeline.step}
          />
        ) : null}
        {comparisonPosition !== null ? (
          <ScrubHandle
            role="comparison"
            label="T1"
            acquisition={comparison}
            position={comparisonPosition}
            onStep={timeline.step}
          />
        ) : null}
      </div>

      {/* ── Year rule ──────────────────────────────────────────────────────────────────────────── */}
      <div className="relative ml-14 mt-1" style={{ height: TIMELINE_LAYOUT.axisHeightPx }}>
        {yearTicks(domain.startMs, domain.endMs).map((tick) => (
          <span
            key={tick.year}
            className="absolute top-0 -translate-x-1/2 font-mono text-[9px] tabular-nums text-muted-foreground/60"
            style={{ left: `${positionForTime(tick.timeMs, domain) * 100}%` }}
          >
            {tick.year}
          </span>
        ))}
      </div>

      {/* ── Why this pair may not be what it looks like ────────────────────────────────────────── */}
      {assessment.notes.length > 0 ? (
        <ul className="mt-1.5 flex flex-col gap-0.5 border-t border-border-soft pt-1.5">
          {assessment.notes.slice(0, 2).map((note) => (
            <li
              key={note}
              className={cn(
                "text-[10px] leading-relaxed",
                assessment.quality === "unusable" ? "text-aeris-red" : "text-aeris-amber",
              )}
            >
              {note}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * One end of the comparison.
 *
 * A slider rather than a decorative marker: an operator working a keyboard has to be able to step through
 * the archive, and a date selector that only responds to a drag excludes them from the one control that
 * decides what the analysis runs on.
 */
function ScrubHandle({
  role,
  label,
  acquisition,
  position,
  onStep,
}: {
  role: TimelineRole;
  label: string;
  acquisition: Acquisition | null;
  position: number;
  onStep: (role: TimelineRole, direction: 1 | -1) => void;
}) {
  const capturedDate = acquisition?.capturedAt.slice(0, 10) ?? "—";

  return (
    <div
      className="pointer-events-none absolute inset-y-0 z-10 -translate-x-1/2"
      style={{ left: `${position * 100}%` }}
    >
      <button
        type="button"
        role="slider"
        aria-label={`${label} observation`}
        aria-valuetext={capturedDate}
        aria-valuenow={acquisition ? Date.parse(acquisition.capturedAt) : undefined}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") {
            event.preventDefault();
            onStep(role, -1);
          } else if (event.key === "ArrowRight") {
            event.preventDefault();
            onStep(role, 1);
          }
        }}
        className="pointer-events-auto absolute inset-y-0 -left-2 w-4 cursor-ew-resize focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <span
          className="absolute inset-y-0 left-1/2 -translate-x-1/2 bg-aeris-teal"
          style={{ width: TIMELINE_LAYOUT.handleWidthPx }}
          aria-hidden="true"
        />
        <span className="absolute -top-4 left-1/2 -translate-x-1/2 rounded-sm border border-aeris-teal/40 bg-surface-2 px-1 font-mono text-[9px] whitespace-nowrap text-aeris-teal">
          {label} {capturedDate}
        </span>
      </button>
    </div>
  );
}

/**
 * Year labels for the rule, thinned so they never collide.
 *
 * A twenty-year archive with every year printed is an unreadable smear; stepping the labels keeps the
 * axis legible without changing what the track is showing.
 */
function yearTicks(startMs: number, endMs: number): { year: number; timeMs: number }[] {
  const firstYear = new Date(startMs).getUTCFullYear();
  const lastYear = new Date(endMs).getUTCFullYear();
  const span = lastYear - firstYear;
  const step = span <= 8 ? 1 : span <= 20 ? 2 : 5;

  const ticks: { year: number; timeMs: number }[] = [];
  for (let year = firstYear; year <= lastYear; year += step) {
    const timeMs = Date.UTC(year, 0, 1);
    if (timeMs >= startMs && timeMs <= endMs) {
      ticks.push({ year, timeMs });
    }
  }

  return ticks;
}

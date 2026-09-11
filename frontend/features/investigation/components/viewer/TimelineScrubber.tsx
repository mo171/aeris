// features/investigation/components/viewer/TimelineScrubber.tsx — choosing which two observations are being compared.
//
// what  : The dated axis of everything the archive holds over this area, with two handles that select the
//         baseline and the comparison, coverage holes drawn in, play-through of the series, and a standing
//         verdict on whether the chosen pair can honestly be compared.
// where : The bottom of the centre column in InvestigationScreen.
// how   : This is the input selector for the entire investigation, not a playback widget. Change detection
//         needs a pair, and that pair used to be chosen by clicking rows in a list that never showed time —
//         the single decision that determines the answer, made through the interface least able to inform
//         it. Two handles on a dated axis make it the thing being looked at.
//
//         COLLAPSED BY DEFAULT. The first build put nine controls in one strip with the comparator playbar
//         stacked above it answering an overlapping question, and it read as an instrument panel rather
//         than a control. What survives in the compact state is what an operator uses on every
//         investigation: the axis, two handles, one verdict, and step-and-play. Sensor lanes, speeds, the
//         archive query and the comparator binding are all real, all one click away, and none of them are
//         needed to answer the question the page is open for.
//
//         Handle positions are written straight to the DOM, never through React. They track the pointer at
//         its own rate, and a render per pointer move would spend exactly the frame budget the scene
//         needs — the same reason the comparator handle and the coordinate readout work this way. The
//         SELECTION is React state and snaps to real acquisitions; the HANDLE is a DOM node that follows
//         the finger. Separating those is what fixed the drag feeling notched: it used to jump between
//         acquisitions because the only position it had was the committed one.
//
//         Unusable acquisitions stay on the axis as hollow marks and coverage holes are drawn explicitly,
//         because a gap is information. An operator who cannot see that the archive has nothing analysable
//         across 2021 will read a change spanning it as a finding rather than as an artefact of what was
//         available — the most common way a change-detection result is quietly wrong.

"use client";

import { ChevronDown, ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Chip } from "@/components/sharedUI/dumbComponent/Chip";
import { Button } from "@/components/ui/button";
import { TIMELINE_LAYOUT, TIMELINE_PLAYBACK } from "@/lib/constants/timeline";
import { cn } from "@/lib/utils";

import { isSelectable, positionForTime } from "../../lib/timeline-geometry";
import type { TimelineRole, useTimeline } from "../../hooks/use-timeline";
import { useInvestigationStore } from "../../store/investigation-store";
import type { Acquisition, WorkspaceMode } from "../../types/investigation.types";
import type {
  AcquisitionModality,
  CoverageGap,
  PairRecommendation,
} from "../../types/catalogue.types";
import { ArchiveQueryPopover } from "./ArchiveQueryPopover";
import { TimelineTrack } from "./TimelineTrack";

type TimelineControls = ReturnType<typeof useTimeline>;

interface TimelineScrubberProps {
  timeline: TimelineControls;
  /** Whether a cross-modal pair is available, so the binding switch can say when it is not. */
  hasCrossModalScene: boolean;
  archive: {
    isSearching: boolean;
    error: Error | null;
    coverageGaps: CoverageGap[];
    recommendation: PairRecommendation | null;
    advisory: string | null;
    onSearch: (window: {
      from: string;
      to: string;
      modalities: AcquisitionModality[];
      cloudCeilingPercentage: number;
    }) => void;
    onDismissRecommendation: () => void;
  };
  isAutoFetchingSar?: boolean;
  onAutoFetchCrossModal?: (from: string, to: string) => void;
}

const VERDICT_TONE = { clean: "green", degraded: "amber", unusable: "red" } as const;
const BINDING_LABEL: Record<WorkspaceMode, string> = {
  temporal: "Temporal",
  crossModal: "Cross-modal",
};

/** Said in terms of what the operator will see, not of which slots are bound. */
const BINDING_HINT: Record<WorkspaceMode, string> = {
  temporal: "Compare the two dates — the same sensor, before against after",
  crossModal: "Compare radar against optical — does backscatter agree with reflectance?",
};

export function TimelineScrubber({
  timeline,
  hasCrossModalScene,
  archive,
  isAutoFetchingSar = false,
  onAutoFetchCrossModal,
}: TimelineScrubberProps) {
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

  const [isExpanded, setExpanded] = useState(false);
  const crossModalLensActive = useInvestigationStore((state) => state.crossModalLens.isActive);
  const setCrossModalLensActive = useInvestigationStore((state) => state.setCrossModalLensActive);

  const trackRef = useRef<HTMLDivElement | null>(null);
  const baselineHandleRef = useRef<HTMLDivElement | null>(null);
  const comparisonHandleRef = useRef<HTMLDivElement | null>(null);
  const magnetRef = useRef<HTMLSpanElement | null>(null);
  const bandRef = useRef<HTMLSpanElement | null>(null);
  const draggingRoleRef = useRef<TimelineRole | null>(null);

  const baselinePosition =
    domain && baseline ? positionForTime(Date.parse(baseline.capturedAt), domain) : null;
  const comparisonPosition =
    domain && comparison ? positionForTime(Date.parse(comparison.capturedAt), domain) : null;

  /** Writes a handle and the selection band to the DOM. The only place either position is set. */
  const paint = useCallback((role: TimelineRole, position: number | null) => {
    const element = role === "baseline" ? baselineHandleRef.current : comparisonHandleRef.current;
    if (element) {
      element.style.left = position === null ? "-100%" : `${position * 100}%`;
      element.style.visibility = position === null ? "hidden" : "visible";
    }

    const band = bandRef.current;
    if (!band) {
      return;
    }

    const other =
      role === "baseline"
        ? comparisonHandleRef.current?.style.left
        : baselineHandleRef.current?.style.left;
    const otherPosition = other ? Number.parseFloat(other) / 100 : null;

    if (position === null || otherPosition === null || Number.isNaN(otherPosition)) {
      band.style.width = "0%";
      return;
    }

    band.style.left = `${Math.min(position, otherPosition) * 100}%`;
    band.style.width = `${Math.abs(position - otherPosition) * 100}%`;
  }, []);

  // React owns the SELECTION; this effect is what turns a selection into a position. During a drag the
  // pointer owns the handle instead, so the committed position is not allowed to fight the finger.
  useEffect(() => {
    if (draggingRoleRef.current !== "baseline") {
      paint("baseline", baselinePosition);
    }
  }, [baselinePosition, paint]);

  useEffect(() => {
    if (draggingRoleRef.current !== "comparison") {
      paint("comparison", comparisonPosition);
    }
  }, [comparisonPosition, paint]);

  const roleNearest = useCallback(
    (position: number): TimelineRole => {
      if (baselinePosition === null) return "baseline";
      if (comparisonPosition === null) return "comparison";
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

  /** Marks the acquisition the handle will land on, so the snap is visible before it happens. */
  const showMagnet = useCallback(
    (position: number | null) => {
      const magnet = magnetRef.current;
      if (!magnet || !domain) {
        return;
      }

      if (position === null) {
        magnet.style.opacity = "0";
        return;
      }

      magnet.style.opacity = "1";
      magnet.style.left = `${position * 100}%`;
    },
    [domain],
  );

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
      timeline.setScrubbing(true);
      event.currentTarget.setPointerCapture(event.pointerId);

      paint(role, position);
      timeline.selectNearest(role, position);
    },
    [isPlaying, paint, positionFromClientX, roleNearest, timeline],
  );

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const role = draggingRoleRef.current;
      const position = positionFromClientX(event.clientX);
      if (position === null) {
        return;
      }

      if (!role) {
        // Not dragging: the magnet still previews where a press would land.
        showMagnet(position);
        return;
      }

      // The handle follows the finger continuously; the SELECTION snaps to a real acquisition underneath.
      paint(role, position);
      timeline.selectNearest(role, position);
    },
    [paint, positionFromClientX, showMagnet, timeline],
  );

  const endDrag = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const role = draggingRoleRef.current;
      draggingRoleRef.current = null;
      timeline.setScrubbing(false);

      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }

      // Settle onto the acquisition actually selected, so the handle never rests on a date with no pass.
      if (role === "baseline") {
        paint("baseline", baselinePosition);
      } else if (role === "comparison") {
        paint("comparison", comparisonPosition);
      }
    },
    [baselinePosition, comparisonPosition, paint, timeline],
  );

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

  // Compact merges every sensor onto one rule; expanded splits them so a cloud-blocked optical window can
  // be read against the radar that covers it.
  const renderedLanes = isExpanded
    ? lanes
    : [{ modality: "optical" as const, label: "ALL", acquisitions: lanes.flatMap((l) => l.acquisitions) }];

  const lanesHeight =
    renderedLanes.length * TIMELINE_LAYOUT.laneHeightPx +
    (renderedLanes.length - 1) * TIMELINE_LAYOUT.laneGapPx;

  const selectedSceneIds = [baseline?.sceneId ?? null, comparison?.sceneId ?? null];

  return (
    <div className="pointer-events-auto w-full max-w-3xl rounded-md border border-border bg-surface-2/70 px-3 py-2 backdrop-blur-md">
      {/* ── Always visible ──────────────────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2">
        <span className="aeris-technical shrink-0">Archive</span>

        <Chip tone={VERDICT_TONE[assessment.quality]} title={assessment.notes.join(" ")}>
          {assessment.headline}
        </Chip>

        {assessment.separationDays !== null ? (
          <span className="font-mono text-[10px] tabular-nums whitespace-nowrap text-muted-foreground">
            {assessment.separationDays.toLocaleString()}d apart
          </span>
        ) : null}

        <span className="flex-1" />

        {/*
          Which PAIR is being compared stays visible at all times. It was briefly folded into the expand
          alongside the speeds, and that was wrong: a playback rate is a preference, but temporal against
          cross-modal changes what the whole comparator is showing, and a mode switch nobody can see is a
          mode nobody knows they are in.
        */}
        <span className="flex items-center gap-0.5">
          {(Object.keys(BINDING_LABEL) as WorkspaceMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              disabled={mode === "crossModal" && !hasCrossModalScene && !onAutoFetchCrossModal}
              onClick={() => {
                if (mode === "crossModal") {
                  if (!hasCrossModalScene && onAutoFetchCrossModal) {
                    onAutoFetchCrossModal(
                      new Date(domain.startMs).toISOString(),
                      new Date(domain.endMs).toISOString(),
                    );
                  } else {
                    setCrossModalLensActive(true);
                  }
                } else {
                  setCrossModalLensActive(false);
                }
              }}
              aria-pressed={
                (mode === "crossModal" && crossModalLensActive) ||
                (mode === "temporal" && !crossModalLensActive)
              }
              title={
                mode === "crossModal" && !hasCrossModalScene
                  ? "Click to auto-fetch a matching radar scene from the archive"
                  : BINDING_HINT[mode]
              }
              className={cn(
                "rounded-sm px-1.5 py-0.5 font-mono text-[10px] tracking-wide transition-colors duration-fast disabled:opacity-35",
                ((mode === "crossModal" && crossModalLensActive) ||
                  (mode === "temporal" && !crossModalLensActive))
                  ? "bg-aeris-teal/10 text-aeris-teal"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {mode === "crossModal" && isAutoFetchingSar ? "Fetching..." : BINDING_LABEL[mode]}
            </button>
          ))}
        </span>

        <span className="h-3 w-px bg-border" aria-hidden="true" />

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
        </div>

        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          aria-label={isExpanded ? "Hide archive controls" : "Show archive controls"}
          aria-expanded={isExpanded}
          onClick={() => setExpanded((current) => !current)}
        >
          <ChevronDown className={cn("transition-transform duration-fast", isExpanded && "rotate-180")} />
        </Button>
      </div>

      {/* ── The axis ────────────────────────────────────────────────────────────────────────────── */}
      <div
        className={cn("relative mt-2 touch-none select-none", isExpanded && "ml-14")}
        style={{ height: lanesHeight }}
        ref={trackRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onPointerLeave={() => showMagnet(null)}
      >
        {/* Coverage holes sit behind everything: they should read as absence, not as content. */}
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
        <span
          ref={bandRef}
          aria-hidden="true"
          className="absolute inset-y-0 border-x border-aeris-teal/40 bg-gradient-to-r from-aeris-teal/5 via-aeris-teal/10 to-aeris-teal/5 shadow-[inset_0_0_15px_rgba(0,255,200,0.05)] transition-all duration-75"
          style={{ left: "0%", width: "0%" }}
        />

        <span
          ref={magnetRef}
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 w-px bg-foreground/25 opacity-0 transition-opacity duration-fast"
        />

        <div className="flex flex-col" style={{ gap: TIMELINE_LAYOUT.laneGapPx }}>
          {renderedLanes.map((lane) => (
            <TimelineTrack
              key={lane.label}
              label={lane.label}
              showLabel={isExpanded}
              colorByModality={!isExpanded}
              acquisitions={lane.acquisitions}
              domain={domain}
              cloudCeilingPercentage={cloudCeilingPercentage}
              selectedSceneIds={selectedSceneIds}
              citedSceneIds={citedSceneIds}
              onSelectAcquisition={handleSelectAcquisition}
            />
          ))}
        </div>

        <ScrubHandle
          ref={baselineHandleRef}
          role="baseline"
          label="T0"
          acquisition={baseline}
          onStep={timeline.step}
        />
        <ScrubHandle
          ref={comparisonHandleRef}
          role="comparison"
          label="T1"
          acquisition={comparison}
          onStep={timeline.step}
        />
      </div>

      {/* ── Year rule ───────────────────────────────────────────────────────────────────────────── */}
      <div
        className={cn("relative mt-1", isExpanded && "ml-14")}
        style={{ height: TIMELINE_LAYOUT.axisHeightPx }}
      >
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

      {/* ── Everything a routine investigation does not need ────────────────────────────────────── */}
      {isExpanded ? (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-border-soft pt-2">
          <span className="flex items-center gap-1">
            <span className="aeris-technical">Speed</span>
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
          </span>

          <span className="flex-1" />

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
      ) : null}

      {/* Why this pair may not be what it looks like. Shown collapsed too — it is not an advanced detail. */}
      {assessment.notes.length > 0 ? (
        <ul className="mt-1.5 flex flex-col gap-0.5 border-t border-border-soft pt-1.5">
          {assessment.notes.slice(0, isExpanded ? 3 : 1).map((note) => (
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
 *
 * Its position is set by the parent through the ref, never by a prop — see the file header.
 */
function ScrubHandle({
  ref,
  role,
  label,
  acquisition,
  onStep,
}: {
  ref: React.Ref<HTMLDivElement>;
  role: TimelineRole;
  label: string;
  acquisition: Acquisition | null;
  onStep: (role: TimelineRole, direction: 1 | -1) => void;
}) {
  const capturedDate = acquisition?.capturedAt.slice(0, 10) ?? "—";

  return (
    <div
      ref={ref}
      className="pointer-events-none absolute inset-y-0 z-10 -translate-x-1/2"
      style={{ left: "-100%", visibility: "hidden" }}
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
        className="group pointer-events-auto absolute inset-y-0 -left-2 w-4 cursor-ew-resize focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <span
          className="absolute inset-y-0 left-1/2 -translate-x-1/2 bg-aeris-teal shadow-[0_0_8px_var(--color-aeris-teal)] transition-transform duration-100 group-hover:scale-x-150"
          style={{ width: TIMELINE_LAYOUT.handleWidthPx }}
          aria-hidden="true"
        />
        <span className="absolute -top-6 left-1/2 -translate-x-1/2 rounded-full border border-aeris-teal/30 bg-surface-2/80 backdrop-blur-md px-2 py-0.5 font-mono text-[9px] whitespace-nowrap text-aeris-teal shadow-lg shadow-black/50 transition-all duration-200 group-hover:-top-7 group-hover:border-aeris-teal/60 group-hover:bg-surface-2/95 group-hover:shadow-[0_4px_12px_rgba(0,255,200,0.2)]">
          {label} <span className="text-foreground ml-1">{capturedDate}</span>
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

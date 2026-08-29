// features/investigation/hooks/use-timeline.ts — the temporal selection, and the imagery it puts on the scene.
//
// what  : Resolves which two acquisitions the comparator is showing, builds the raster layers for them,
//         reports whether the pair is a fair comparison, and drives play-through of the archive.
// where : Called once by InvestigationScreen. Its layers and comparator binding are handed to
//         use-scene-stage-binding; its lanes and selection drive TimelineScrubber.
// how   : The pair is the single input that determines the answer, so it gets one owner. Before this hook
//         existed the selection was implicit in whichever scenes happened to occupy the T0 and T1 role
//         slots, bound by clicking rows in a list that never showed time — which meant the most
//         consequential decision in the workspace was made through the interface least able to inform it.
//
//         Selection falls back to the role slots rather than duplicating them. On arrival nothing is
//         chosen, the slots stand, and the comparator binds exactly as it always did; the moment a handle
//         moves, this hook takes over that side. That fallback is what keeps the change additive — no
//         investigation has to carry a timeline selection for the workspace to work.
//
//         Scrubbed imagery is pushed as a BASE layer, not as evidence. It carries no provenance block
//         because it has no model behind it: it is the pixels an analysis would run on, not a product of
//         one. Giving it a fabricated trace step so it could pose as an EvidenceLayer would put a lie in
//         the one structure this product asks people to trust.
//
//         Play-through steps acquisition to acquisition rather than sliding continuously. There is nothing
//         to show between two passes, and a continuous slider would imply an archive that does not exist.

"use client";

import { useCallback, useEffect, useMemo } from "react";

import type { StageLayer } from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";
import { TIMELINE_PLAYBACK } from "@/lib/constants/timeline";
import { useGeoStageStore } from "@/store/geo-stage-store";

import {
  assessPair,
  buildLanes,
  computeCoverageGaps,
  computeDomain,
  isSelectable,
  nearestAcquisition,
  stepAcquisition,
  type TimelineDomain,
  type TimelineGap,
  type TimelineLane,
  type TimelinePairAssessment,
} from "../lib/timeline-geometry";
import { useInvestigationStore } from "../store/investigation-store";
import type { Acquisition, Investigation } from "../types/investigation.types";

/** Which end of the comparison a handle controls. Named for the work, not for the slot it usually maps to. */
export type TimelineRole = "baseline" | "comparison";

interface TimelineControls {
  lanes: TimelineLane[];
  domain: TimelineDomain | null;
  gaps: TimelineGap[];
  baseline: Acquisition | null;
  comparison: Acquisition | null;
  assessment: TimelinePairAssessment;
  cloudCeilingPercentage: number;
  isPlaying: boolean;
  playbackRate: number;
  /** Scene ids the current answer cites, so the operator can see which dates the evidence came from. */
  citedSceneIds: ReadonlySet<string>;

  /** Base rasters for any selection the role slots do not already cover. Empty on arrival. */
  layers: StageLayer[];
  /** Comparator binding the timeline owns, or null to leave the role-based binding in charge. */
  comparatorOverride: { left: string | null; right: string | null } | null;

  select: (role: TimelineRole, acquisition: Acquisition) => void;
  selectNearest: (role: TimelineRole, position: number) => void;
  step: (role: TimelineRole, direction: 1 | -1) => void;
  applyPair: (baselineSceneId: string, comparisonSceneId: string) => void;
  setPlaying: (isPlaying: boolean) => void;
  /** Told while a handle is being dragged, so the renderer can shorten its cross-fade. */
  setScrubbing: (isScrubbing: boolean) => void;
  setPlaybackRate: (rate: number) => void;
  setCloudCeiling: (percentage: number) => void;
}

interface TimelineOptions {
  investigation: Investigation | undefined;
  /** Scene ids referenced by the evidence of the current run, taken from the graph. */
  citedSceneIds: readonly string[];
}

export function useTimeline({ investigation, citedSceneIds }: TimelineOptions): TimelineControls {
  const baselineSceneId = useInvestigationStore((state) => state.timelineBaselineSceneId);
  const comparisonSceneId = useInvestigationStore((state) => state.timelineComparisonSceneId);
  const isPlaying = useInvestigationStore((state) => state.isTimelinePlaying);
  const playbackRate = useInvestigationStore((state) => state.timelinePlaybackRate);
  const cloudCeilingPercentage = useInvestigationStore(
    (state) => state.timelineCloudCeilingPercentage,
  );
  const comparatorBinding = useInvestigationStore((state) => state.comparatorBinding);

  const setTimelineSelection = useInvestigationStore((state) => state.setTimelineSelection);
  const setTimelinePair = useInvestigationStore((state) => state.setTimelinePair);
  const setPlaying = useInvestigationStore((state) => state.setTimelinePlaying);
  const setScrubbing = useInvestigationStore((state) => state.setTimelineScrubbing);
  const setPlaybackRate = useInvestigationStore((state) => state.setTimelinePlaybackRate);
  const setCloudCeiling = useInvestigationStore((state) => state.setTimelineCloudCeiling);

  const acquisitions = useMemo(() => investigation?.acquisitions ?? [], [investigation]);

  const domain = useMemo(() => computeDomain(acquisitions), [acquisitions]);
  const lanes = useMemo(() => buildLanes(acquisitions), [acquisitions]);
  const gaps = useMemo(
    () => computeCoverageGaps(acquisitions, cloudCeilingPercentage),
    [acquisitions, cloudCeilingPercentage],
  );

  /** The scene each role falls back to when the operator has not moved that handle. */
  const slotSceneIdFor = useCallback(
    (role: TimelineRole) => {
      const slotRole = role === "baseline" ? "t0" : "t1";
      return investigation?.sceneSlots.find((slot) => slot.role === slotRole)?.sceneId ?? null;
    },
    [investigation],
  );

  const resolve = useCallback(
    (sceneId: string | null, role: TimelineRole): Acquisition | null => {
      const effectiveSceneId = sceneId ?? slotSceneIdFor(role);
      if (!effectiveSceneId) {
        return null;
      }
      return (
        acquisitions.find((acquisition) => acquisition.sceneId === effectiveSceneId) ?? null
      );
    },
    [acquisitions, slotSceneIdFor],
  );

  const baseline = useMemo(
    () => resolve(baselineSceneId, "baseline"),
    [baselineSceneId, resolve],
  );
  const comparison = useMemo(
    () => resolve(comparisonSceneId, "comparison"),
    [comparisonSceneId, resolve],
  );

  const assessment = useMemo(() => assessPair(baseline, comparison), [baseline, comparison]);

  const citedSceneIdSet = useMemo(() => new Set(citedSceneIds), [citedSceneIds]);

  // ── Imagery ──────────────────────────────────────────────────────────────────────────────────────
  //
  // A layer is built only for a selection the role slots do not already draw. Duplicating the T0 raster
  // under a second id would put two identical tile requests on every pan and leave the layer stack listing
  // one of them while the comparator used the other.
  const { layers, comparatorOverride } = useMemo(() => {
    if (!investigation || comparatorBinding !== "temporal") {
      // Cross-modal binding compares SAR against optical by role. The timeline keeps its selection so it
      // is still there on switching back, but it does not fight the role binding for the comparator.
      return { layers: [] as StageLayer[], comparatorOverride: null };
    }

    const built: StageLayer[] = [];

    const layerIdFor = (acquisition: Acquisition | null, role: TimelineRole): string | null => {
      if (!acquisition) {
        return null;
      }

      const slotRole = role === "baseline" ? "t0" : "t1";
      const slot = investigation.sceneSlots.find(
        (candidate) => candidate.role === slotRole && candidate.sceneId === acquisition.sceneId,
      );
      if (slot) {
        return slot.layerId;
      }

      if (!acquisition.tiles) {
        // Catalogued but not tiled. Nothing can be drawn, so the side falls back to its slot rather than
        // binding the comparator to a layer that will never produce a pixel.
        return null;
      }

      const layerId = `${investigation.id}-scrub-${acquisition.sceneId}`;
      built.push({
        id: layerId,
        kind: "raster-tiles",
        renderMode: "draped",
        title: `${acquisition.sensorPlatform} · ${acquisition.capturedAt.slice(0, 10)}`,
        colorRampId: acquisition.modality === "sar" ? "sar-grayscale" : "true-color",
        opacity: 1,
        isVisible: true,
        comparatorSide: role === "baseline" ? "left" : "right",
        tileUrlTemplate: acquisition.tiles.urlTemplate,
        attribution: acquisition.tiles.attribution,
        bounds: investigation.areaOfInterest,
        minimumZoom: acquisition.tiles.minimumZoom,
        maximumZoom: acquisition.tiles.maximumZoom,
        features: [],
      });

      return layerId;
    };

    const left = layerIdFor(baseline, "baseline");
    const right = layerIdFor(comparison, "comparison");

    return { layers: built, comparatorOverride: { left, right } };
  }, [baseline, comparatorBinding, comparison, investigation]);

  // ── Selection ────────────────────────────────────────────────────────────────────────────────────
  const select = useCallback(
    (role: TimelineRole, acquisition: Acquisition) => {
      setTimelineSelection(role, acquisition.sceneId);
    },
    [setTimelineSelection],
  );

  const selectNearest = useCallback(
    (role: TimelineRole, position: number) => {
      if (!domain) {
        return;
      }
      const candidate = nearestAcquisition(acquisitions, position, domain, {
        onlySelectable: true,
        maximumCloudPercentage: cloudCeilingPercentage,
      });
      if (candidate) {
        setTimelineSelection(role, candidate.sceneId);
      }
    },
    [acquisitions, cloudCeilingPercentage, domain, setTimelineSelection],
  );

  const step = useCallback(
    (role: TimelineRole, direction: 1 | -1) => {
      const current = role === "baseline" ? baseline : comparison;
      const next = stepAcquisition(
        acquisitions,
        current?.sceneId ?? null,
        direction,
        cloudCeilingPercentage,
      );
      if (next) {
        setTimelineSelection(role, next.sceneId);
      }
    },
    [acquisitions, baseline, cloudCeilingPercentage, comparison, setTimelineSelection],
  );

  // ── Play-through ─────────────────────────────────────────────────────────────────────────────────
  //
  // Self-scheduling rather than an interval, because the next step waits for the imagery of the current
  // one. A fixed clock shorter than the tile fetch makes the fastest speed show the least: the archive
  // advances past frames the operator never sees, which is the opposite of what a faster setting is for.
  useEffect(() => {
    if (!isPlaying) {
      return;
    }

    const usableCount = acquisitions.filter((acquisition) =>
      isSelectable(acquisition, cloudCeilingPercentage),
    ).length;

    if (usableCount < 2) {
      // Nothing to step through. Stopping is honest; leaving a play button lit over a static scene is not.
      setPlaying(false);
      return;
    }

    const dwellMs = TIMELINE_PLAYBACK.dwellMs / Math.max(0.25, playbackRate);
    let timerId = 0;
    let isCancelled = false;
    let waitedMs = 0;

    const advance = () => {
      if (isCancelled) {
        return;
      }

      const sceneLayers = useGeoStageStore.getState().handle?.sceneLayers;
      if (
        sceneLayers &&
        !sceneLayers.isSettled() &&
        waitedMs < TIMELINE_PLAYBACK.maximumSettleWaitMs
      ) {
        // Still loading. Hold this frame rather than skipping it — but only up to the cap, so a dead tile
        // service degrades playback to the fixed clock instead of stopping it.
        waitedMs += TIMELINE_PLAYBACK.settlePollMs;
        timerId = window.setTimeout(advance, TIMELINE_PLAYBACK.settlePollMs);
        return;
      }

      waitedMs = 0;
      const store = useInvestigationStore.getState();
      const currentSceneId = store.timelineComparisonSceneId ?? slotSceneIdFor("comparison");
      const next = stepAcquisition(acquisitions, currentSceneId, 1, cloudCeilingPercentage);
      if (next) {
        store.setTimelineSelection("comparison", next.sceneId);
      }

      timerId = window.setTimeout(advance, dwellMs);
    };

    timerId = window.setTimeout(advance, dwellMs);

    return () => {
      isCancelled = true;
      window.clearTimeout(timerId);
    };
  }, [acquisitions, cloudCeilingPercentage, isPlaying, playbackRate, setPlaying, slotSceneIdFor]);

  return {
    lanes,
    domain,
    gaps,
    baseline,
    comparison,
    assessment,
    cloudCeilingPercentage,
    isPlaying,
    playbackRate,
    citedSceneIds: citedSceneIdSet,
    layers,
    comparatorOverride,
    select,
    selectNearest,
    step,
    applyPair: setTimelinePair,
    setPlaying,
    setScrubbing,
    setPlaybackRate,
    setCloudCeiling,
  };
}

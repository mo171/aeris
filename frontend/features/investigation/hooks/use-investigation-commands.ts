// features/investigation/hooks/use-investigation-commands.ts — every workspace action, as an agent-invocable command.
//
// what  : Registers the `investigation.*` commands: asking, layers, the comparator, the spotlight,
//         volumetric mode, region drawing, the autonomous macro, present mode, the trace and the report.
// where : Called once by InvestigationScreen; unregistered automatically when it unmounts.
// how   : Every affordance on this surface dispatches through here rather than calling a handler
//         directly. Three things fall out of that, and all three are the reason the bus exists.
//
//         First, the autonomous investigation is not a special code path — it is a sequence of these same
//         commands, so the machine literally presses the buttons a human would and the two modes cannot
//         drift apart.
//
//         Second, voice needs no new UI at all. The vocabulary IS this list: "sweep", "show me the
//         change", "zoom to the biggest change", "why", "generate a report" each map to one command, so
//         the speech layer is an adapter from intent to dispatchCommand and nothing more.
//
//         Third, listCommandDescriptors already serialises this registry to JSON Schema, so the agent
//         layer consumes the workspace as tools with no rewiring.
//
//         Commands that take parameters are hidden from the palette — a palette cannot collect arguments —
//         but stay fully agent-invocable. Shortcut-bearing commands must take no parameters, because the
//         keyboard layer dispatches them with none.

"use client";

import {
  Box,
  Building2,
  CalendarClock,
  Crosshair,
  Eye,
  FileText,
  Layers,
  ListTree,
  Mountain,
  Play,
  Presentation,
  Search,
  SplitSquareHorizontal,
  Target,
} from "lucide-react";
import { useMemo } from "react";
import { z } from "zod";

import { defineCommand, useRegisterCommands } from "@/lib/command-bus";
import { COMMAND_IDS } from "@/lib/constants/commands";
import { INVESTIGATION_CAMERA } from "@/lib/constants/investigation";
import { useGeoStageStore } from "@/store/geo-stage-store";

import {
  computeDomain,
  nearestAcquisition,
  positionForTime,
  stepAcquisition,
} from "../lib/timeline-geometry";
import { useInvestigationStore } from "../store/investigation-store";
import type { EvidenceItem } from "../types/evidence.types";
import type { Acquisition } from "../types/investigation.types";

interface InvestigationCommandOptions {
  ask: (query: string) => void;
  /** The archive over this area, so temporal commands resolve a date to an observation that exists. */
  acquisitions: Acquisition[];
  /** Opens the autonomous plan for review. Nothing executes until the operator approves it. */
  prepareAutonomous: (fromClaimId: string) => void;
  /** Evidence by id, so focus commands frame real geometry rather than guessing at it. */
  evidenceById: Record<string, EvidenceItem>;
  /** The investigation extent, so resetting the view always has somewhere definite to return to. */
  areaOfInterest: { west: number; south: number; east: number; north: number } | null;
}

export function useInvestigationCommands({
  ask,
  acquisitions,
  prepareAutonomous,
  evidenceById,
  areaOfInterest,
}: InvestigationCommandOptions): void {
  const commands = useMemo(() => {
    const store = () => useInvestigationStore.getState();
    const stage = () => useGeoStageStore.getState().handle;

    /** Frames whichever evidence carries the highest magnitude — "the biggest change". */
    const focusStrongestEvidence = () => {
      const ranked = Object.values(evidenceById).sort(
        (left, right) => right.magnitude - left.magnitude,
      );
      const strongest = ranked[0];
      if (!strongest) {
        return;
      }

      stage()?.sceneLayers.setSpotlight(strongest.featureIds);
      // Framing follows the spotlight: naming the biggest change without going to look at it would be
      // half an answer.
      if (areaOfInterest) {
        stage()?.camera.flyToBoundingBox(areaOfInterest, {
          durationMs: INVESTIGATION_CAMERA.localFlightDurationSeconds * 1000,
        });
      }
    };

    return [
      defineCommand({
        id: COMMAND_IDS.investigation.ask,
        title: "Ask AERIS about this scene",
        description:
          "Run an analysis on the open investigation. If a region has been drawn, the question is scoped to it.",
        group: "investigation",
        keywords: ["question", "analyse", "query"],
        icon: Search,
        paramsSchema: z.object({ query: z.string().min(1) }),
        handler: ({ query }) => ask(query),
        isPaletteVisible: false,
      }),

      // ── Layers ─────────────────────────────────────────────────────────────────────────────────
      defineCommand({
        id: COMMAND_IDS.investigation.toggleLayer,
        title: "Show or hide an evidence layer",
        description:
          "Toggle one layer in the evidence stack. Omit isVisible to flip whatever it currently is.",
        group: "investigation",
        icon: Layers,
        paramsSchema: z.object({
          layerId: z.string().min(1),
          isVisible: z.boolean().optional(),
        }),
        handler: ({ layerId, isVisible }) => {
          const current = store().layerVisibilityOverrides[layerId] ?? true;
          store().setLayerVisibility(layerId, isVisible ?? !current);
        },
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.setLayerOpacity,
        title: "Set an evidence layer opacity",
        description: "Set one layer opacity between 0 and 1.",
        group: "investigation",
        icon: Layers,
        paramsSchema: z.object({
          layerId: z.string().min(1),
          opacity: z.number().min(0).max(1),
        }),
        handler: ({ layerId, opacity }) => store().setLayerOpacity(layerId, opacity),
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.soloLayer,
        title: "Solo an evidence layer",
        description: "Show only this layer and hide the rest. Running it again restores the stack.",
        group: "investigation",
        icon: Eye,
        paramsSchema: z.object({ layerId: z.string().min(1) }),
        handler: ({ layerId }) => store().toggleSoloLayer(layerId),
        isPaletteVisible: false,
      }),

      // ── Comparator ─────────────────────────────────────────────────────────────────────────────
      defineCommand({
        id: COMMAND_IDS.investigation.setSplitPosition,
        title: "Move the before/after handle",
        description:
          "Position the comparator handle. 0 shows the right scene everywhere, 1 shows the left scene everywhere.",
        group: "investigation",
        icon: SplitSquareHorizontal,
        paramsSchema: z.object({ position: z.number().min(0).max(1) }),
        handler: ({ position }) => stage()?.comparator.setPosition(position),
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.sweepSplit,
        title: "Sweep before to after",
        description:
          "Animate the comparator across the scene, revealing the later observation under the handle.",
        group: "investigation",
        keywords: ["compare", "reveal", "wipe", "before after"],
        icon: SplitSquareHorizontal,
        shortcut: ["shift", "s"],
        paramsSchema: z.void(),
        handler: () => stage()?.comparator.sweep(),
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.setComparator,
        title: "Choose what the comparator compares",
        description:
          "Bind the before/after handle to the temporal pair (T0 against T1) or to the cross-modal pair (SAR against optical).",
        group: "investigation",
        icon: SplitSquareHorizontal,
        paramsSchema: z.object({ binding: z.enum(["temporal", "crossModal"]) }),
        handler: ({ binding }) => store().setComparatorBinding(binding),
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.togglePlayback,
        title: "Play the before/after loop",
        description:
          "Start or stop the automatic dissolve between the two observations, holding briefly at each end.",
        group: "investigation",
        keywords: ["animate", "loop", "timelapse"],
        icon: Play,
        shortcut: ["shift", "p"],
        paramsSchema: z.void(),
        handler: () => store().setPlaybackRunning(!store().isPlaybackRunning),
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.toggleVolumetric,
        title: "Toggle volumetric change",
        description:
          "Extrude change regions by how much changed, so the scale of the change is felt rather than read.",
        group: "investigation",
        keywords: ["3d", "extrude", "height"],
        icon: Box,
        shortcut: ["shift", "v"],
        paramsSchema: z.void(),
        handler: () => store().toggleRenderMode(),
      }),

      // ── Evidence ───────────────────────────────────────────────────────────────────────────────
      defineCommand({
        id: COMMAND_IDS.investigation.spotlightClaim,
        title: "Spotlight the evidence behind a claim",
        description:
          "Dim the scene and raise only the geometry supporting this claim, so the answer can be checked against pixels.",
        group: "investigation",
        icon: Crosshair,
        paramsSchema: z.object({ claimId: z.string().min(1) }),
        handler: ({ claimId }) => store().setSpotlightClaimId(claimId),
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.inspectFeature,
        title: "Open a feature's record",
        description:
          "Show everything known about one piece of geometry: what it is, where, how large, how confident the model was, which model drew it and which claim it supports.",
        group: "investigation",
        keywords: ["identify", "attributes", "what is this", "inspect", "detail"],
        icon: Crosshair,
        paramsSchema: z.object({
          layerId: z.string().min(1),
          featureId: z.string().min(1),
        }),
        handler: ({ layerId, featureId }) => store().setInspectedFeature({ layerId, featureId }),
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.clearSpotlight,
        title: "Clear the evidence spotlight",
        description: "Restore normal scene rendering.",
        group: "investigation",
        icon: Crosshair,
        paramsSchema: z.void(),
        handler: () => store().setSpotlightClaimId(null),
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.focusEvidence,
        title: "Zoom to the biggest change",
        description:
          "Frame the highest-magnitude piece of evidence in the investigation and spotlight it.",
        group: "investigation",
        keywords: ["largest", "biggest", "most significant"],
        icon: Target,
        shortcut: ["shift", "b"],
        paramsSchema: z.void(),
        handler: focusStrongestEvidence,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.peekArtefact,
        title: "Inspect a pipeline stage output",
        description:
          "Load the intermediate product a pipeline stage produced — a cloud mask, a registration residual, an index map — onto the scene.",
        group: "investigation",
        icon: ListTree,
        paramsSchema: z.object({ layerId: z.string().min(1) }),
        handler: ({ layerId }) => store().setArtefactLayerId(layerId),
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.clearArtefact,
        title: "Clear the inspected stage output",
        description: "Remove the temporary pipeline artefact from the scene.",
        group: "investigation",
        icon: ListTree,
        paramsSchema: z.void(),
        handler: () => store().setArtefactLayerId(null),
      }),

      // ── Geometry and measurement ───────────────────────────────────────────────────────────────
      defineCommand({
        id: COMMAND_IDS.investigation.selectDrawTool,
        title: "Pick a drawing or measurement tool",
        description:
          "Arm one of the scene tools: rectangle, polygon, freehand or circle to define an area of interest, or distance, area or bearing to measure.",
        group: "investigation",
        keywords: ["draw", "ask this region", "measure", "polygon", "box", "ruler"],
        icon: Crosshair,
        paramsSchema: z.object({
          tool: z.enum(["rectangle", "polygon", "freehand", "circle", "distance", "area", "bearing"]),
        }),
        handler: ({ tool }) => store().setActiveDrawTool(tool),
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.completeDraw,
        title: "Finish the current shape",
        description: "Close the shape being drawn and commit it.",
        group: "investigation",
        icon: Crosshair,
        paramsSchema: z.void(),
        handler: () => stage()?.draw.complete(),
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.undoVertex,
        title: "Undo the last point",
        description: "Remove the most recently placed vertex from the shape being drawn.",
        group: "investigation",
        icon: Crosshair,
        paramsSchema: z.void(),
        handler: () => stage()?.draw.undoVertex(),
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.cancelDraw,
        title: "Cancel drawing",
        description: "Disarm the active tool and return the pointer to the camera.",
        group: "investigation",
        icon: Crosshair,
        paramsSchema: z.void(),
        handler: () => store().setActiveDrawTool(null),
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.clearRegions,
        title: "Clear drawn regions",
        description: "Remove every drawn area of interest and measurement from the scene.",
        group: "investigation",
        icon: Crosshair,
        paramsSchema: z.void(),
        handler: () => stage()?.draw.clearAll(),
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.setProjection,
        title: "Switch the map projection",
        description:
          "Show the scene as a 3D globe, a flat 2D map for precise digitising, or the 2.5D view that keeps height on a flat map.",
        group: "investigation",
        keywords: ["2d", "3d", "flat", "nadir", "map"],
        icon: Box,
        paramsSchema: z.object({ projection: z.enum(["3D", "2D", "columbus"]) }),
        handler: ({ projection }) => store().setProjection(projection),
        isPaletteVisible: false,
      }),

      // ── Aiming the camera ──────────────────────────────────────────────────────────────────────
      //
      // Tilt and orbit are commands, not just buttons, for the same reason everything else here is: the
      // autonomous run narrates by moving the camera, and "look at it from the side" has to reach exactly
      // the control an operator would press.
      defineCommand({
        id: COMMAND_IDS.investigation.setTilt,
        title: "Set the viewing angle",
        description:
          "Tilt the camera between straight down (-90) and a low oblique. Pivots around what the scene is framing, so the distance to it does not change.",
        group: "investigation",
        keywords: ["tilt", "pitch", "oblique", "nadir", "angle", "3d", "look from the side"],
        icon: Mountain,
        paramsSchema: z.object({ pitchDegrees: z.number().min(-90).max(-5) }),
        handler: ({ pitchDegrees }) => stage()?.camera.orient({ pitchDegrees }),
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.orbit,
        title: "Orbit around the area of interest",
        description:
          "Swing the camera around whatever the scene is framing by a number of degrees. Negative goes anticlockwise.",
        group: "investigation",
        keywords: ["rotate", "spin", "around", "orbit", "other side"],
        icon: Mountain,
        paramsSchema: z.object({ deltaDegrees: z.number().min(-360).max(360) }),
        handler: ({ deltaDegrees }) => stage()?.camera.orbitByDegrees(deltaDegrees),
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.toggleBuildings,
        title: "Show or hide building massing",
        description:
          "Put three-dimensional buildings on the scene. In a city almost none of the vertical information is in the terrain, so this is what makes the scene read as a place rather than a photograph.",
        group: "investigation",
        keywords: ["buildings", "3d", "massing", "height", "depth", "osm"],
        icon: Building2,
        paramsSchema: z.object({ isVisible: z.boolean().optional() }),
        handler: ({ isVisible }) =>
          store().setBuildingMassing(isVisible ?? !store().hasBuildingMassing),
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.setTerrainExaggeration,
        title: "Exaggerate terrain relief",
        description:
          "Multiply terrain height so relief is legible over nearly flat ground. Scales height only — every horizontal position and measured area is unchanged.",
        group: "investigation",
        keywords: ["exaggeration", "relief", "terrain", "height", "vertical"],
        icon: Mountain,
        paramsSchema: z.object({ factor: z.number().min(1).max(8) }),
        handler: ({ factor }) => store().setTerrainExaggeration(factor),
        isPaletteVisible: false,
      }),

      // ── The temporal selection ─────────────────────────────────────────────────────────────────
      //
      // The pair is the one input that determines the answer, so it is agent-invocable like everything
      // else. "Compare against 2019" is a legitimate instruction, and it has to reach the same selection
      // a drag would — otherwise the machine and the operator are working two different timelines.
      defineCommand({
        id: COMMAND_IDS.investigation.scrubTo,
        title: "Compare against a date",
        description:
          "Move one end of the comparison to the acquisition nearest a date. Snaps to a real observation, because a date with no pass behind it cannot be shown.",
        group: "investigation",
        keywords: ["timeline", "date", "scrub", "when", "compare against"],
        icon: CalendarClock,
        paramsSchema: z.object({
          date: z.string().min(4),
          end: z.enum(["baseline", "comparison"]).optional(),
        }),
        handler: ({ date, end }) => {
          const targetMs = Date.parse(date);
          if (!Number.isFinite(targetMs)) {
            return;
          }

          const domain = computeDomain(acquisitions);
          if (!domain) {
            return;
          }

          const match = nearestAcquisition(
            acquisitions,
            positionForTime(targetMs, domain),
            domain,
            {
              onlySelectable: true,
              maximumCloudPercentage: store().timelineCloudCeilingPercentage,
            },
          );

          if (match) {
            store().setTimelineSelection(end ?? "comparison", match.sceneId);
          }
        },
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.stepAcquisition,
        title: "Step to the next or previous acquisition",
        description:
          "Move one end of the comparison by one observation along the archive, skipping anything the cloud ceiling has ruled out.",
        group: "investigation",
        keywords: ["next", "previous", "advance", "timeline"],
        icon: CalendarClock,
        paramsSchema: z.object({
          direction: z.enum(["next", "previous"]),
          end: z.enum(["baseline", "comparison"]).optional(),
        }),
        handler: ({ direction, end }) => {
          const role = end ?? "comparison";
          const currentSceneId =
            role === "baseline" ? store().timelineBaselineSceneId : store().timelineComparisonSceneId;

          const next = stepAcquisition(
            acquisitions,
            currentSceneId,
            direction === "next" ? 1 : -1,
            store().timelineCloudCeilingPercentage,
          );

          if (next) {
            store().setTimelineSelection(role, next.sceneId);
          }
        },
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.toggleTimelinePlayback,
        title: "Play through the archive",
        description:
          "Step the comparison through every usable acquisition in turn, so the whole series is seen rather than one pair from it.",
        group: "investigation",
        keywords: ["timelapse", "series", "history", "play"],
        icon: CalendarClock,
        paramsSchema: z.void(),
        handler: () => store().setTimelinePlaying(!store().isTimelinePlaying),
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.setCloudCeiling,
        title: "Set the cloud ceiling",
        description:
          "Optical acquisitions above this percentage stay visible on the timeline but stop being offered as analysis inputs.",
        group: "investigation",
        icon: CalendarClock,
        paramsSchema: z.object({ percentage: z.number().min(0).max(100) }),
        handler: ({ percentage }) => store().setTimelineCloudCeiling(percentage),
        isPaletteVisible: false,
      }),

      // ── Autonomous, present, trace, report ─────────────────────────────────────────────────────
      defineCommand({
        id: COMMAND_IDS.investigation.runAutonomous,
        title: "Investigate further",
        description:
          "Ask AERIS to plan a multi-step drill-down from the current answer. The plan is shown for review before anything runs.",
        group: "investigation",
        keywords: ["autonomous", "drill down", "deeper", "why"],
        icon: Search,
        paramsSchema: z.object({ claimId: z.string().min(1).optional() }),
        handler: ({ claimId }) => {
          const fallbackClaimId = store().runs.at(-1)?.claimIds[0];
          const targetClaimId = claimId ?? fallbackClaimId;
          if (targetClaimId) {
            prepareAutonomous(targetClaimId);
          }
        },
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.togglePresentMode,
        title: "Present mode",
        description:
          "Hide every panel and slowly orbit the area of interest. For showing the result rather than working on it.",
        group: "investigation",
        keywords: ["fullscreen", "demo", "focus"],
        icon: Presentation,
        shortcut: ["shift", "f"],
        paramsSchema: z.void(),
        handler: () => store().togglePresentMode(),
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.toggleTrace,
        title: "Show the execution trace",
        description:
          "Expand or collapse the pipeline spine, where each stage can be opened to inspect what it produced.",
        group: "investigation",
        keywords: ["pipeline", "provenance", "stages"],
        icon: ListTree,
        shortcut: ["shift", "t"],
        paramsSchema: z.void(),
        handler: () => store().toggleTraceExpanded(),
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.openReport,
        title: "Generate an intelligence report",
        description:
          "Assemble the investigation into a report with its trace id embedded, exportable as PDF, JSON or GeoJSON.",
        group: "investigation",
        keywords: ["export", "pdf", "document"],
        icon: FileText,
        paramsSchema: z.void(),
        handler: () => store().setReportOpen(true),
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.resetView,
        title: "Reset the scene view",
        description: "Return the camera to the framing of the whole area of interest.",
        group: "investigation",
        icon: Target,
        paramsSchema: z.void(),
        handler: () => {
          if (areaOfInterest) {
            stage()?.camera.flyToBoundingBox(areaOfInterest, {
              durationMs: INVESTIGATION_CAMERA.localFlightDurationSeconds * 1000,
            });
          }
        },
      }),
    ];
  }, [acquisitions, areaOfInterest, ask, evidenceById, prepareAutonomous]);

  useRegisterCommands(commands);
}

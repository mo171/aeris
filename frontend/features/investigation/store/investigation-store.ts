// features/investigation/store/investigation-store.ts — shared state inside the Investigation Workspace.
//
// what  : View state for the workspace — comparator binding, render mode, layer overrides, spotlight,
//         artefact peek, region draw, present mode — plus the fold of the in-flight analysis run.
// where : Read by every zone of the workspace: header, inputs panel, viewer bindings, answer panel and
//         the execution spine. Written by the run hook and by the investigation commands.
// how   : Two categories live here, and the line between them matters.
//
//         VIEW STATE — split binding, layer opacity, spotlight, draw mode — changes at pointer rate while
//         an operator drags, and must never touch the query cache. It is not server data and will not
//         survive a reload, which is correct: a shared URL restores the investigation and its camera, not
//         which layer someone happened to have hidden.
//
//         RUN STATE — trace steps, the streaming answer, confidence — is the client-side fold of an
//         in-flight operation, not cached server data. Keeping it here rather than in a hook is what lets
//         the answer panel and the execution spine, which sit at opposite ends of the screen, read the
//         same run without either one prop-drilling through the screen component.
//
//         The evidence GRAPH is deliberately NOT here. It is server state, so it lives in the query cache
//         and the stream mutates it incrementally — which is the rule for realtime data in this codebase.
//
//         Split position is also deliberately absent: it changes every frame during a sweep, and a React
//         render per frame would spend exactly the budget this page exists to showcase. The stage owns it
//         and the DOM handle subscribes.

import { create } from "zustand";

import type {
  StageBuildingMode,
  StageDrawnRegion,
  StageDrawTool,
  StageProjection,
} from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";
import type { Polarisation, SensorId } from "@/lib/constants/cross-modal";
import { INVESTIGATION_LIMITS, SCENE_RELIEF } from "@/lib/constants/investigation";
import type { BuildingStyleId } from "@/lib/constants/overlays";
import { TIMELINE_PLAYBACK, TIMELINE_QUERY } from "@/lib/constants/timeline";

import type {
  AnalysisPlan,
  AnalysisRun,
  AnalysisTraceStep,
} from "../types/analysis.types";
import type { InsufficientEvidence } from "../types/evidence.types";
import type { WorkspaceMode as InvestigationMode } from "../types/investigation.types";
import type { LayerRenderMode } from "../types/layer.types";

/**
 * The cross-modal lens — a second READING of the evidence already in the workspace.
 *
 * It lives in this store rather than in a component because three separate subtrees act on it: the Toolbox
 * row and the header button toggle it, the left panel renders the sensor cards from it, and the stage
 * binding composes a different layer stack while it is on. It is also reachable from the command bus, and
 * commands dispatch into stores rather than into a component's useState.
 *
 * `displacedBinding` is the load-bearing field. Turning the lens on forces the comparator to radar-left /
 * optical-right; without remembering what it replaced, turning the lens OFF would leave the split wrong
 * and the operator with no way to know why.
 */
export interface CrossModalLensState {
  isActive: boolean;
  /** Which sensor the stage is showing alone, or null for the split. Never re-runs anything. */
  soloSensor: SensorId | null;
  /** The agreement row under inspection. Drives the scene spotlight across both sensors' features. */
  selectedRowId: string | null;
  polarisation: Polarisation;
  /** The comparator binding the lens displaced, restored when it closes. */
  displacedBinding: InvestigationMode | null;
}

const CLOSED_CROSS_MODAL_LENS: CrossModalLensState = {
  isActive: false,
  soloSensor: null,
  selectedRowId: null,
  polarisation: "VV",
  displacedBinding: null,
};

interface InvestigationState {
  investigationId: string | null;

  // ── Viewer ───────────────────────────────────────────────────────────────────────────────────────
  comparatorBinding: InvestigationMode;
  renderMode: LayerRenderMode;
  /** Globe, flat map, or the 2.5D middle ground. Lives here so a command and the toggle agree. */
  projection: StageProjection;
  /**
   * How the built environment renders, and how much terrain height is exaggerated.
   *
   * Here rather than read back off the stage for the same reason projection is: a command, a button and
   * the renderer must not each hold their own opinion about what is on screen. It also keeps the control
   * out of the "mirror external state into React on mount" pattern, which is a stale-UI bug waiting.
   */
  buildingMode: StageBuildingMode;
  /** What the massing's colour encodes: nothing, building type, or height band. */
  buildingStyleId: BuildingStyleId;
  terrainExaggeration: number;
  isPlaybackRunning: boolean;
  isPresentMode: boolean;

  /** Cross-modal reading of the same evidence. See CrossModalLensState. */
  crossModalLens: CrossModalLensState;

  /**
   * Visibility and opacity for the reference catalogue — terrain shading, boundaries, roads.
   *
   * Kept apart from the evidence overrides below on purpose. Reference layers are context nobody asserted;
   * evidence layers are model output that must carry provenance. One map for both would let a boundary be
   * handled like a finding, which is the confusion the whole separation exists to prevent.
   */
  referenceLayerState: Record<string, { isVisible: boolean; opacity: number }>;

  /** Operator overrides on top of what the backend declared. Absent means "use the descriptor". */
  layerVisibilityOverrides: Record<string, boolean>;
  layerOpacityOverrides: Record<string, number>;
  soloLayerId: string | null;

  /** The claim currently under the pointer. Drives the scene spotlight. */
  spotlightClaimId: string | null;
  /** A trace step's intermediate product, temporarily added to the scene. */
  artefactLayerId: string | null;
  /**
   * The feature the operator clicked, so its full record can be shown.
   *
   * Separate from the spotlight: the spotlight answers "which geometry supports this claim" and points
   * from the answer to the scene, while this answers "what IS this thing" and points the other way. The
   * workspace could previously highlight a clicked polygon and then say nothing whatsoever about it,
   * which is the one verb every GIS has and this did not.
   */
  inspectedFeature: { layerId: string; featureId: string } | null;

  // ── The temporal selection ───────────────────────────────────────────────────────────────────────
  //
  // Which two observations the comparator is showing, chosen on the timeline. Scene ids rather than
  // acquisition ids because that is what the layer stack, the pop-out inspector and the backend all key
  // on — an acquisition id would need translating at three call sites.
  //
  // These are the whole reason the timeline exists: the pair is the single input that determines the
  // answer, and it now lives in one place that a drag, a keystroke, a command and a backend suggestion
  // all write to. Null means "fall back to whichever scene occupies that role", which is the state on
  // arrival, before the operator has moved anything.
  timelineBaselineSceneId: string | null;
  timelineComparisonSceneId: string | null;
  /** Stepping through the archive one acquisition at a time. Distinct from the comparator's dissolve. */
  isTimelinePlaying: boolean;
  /**
   * True while a handle is being dragged.
   *
   * Held here rather than locally because it changes how the RENDERER behaves, not just the control: the
   * raster cross-fade shortens while a scrub is in progress so ten steps in one drag do not read as ten
   * separate loads. The stage binding is the only thing that acts on it.
   */
  isTimelineScrubbing: boolean;
  timelinePlaybackRate: number;
  /** Optical acquisitions above this are shown on the timeline but cannot be selected as inputs. */
  timelineCloudCeilingPercentage: number;

  // ── Drawing and measurement ──────────────────────────────────────────────────────────────────────
  /** Which tool the pointer is currently armed with. Null means the camera owns the pointer. */
  activeDrawTool: StageDrawTool | null;
  /** Every committed region. An analyst comparing two sites needs both on screen, not one at a time. */
  drawnRegions: StageDrawnRegion[];
  /** Which region scopes the next question. Null means the whole area of interest. */
  activeRegionId: string | null;

  // ── Panels ───────────────────────────────────────────────────────────────────────────────────────
  isTraceExpanded: boolean;
  isReportOpen: boolean;
  activePlan: AnalysisPlan | null;

  // ── The analysis run ─────────────────────────────────────────────────────────────────────────────
  runs: AnalysisRun[];
  isRunning: boolean;
  /**
   * Which past run the answer surface is showing. Null follows the newest.
   *
   * Without this a second question made the first answer unrecoverable — the panel always rendered
   * `runs.at(-1)` and the history could only RE-ASK, which reruns the models and may not even reproduce
   * the same numbers. For a product whose whole claim is auditability, an answer you cannot go back to is
   * not audited.
   */
  selectedRunId: string | null;

  // ── Actions ──────────────────────────────────────────────────────────────────────────────────────
  enterInvestigation: (investigationId: string, mode: InvestigationMode) => void;
  leaveInvestigation: () => void;

  setComparatorBinding: (binding: InvestigationMode) => void;
  setRenderMode: (renderMode: LayerRenderMode) => void;
  toggleRenderMode: () => void;
  setProjection: (projection: StageProjection) => void;
  setBuildingMode: (mode: StageBuildingMode) => void;
  setBuildingStyle: (styleId: BuildingStyleId) => void;
  setTerrainExaggeration: (factor: number) => void;
  setPlaybackRunning: (isRunning: boolean) => void;
  togglePresentMode: () => void;

  setCrossModalLensActive: (isActive: boolean) => void;
  setCrossModalSoloSensor: (sensor: SensorId | null) => void;
  selectAgreementRow: (rowId: string | null) => void;
  setCrossModalPolarisation: (polarisation: Polarisation) => void;

  setReferenceLayerVisibility: (layerId: string, isVisible: boolean) => void;
  setReferenceLayerOpacity: (layerId: string, opacity: number) => void;

  setLayerVisibility: (layerId: string, isVisible: boolean) => void;
  setLayerOpacity: (layerId: string, opacity: number) => void;
  toggleSoloLayer: (layerId: string) => void;

  setSpotlightClaimId: (claimId: string | null) => void;
  setArtefactLayerId: (layerId: string | null) => void;
  setInspectedFeature: (target: { layerId: string; featureId: string } | null) => void;

  setTimelineSelection: (role: "baseline" | "comparison", sceneId: string | null) => void;
  /** Applies a pair in one write, so a recommendation cannot land as two separate scene changes. */
  setTimelinePair: (baselineSceneId: string, comparisonSceneId: string) => void;
  setTimelinePlaying: (isPlaying: boolean) => void;
  setTimelineScrubbing: (isScrubbing: boolean) => void;
  setTimelinePlaybackRate: (rate: number) => void;
  setTimelineCloudCeiling: (percentage: number) => void;

  setActiveDrawTool: (tool: StageDrawTool | null) => void;
  setDrawnRegions: (regions: readonly StageDrawnRegion[]) => void;
  setActiveRegionId: (regionId: string | null) => void;

  toggleTraceExpanded: (isExpanded?: boolean) => void;
  setReportOpen: (isOpen: boolean) => void;
  setActivePlan: (plan: AnalysisPlan | null) => void;
  togglePlanStep: (stepId: string) => void;

  selectRun: (runId: string | null) => void;
  startRun: (run: AnalysisRun) => void;
  upsertTraceStep: (runId: string, step: AnalysisTraceStep) => void;
  appendAnswerText: (runId: string, text: string) => void;
  attachClaim: (runId: string, claimId: string) => void;
  completeRun: (
    runId: string,
    result: {
      confidence: number | null;
      insufficientEvidence: InsufficientEvidence | null;
      totalDurationMs: number;
    },
  ) => void;
  failRun: (runId: string, message: string) => void;
  cancelRun: (runId: string) => void;
}

/** Applied to every run update so a malfunctioning stream cannot grow the trace without bound. */
function boundTrace(steps: AnalysisTraceStep[]): AnalysisTraceStep[] {
  return steps.length <= INVESTIGATION_LIMITS.maximumTraceSteps
    ? steps
    : steps.slice(-INVESTIGATION_LIMITS.maximumTraceSteps);
}

function updateRun(
  runs: AnalysisRun[],
  runId: string,
  change: (run: AnalysisRun) => AnalysisRun,
): AnalysisRun[] {
  return runs.map((run) => (run.id === runId ? change(run) : run));
}

export const useInvestigationStore = create<InvestigationState>((set) => ({
  investigationId: null,

  comparatorBinding: "temporal",
  renderMode: "draped",
  projection: "3D",
  buildingMode: SCENE_RELIEF.defaultBuildingMode,
  buildingStyleId: "uniform" as BuildingStyleId,
  terrainExaggeration: SCENE_RELIEF.defaultTerrainExaggeration,
  isPlaybackRunning: false,
  isPresentMode: false,

  crossModalLens: CLOSED_CROSS_MODAL_LENS,

  referenceLayerState: {},
  layerVisibilityOverrides: {},
  layerOpacityOverrides: {},
  soloLayerId: null,

  spotlightClaimId: null,
  artefactLayerId: null,
  inspectedFeature: null,

  timelineBaselineSceneId: null,
  timelineComparisonSceneId: null,
  isTimelinePlaying: false,
  isTimelineScrubbing: false,
  timelinePlaybackRate: TIMELINE_PLAYBACK.defaultRate,
  timelineCloudCeilingPercentage: TIMELINE_QUERY.defaultMaximumCloudPercentage,

  activeDrawTool: null,
  drawnRegions: [],
  activeRegionId: null,

  isTraceExpanded: false,
  isReportOpen: false,
  activePlan: null,

  runs: [],
  isRunning: false,
  selectedRunId: null,

  // Entering resets everything view-scoped. Carrying one investigation's hidden layers into the next
  // would make the workspace feel haunted.
  enterInvestigation: (investigationId, mode) =>
    set({
      investigationId,
      comparatorBinding: mode,
      renderMode: "draped",
      projection: "3D",
      buildingMode: SCENE_RELIEF.defaultBuildingMode,
      buildingStyleId: "uniform",
      terrainExaggeration: SCENE_RELIEF.defaultTerrainExaggeration,
      isPlaybackRunning: false,
      isPresentMode: false,
      crossModalLens: CLOSED_CROSS_MODAL_LENS,
      referenceLayerState: {},
      layerVisibilityOverrides: {},
      layerOpacityOverrides: {},
      soloLayerId: null,
      spotlightClaimId: null,
      artefactLayerId: null,
      inspectedFeature: null,
      timelineBaselineSceneId: null,
      timelineComparisonSceneId: null,
      isTimelinePlaying: false,
      isTimelineScrubbing: false,
      timelinePlaybackRate: TIMELINE_PLAYBACK.defaultRate,
      timelineCloudCeilingPercentage: TIMELINE_QUERY.defaultMaximumCloudPercentage,
      activeDrawTool: null,
      drawnRegions: [],
      activeRegionId: null,
      isTraceExpanded: false,
      isReportOpen: false,
      activePlan: null,
      runs: [],
      isRunning: false,
      selectedRunId: null,
    }),

  leaveInvestigation: () =>
    set({
      investigationId: null,
      runs: [],
      isRunning: false,
      selectedRunId: null,
      spotlightClaimId: null,
      artefactLayerId: null,
      inspectedFeature: null,
      timelineBaselineSceneId: null,
      timelineComparisonSceneId: null,
      isTimelinePlaying: false,
      isTimelineScrubbing: false,
      drawnRegions: [],
      activeRegionId: null,
      activeDrawTool: null,
      isPresentMode: false,
      crossModalLens: CLOSED_CROSS_MODAL_LENS,
    }),

  setComparatorBinding: (comparatorBinding) => set({ comparatorBinding }),
  setRenderMode: (renderMode) => set({ renderMode }),
  toggleRenderMode: () =>
    set((state) => ({ renderMode: state.renderMode === "draped" ? "extruded" : "draped" })),
  setProjection: (projection) => set({ projection }),
  setBuildingMode: (buildingMode) => set({ buildingMode }),
  // Style is remembered across a mode change: an operator who chose height bands, switched to flat to
  // read the imagery, then switched massing back on expects their banding still there.
  setBuildingStyle: (buildingStyleId) => set({ buildingStyleId }),
  setTerrainExaggeration: (terrainExaggeration) => set({ terrainExaggeration }),
  setPlaybackRunning: (isPlaybackRunning) => set({ isPlaybackRunning }),
  togglePresentMode: () => set((state) => ({ isPresentMode: !state.isPresentMode })),

  // Turning the lens on takes the comparator with it and remembers what it took, so closing the lens puts
  // the operator back exactly where they were rather than leaving a radar/optical split behind on a
  // temporal investigation. Selection resets on close because a row id from one reading means nothing in
  // the next — the same rule enterInvestigation follows for everything else view-scoped.
  setCrossModalLensActive: (isActive) =>
    set((state) => {
      if (isActive === state.crossModalLens.isActive) {
        return {};
      }

      if (isActive) {
        return {
          comparatorBinding: "crossModal" as InvestigationMode,
          crossModalLens: {
            ...state.crossModalLens,
            isActive: true,
            displacedBinding: state.comparatorBinding,
          },
        };
      }

      return {
        comparatorBinding: state.crossModalLens.displacedBinding ?? state.comparatorBinding,
        crossModalLens: CLOSED_CROSS_MODAL_LENS,
      };
    }),

  setCrossModalSoloSensor: (soloSensor) =>
    set((state) => ({ crossModalLens: { ...state.crossModalLens, soloSensor } })),

  selectAgreementRow: (rowId) =>
    set((state) => ({
      crossModalLens: {
        ...state.crossModalLens,
        selectedRowId: state.crossModalLens.selectedRowId === rowId ? null : rowId,
      },
    })),

  setCrossModalPolarisation: (polarisation) =>
    set((state) => ({ crossModalLens: { ...state.crossModalLens, polarisation } })),

  setReferenceLayerVisibility: (layerId, isVisible) =>
    set((state) => ({
      referenceLayerState: {
        ...state.referenceLayerState,
        [layerId]: {
          opacity: state.referenceLayerState[layerId]?.opacity ?? 1,
          isVisible,
        },
      },
    })),

  setReferenceLayerOpacity: (layerId, opacity) =>
    set((state) => ({
      referenceLayerState: {
        ...state.referenceLayerState,
        [layerId]: {
          isVisible: state.referenceLayerState[layerId]?.isVisible ?? true,
          opacity,
        },
      },
    })),

  setLayerVisibility: (layerId, isVisible) =>
    set((state) => ({
      layerVisibilityOverrides: { ...state.layerVisibilityOverrides, [layerId]: isVisible },
      // Hiding or showing a layer by hand is an explicit statement about what should be on screen, so it
      // ends any solo the operator had going rather than silently fighting it.
      soloLayerId: null,
    })),

  setLayerOpacity: (layerId, opacity) =>
    set((state) => ({
      layerOpacityOverrides: { ...state.layerOpacityOverrides, [layerId]: opacity },
    })),

  toggleSoloLayer: (layerId) =>
    set((state) => ({ soloLayerId: state.soloLayerId === layerId ? null : layerId })),

  setSpotlightClaimId: (spotlightClaimId) => set({ spotlightClaimId }),
  setArtefactLayerId: (artefactLayerId) => set({ artefactLayerId }),
  setInspectedFeature: (inspectedFeature) => set({ inspectedFeature }),

  setTimelineSelection: (role, sceneId) =>
    set(
      role === "baseline"
        ? { timelineBaselineSceneId: sceneId }
        : { timelineComparisonSceneId: sceneId },
    ),

  setTimelinePair: (timelineBaselineSceneId, timelineComparisonSceneId) =>
    set({ timelineBaselineSceneId, timelineComparisonSceneId }),

  setTimelinePlaying: (isTimelinePlaying) => set({ isTimelinePlaying }),
  setTimelineScrubbing: (isTimelineScrubbing) => set({ isTimelineScrubbing }),
  setTimelinePlaybackRate: (timelinePlaybackRate) => set({ timelinePlaybackRate }),

  // Raising the ceiling only widens what is selectable, so it cannot invalidate a selection. Lowering it
  // can, and deliberately does not clear one: an operator who has explicitly chosen a cloudy scene has
  // made a decision, and having a filter silently undo it is worse than the pair verdict warning about it.
  setTimelineCloudCeiling: (timelineCloudCeilingPercentage) =>
    set({ timelineCloudCeilingPercentage }),

  setActiveDrawTool: (activeDrawTool) => set({ activeDrawTool }),

  setDrawnRegions: (regions) =>
    set((state) => ({
      drawnRegions: [...regions],
      // A newly committed region becomes the active scope, because drawing one is a statement of intent
      // about what the next question is about. Removing the active one falls back to the whole AOI.
      activeRegionId:
        regions.length > state.drawnRegions.length
          ? (regions[regions.length - 1]?.id ?? null)
          : regions.some((region) => region.id === state.activeRegionId)
            ? state.activeRegionId
            : null,
    })),

  setActiveRegionId: (activeRegionId) => set({ activeRegionId }),

  toggleTraceExpanded: (isExpanded) =>
    set((state) => ({ isTraceExpanded: isExpanded ?? !state.isTraceExpanded })),
  setReportOpen: (isReportOpen) => set({ isReportOpen }),
  setActivePlan: (activePlan) => set({ activePlan }),

  togglePlanStep: (stepId) =>
    set((state) =>
      state.activePlan === null
        ? {}
        : {
            activePlan: {
              ...state.activePlan,
              steps: state.activePlan.steps.map((step) =>
                step.id === stepId ? { ...step, isEnabled: !step.isEnabled } : step,
              ),
            },
          },
    ),

  selectRun: (selectedRunId) => set({ selectedRunId }),

  // A new run always takes the surface. Leaving an old answer on screen while the machine works below it
  // is how an operator reads a stale number as a fresh one.
  startRun: (run) =>
    set((state) => ({ runs: [...state.runs, run], isRunning: true, selectedRunId: null })),

  upsertTraceStep: (runId, step) =>
    set((state) => ({
      runs: updateRun(state.runs, runId, (run) => {
        const existingIndex = run.traceSteps.findIndex((candidate) => candidate.id === step.id);
        const traceSteps =
          existingIndex === -1
            ? [...run.traceSteps, step]
            : run.traceSteps.map((candidate, index) =>
                index === existingIndex ? step : candidate,
              );
        return { ...run, traceSteps: boundTrace(traceSteps) };
      }),
    })),

  appendAnswerText: (runId, text) =>
    set((state) => ({
      runs: updateRun(state.runs, runId, (run) => ({
        ...run,
        answerText: run.answerText + text,
      })),
    })),

  attachClaim: (runId, claimId) =>
    set((state) => ({
      runs: updateRun(state.runs, runId, (run) =>
        run.claimIds.includes(claimId)
          ? run
          : { ...run, claimIds: [...run.claimIds, claimId] },
      ),
    })),

  completeRun: (runId, result) =>
    set((state) => ({
      isRunning: false,
      runs: updateRun(state.runs, runId, (run) => ({
        ...run,
        status: "complete",
        confidence: result.confidence,
        insufficientEvidence: result.insufficientEvidence,
        totalDurationMs: result.totalDurationMs,
      })),
    })),

  failRun: (runId, message) =>
    set((state) => ({
      isRunning: false,
      runs: updateRun(state.runs, runId, (run) => ({
        ...run,
        status: "failed",
        answerText: run.answerText.length > 0 ? run.answerText : message,
      })),
    })),

  cancelRun: (runId) =>
    set((state) => ({
      isRunning: false,
      runs: updateRun(state.runs, runId, (run) => ({ ...run, status: "cancelled" })),
    })),
}));

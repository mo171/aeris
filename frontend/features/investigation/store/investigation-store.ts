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

import type { StageDrawnRegion } from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";
import { INVESTIGATION_LIMITS } from "@/lib/constants/investigation";

import type {
  AnalysisPlan,
  AnalysisRun,
  AnalysisTraceStep,
} from "../types/analysis.types";
import type { InsufficientEvidence } from "../types/evidence.types";
import type { WorkspaceMode as InvestigationMode } from "../types/investigation.types";
import type { LayerRenderMode } from "../types/layer.types";

interface InvestigationState {
  investigationId: string | null;

  // ── Viewer ───────────────────────────────────────────────────────────────────────────────────────
  comparatorBinding: InvestigationMode;
  renderMode: LayerRenderMode;
  isPlaybackRunning: boolean;
  isPresentMode: boolean;

  /** Operator overrides on top of what the backend declared. Absent means "use the descriptor". */
  layerVisibilityOverrides: Record<string, boolean>;
  layerOpacityOverrides: Record<string, number>;
  soloLayerId: string | null;

  /** The claim currently under the pointer. Drives the scene spotlight. */
  spotlightClaimId: string | null;
  /** A trace step's intermediate product, temporarily added to the scene. */
  artefactLayerId: string | null;

  // ── Region drawing ───────────────────────────────────────────────────────────────────────────────
  isRegionDrawArmed: boolean;
  drawnRegion: StageDrawnRegion | null;

  // ── Panels ───────────────────────────────────────────────────────────────────────────────────────
  isTraceExpanded: boolean;
  isReportOpen: boolean;
  activePlan: AnalysisPlan | null;

  // ── The analysis run ─────────────────────────────────────────────────────────────────────────────
  runs: AnalysisRun[];
  isRunning: boolean;

  // ── Actions ──────────────────────────────────────────────────────────────────────────────────────
  enterInvestigation: (investigationId: string, mode: InvestigationMode) => void;
  leaveInvestigation: () => void;

  setComparatorBinding: (binding: InvestigationMode) => void;
  setRenderMode: (renderMode: LayerRenderMode) => void;
  toggleRenderMode: () => void;
  setPlaybackRunning: (isRunning: boolean) => void;
  togglePresentMode: () => void;

  setLayerVisibility: (layerId: string, isVisible: boolean) => void;
  setLayerOpacity: (layerId: string, opacity: number) => void;
  toggleSoloLayer: (layerId: string) => void;

  setSpotlightClaimId: (claimId: string | null) => void;
  setArtefactLayerId: (layerId: string | null) => void;

  setRegionDrawArmed: (isArmed: boolean) => void;
  setDrawnRegion: (region: StageDrawnRegion | null) => void;

  toggleTraceExpanded: (isExpanded?: boolean) => void;
  setReportOpen: (isOpen: boolean) => void;
  setActivePlan: (plan: AnalysisPlan | null) => void;
  togglePlanStep: (stepId: string) => void;

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
  isPlaybackRunning: false,
  isPresentMode: false,

  layerVisibilityOverrides: {},
  layerOpacityOverrides: {},
  soloLayerId: null,

  spotlightClaimId: null,
  artefactLayerId: null,

  isRegionDrawArmed: false,
  drawnRegion: null,

  isTraceExpanded: false,
  isReportOpen: false,
  activePlan: null,

  runs: [],
  isRunning: false,

  // Entering resets everything view-scoped. Carrying one investigation's hidden layers into the next
  // would make the workspace feel haunted.
  enterInvestigation: (investigationId, mode) =>
    set({
      investigationId,
      comparatorBinding: mode,
      renderMode: "draped",
      isPlaybackRunning: false,
      isPresentMode: false,
      layerVisibilityOverrides: {},
      layerOpacityOverrides: {},
      soloLayerId: null,
      spotlightClaimId: null,
      artefactLayerId: null,
      isRegionDrawArmed: false,
      drawnRegion: null,
      isTraceExpanded: false,
      isReportOpen: false,
      activePlan: null,
      runs: [],
      isRunning: false,
    }),

  leaveInvestigation: () =>
    set({
      investigationId: null,
      runs: [],
      isRunning: false,
      spotlightClaimId: null,
      artefactLayerId: null,
      drawnRegion: null,
      isRegionDrawArmed: false,
      isPresentMode: false,
    }),

  setComparatorBinding: (comparatorBinding) => set({ comparatorBinding }),
  setRenderMode: (renderMode) => set({ renderMode }),
  toggleRenderMode: () =>
    set((state) => ({ renderMode: state.renderMode === "draped" ? "extruded" : "draped" })),
  setPlaybackRunning: (isPlaybackRunning) => set({ isPlaybackRunning }),
  togglePresentMode: () => set((state) => ({ isPresentMode: !state.isPresentMode })),

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

  setRegionDrawArmed: (isRegionDrawArmed) => set({ isRegionDrawArmed }),
  setDrawnRegion: (drawnRegion) => set({ drawnRegion, isRegionDrawArmed: false }),

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

  startRun: (run) => set((state) => ({ runs: [...state.runs, run], isRunning: true })),

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

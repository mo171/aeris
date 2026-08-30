// features/investigation/components/InvestigationScreen.tsx — the Investigation Workspace surface.
//
// what  : Composes the four zones of the workspace — identity strip, inputs and evidence layers, the scene
//         with its tools, the AERIS answer surface, and the execution spine — over the shared 3D stage.
// where : Rendered by app/(geospatial)/investigation/[investigationId]/page.tsx, which contains nothing else.
// how   : The scene is NOT rendered here. It belongs to the shared stage mounted by the route group layout,
//         which is what lets the camera keep flying from the globe into this surface without a cut. This
//         screen contributes the chrome that floats over it and the hooks that drive it.
//
//         Zones never talk to each other. The answer panel spotlights a claim by writing to the feature
//         store; the stage binding reads that and dims the scene. Adding a fifth zone therefore means
//         adding a component, not rewiring the four that exist.
//
//         Present mode removes the chrome rather than hiding it behind an opacity transition, so nothing
//         invisible is still capturing pointer events over the scene. The comparator handle survives,
//         because the reveal is the thing being presented.
//
//         A LENS IS A FIFTH ZONE THAT BORROWS THE OTHER FOUR. The cross-modal reading contributes a
//         section to the left panel and a verdict to the right, both as composed slots, and swaps the
//         evidence the stage draws. It does not get a surface of its own — it used to, and the cost was
//         that an operator reading "these two sensors disagree here" had no assistant to ask about it, no
//         timeline to move the pair, and no draw tool to scope a question to the ground in question.

//         Each zone has its own error boundary: a failure in the layer stack must cost the layer stack,
//         not the answer and the trace as well.

"use client";

import { useCallback, useMemo, useState } from "react";

import { PanelContainer } from "@/components/sharedUI/functionalComponent/appShell/PanelContainer";
import { PanelErrorBoundary } from "@/components/sharedUI/functionalComponent/feedback/PanelErrorBoundary";
import { ErrorState } from "@/components/sharedUI/functionalComponent/feedback/ErrorState";
import { PanelSkeleton } from "@/components/sharedUI/functionalComponent/feedback/PanelSkeleton";
import { AgreementSection } from "@/features/crossModal/components/AgreementSection";
import { SensorsSection } from "@/features/crossModal/components/SensorsSection";
import { useCrossModal } from "@/features/crossModal/hooks/use-cross-modal";
import {
  composeSensorLayers,
  spotlightIdsForRow,
} from "@/features/crossModal/lib/sensor-stage-layers";
import type { AgreementRow } from "@/features/crossModal/types/cross-modal.types";
import { ANALYSIS_OPERATIONS } from "@/lib/constants/analysis-operations";
import {
  AGREEMENT,
  agreementQuestion,
  CROSS_MODAL_OPERATION_ID,
} from "@/lib/constants/cross-modal";
import { INVESTIGATION_CAMERA } from "@/lib/constants/investigation";
import { BOOT_SEQUENCE_DELAY } from "@/lib/constants/motion";
import { useGeoStageStore } from "@/store/geo-stage-store";
import { useUiStore } from "@/store/ui-store";

import { useAnalysisRun } from "../hooks/use-analysis-run";
import { useAutonomousInvestigation } from "../hooks/use-autonomous-investigation";
import { useCatalogueSearch } from "../hooks/use-catalogue-search";
import { useEvidenceGraph } from "../hooks/use-evidence-graph";
import { useInvestigation } from "../hooks/use-investigation";
import { useInvestigationCommands } from "../hooks/use-investigation-commands";
import { useRegionSelection } from "../hooks/use-region-selection";
import { useScenePopout } from "../hooks/use-scene-popout";
import { useReferenceLayers } from "../hooks/use-reference-layers";
import { useSceneStageBinding } from "../hooks/use-scene-stage-binding";
import { useTimeline } from "../hooks/use-timeline";
import { useInvestigationStore } from "../store/investigation-store";
import type { Claim } from "../types/evidence.types";
import type { InvestigationSceneSlot } from "../types/investigation.types";
import { AnswerPanel } from "./answerPanel/AnswerPanel";
import { InvestigationHeader } from "./header/InvestigationHeader";
import { LeftPanelTabs } from "./inputsPanel/LeftPanelTabs";
import { ReportDrawer } from "./report/ReportDrawer";
import { ExecutionSpine } from "./tracePanel/ExecutionSpine";
import { CameraControls } from "./viewer/CameraControls";
import { DrawToolbar } from "./viewer/DrawToolbar";
import { EvidenceLegend } from "./viewer/EvidenceLegend";
import { FeatureInspector } from "./viewer/FeatureInspector";
import { ProjectionToggle } from "./viewer/ProjectionToggle";
import { RegionPromptPopover } from "./viewer/RegionPromptPopover";
import { SceneReadout } from "./viewer/SceneReadout";
import { SplitHandle } from "./viewer/SplitHandle";
import { TargetLockOverlay } from "./viewer/TargetLockOverlay";
import { TimelineScrubber } from "./viewer/TimelineScrubber";
import { ViewerToolCluster } from "./viewer/ViewerToolCluster";

interface InvestigationScreenProps {
  investigationId: string;
}

export function InvestigationScreen({ investigationId }: InvestigationScreenProps) {
  const { investigation, isLoading, error, assignSceneRole, saveCameraView } =
    useInvestigation(investigationId);
  const { graph, layers, featureIdsForClaim } = useEvidenceGraph(investigationId);

  // Which catalogue products are actually on the scene, so the overlay browser can mark them rather than
  // listing every capability with no indication of which ones the operator is already looking at.
  const activeOverlayIds = useMemo(
    () =>
      layers
        .filter((layer) => layer.isVisible && layer.overlayId !== null)
        .map((layer) => layer.overlayId as string),
    [layers],
  );
  const { ask, stop } = useAnalysisRun(investigationId);
  const autonomous = useAutonomousInvestigation({ investigationId, ask });
  const regionSelection = useRegionSelection(investigationId);
  const scenePopout = useScenePopout({ investigationId, onAssignRole: assignSceneRole });
  const catalogue = useCatalogueSearch(investigationId);
  const referenceLayers = useReferenceLayers();
  /**
   * The cross-modal reading of this same investigation.
   *
   * Always called, never conditional — the hook gates its own query on the lens being open, so an
   * investigation nobody cross-checks pays nothing for the capability being available.
   */
  const crossModal = useCrossModal(investigationId);

  const [isSensorsExpanded, setIsSensorsExpanded] = useState(true);
  const [isAgreementExpanded, setIsAgreementExpanded] = useState(true);

  const sceneSlots = useMemo(() => investigation?.sceneSlots ?? [], [investigation]);
  const acquisitions = useMemo(() => investigation?.acquisitions ?? [], [investigation]);

  /** Which scene currently occupies which role, so the acquisition list can show what is bound. */
  const roleBySceneId = useMemo(
    () => Object.fromEntries(sceneSlots.map((slot) => [slot.sceneId, slot.role])),
    [sceneSlots],
  );


  /**
   * Which acquisitions the answer on screen actually drew from.
   *
   * Marked on the timeline so the operator can see that a claim about 2019 rests on the 2019 pass and not
   * on a neighbouring one — the difference between an answer and an answer you can check.
   */
  const citedSceneIds = useMemo(
    () => [...new Set(Object.values(graph.evidenceById).flatMap((item) => item.sourceSceneIds))],
    [graph.evidenceById],
  );

  const timeline = useTimeline({ investigation, citedSceneIds });

  const isDataPanelOpen = useUiStore((state) => state.isDataPanelOpen);
  const isAssistantPanelOpen = useUiStore((state) => state.isAssistantPanelOpen);
  const dataPanelWidth = useUiStore((state) => state.dataPanelWidth);
  const assistantPanelWidth = useUiStore((state) => state.assistantPanelWidth);
  const setDataPanelWidth = useUiStore((state) => state.setDataPanelWidth);
  const setAssistantPanelWidth = useUiStore((state) => state.setAssistantPanelWidth);

  const runs = useInvestigationStore((state) => state.runs);
  const isRunning = useInvestigationStore((state) => state.isRunning);
  const activePlan = useInvestigationStore((state) => state.activePlan);
  const isPresentMode = useInvestigationStore((state) => state.isPresentMode);
  const projection = useInvestigationStore((state) => state.projection);
  const setProjection = useInvestigationStore((state) => state.setProjection);
  const setSpotlightClaimId = useInvestigationStore((state) => state.setSpotlightClaimId);
  const inspectedFeature = useInvestigationStore((state) => state.inspectedFeature);
  const setInspectedFeature = useInvestigationStore((state) => state.setInspectedFeature);
  const setCrossModalLensActive = useInvestigationStore((state) => state.setCrossModalLensActive);

  /**
   * The clicked feature, its layer, and every claim that rests on it.
   *
   * The claim lookup runs the spotlight relationship backwards: a claim names its evidence, so finding the
   * claims for one feature needs a scan. It runs once per click rather than per frame, which is why a scan
   * is the right trade against a second index that would have to be kept in step with every streamed layer.
   */
  const inspection = useMemo(() => {
    if (!inspectedFeature) {
      return null;
    }

    const layer = graph.layersById[inspectedFeature.layerId];
    const feature = layer?.features.find((candidate) => candidate.id === inspectedFeature.featureId);
    if (!layer || !feature) {
      return null;
    }

    const claims = graph.claimOrder
      .map((claimId) => graph.claimsById[claimId])
      .filter((claim) => featureIdsForClaim(claim.id).includes(feature.id));

    return { feature, layer, claims };
  }, [featureIdsForClaim, graph, inspectedFeature]);

  const toggleSoloLayer = useInvestigationStore((state) => state.toggleSoloLayer);
  const togglePlanStep = useInvestigationStore((state) => state.togglePlanStep);

  /**
   * The evidence the stage draws while the lens is open: both sensors' stacks, radar beneath optical.
   *
   * Null when the lens is closed, which hands the stage straight back to the run's own layers. Composed
   * here and passed DOWN rather than pushed by a second binding hook — one writer per stage.
   */
  const sensorLayers = useMemo(
    () =>
      crossModal.isActive
        ? composeSensorLayers({ result: crossModal.result, soloSensor: crossModal.soloSensor })
        : null,
    [crossModal.isActive, crossModal.result, crossModal.soloSensor],
  );

  const agreementSpotlightIds = useMemo(
    () =>
      crossModal.isActive
        ? spotlightIdsForRow(crossModal.result, crossModal.selectedRowId)
        : null,
    [crossModal.isActive, crossModal.result, crossModal.selectedRowId],
  );

  useSceneStageBinding({
    investigation,
    layers,
    baseLayers: timeline.layers,
    referenceLayers,
    comparatorOverride: timeline.comparatorOverride,
    sensorLayers,
    spotlightFeatureIds: agreementSpotlightIds,
    featureIdsForClaim,
    // The scene is lit for the moment the comparison observation was taken, so its shadows agree with its
    // pixels rather than with the operator's wall clock.
    illuminationTime: timeline.comparison?.capturedAt ?? null,
  });

  /**
   * What the investigation can currently satisfy, so each Toolbox operation can say what it is waiting
   * for rather than appearing broken.
   */
  const analysisReadiness = useMemo(
    () => ({
      pair: timeline.baseline !== null && timeline.comparison !== null,
      optical: timeline.comparison?.modality !== "sar",
      sar: sceneSlots.some((slot) => slot.role === "sar"),
      evidence: layers.some((layer) => layer.features.length > 0),
      scopeLabel: regionSelection.activeRegion ? "the drawn region" : "the area of interest",
    }),
    [layers, regionSelection.activeRegion, sceneSlots, timeline.baseline, timeline.comparison],
  );

  /**
   * Runs a named operation.
   *
   * It goes through the SAME analysis run as a typed question — one pipeline, two ways in — but carries
   * the operation id on the wire so the backend dispatches directly instead of classifying intent from a
   * sentence it might read wrong.
   */
  const handleRunOperation = useCallback(
    (operationId: string) => {
      const operation = ANALYSIS_OPERATIONS.find((candidate) => candidate.id === operationId);
      if (!operation) {
        return;
      }

      // A lens re-reads evidence that already exists. Dispatching an analysis run for one would put a
      // trace step on the spine for work no model performed, which is the opposite of auditable.
      // Cross-modal is the only lens today; a second would turn this into a lookup rather than a branch.
      if (operation.kind === "lens") {
        setCrossModalLensActive(!crossModal.isActive);
        return;
      }

      ask(operation.prompt, { operationId });
    },
    [ask, crossModal.isActive, setCrossModalLensActive],
  );

  /** Turns the popover's window into the temporal query the archive is actually asked. */
  const handleArchiveSearch = useCallback(
    (window: {
      from: string;
      to: string;
      modalities: Parameters<typeof catalogue.search>[0]["modalities"];
      cloudCeilingPercentage: number;
    }) => {
      if (!investigation) {
        return;
      }

      // The ceiling is applied locally as well as sent, so the timeline stops offering scenes the query
      // has already declared unusable rather than waiting for the response to disagree with it.
      timeline.setCloudCeiling(window.cloudCeilingPercentage);

      catalogue.search({
        areaOfInterest: investigation.areaOfInterest,
        from: window.from,
        to: window.to,
        modalities: window.modalities,
        maximumCloudPercentage: window.cloudCeilingPercentage,
      });
    },
    [catalogue, investigation, timeline],
  );

  useInvestigationCommands({
    ask,
    acquisitions,
    saveCameraView,
    prepareAutonomous: autonomous.prepare,
    evidenceById: graph.evidenceById,
    areaOfInterest: investigation?.areaOfInterest ?? null,
  });

  const handleFocusScene = useCallback(
    (slot: InvestigationSceneSlot) => {
      toggleSoloLayer(slot.layerId);
      if (investigation) {
        useGeoStageStore.getState().handle?.camera.flyToBoundingBox(investigation.areaOfInterest, {
          durationMs: INVESTIGATION_CAMERA.localFlightDurationSeconds * 1000,
        });
      }
    },
    [investigation, toggleSoloLayer],
  );

  /** Frames the geometry behind one claim, so "show me" resolves to a place rather than a highlight. */
  const handleFocusEvidence = useCallback(
    (claim: Claim) => {
      setSpotlightClaimId(claim.id);

      const featureIds = new Set(featureIdsForClaim(claim.id));
      const bounds = unionOfFeatureBounds(graph.layersById, featureIds);
      if (bounds) {
        useGeoStageStore.getState().handle?.camera.flyToBoundingBox(bounds, {
          durationMs: INVESTIGATION_CAMERA.localFlightDurationSeconds * 1000,
        });
      }
    },
    [featureIdsForClaim, graph.layersById, setSpotlightClaimId],
  );

  const handleInvestigate = useCallback(
    (claimId: string) => autonomous.prepare(claimId),
    [autonomous],
  );

  /**
   * Hands an agreement row's question to the assistant.
   *
   * The capability that was impossible while the cross-modal reading lived on its own route: the ledger
   * could name a conflict and tell the operator to resolve it with a third observation, and there was no
   * composer on that surface to act on the advice.
   */
  const handleAskAboutRow = useCallback(
    (row: AgreementRow) => {
      ask(
        agreementQuestion({
          stateLabel: AGREEMENT[row.state].label,
          label: row.label,
          reason: row.reason,
        }),
      );
    },
    [ask],
  );

  /** Frames every feature BOTH sensors contributed to a row, not just the half drawn on top. */
  const handleFocusRow = useCallback(
    (row: AgreementRow) => {
      if (!crossModal.result) {
        return;
      }

      const sensorLayersById = Object.fromEntries(
        [...crossModal.result.optical.layers, ...(crossModal.result.radar?.layers ?? [])].map(
          (layer) => [layer.id, layer],
        ),
      );
      const featureIds = new Set([...row.opticalFeatureIds, ...row.radarFeatureIds]);
      const bounds = unionOfFeatureBounds(sensorLayersById, featureIds);
      if (bounds) {
        useGeoStageStore.getState().handle?.camera.flyToBoundingBox(bounds, {
          durationMs: INVESTIGATION_CAMERA.localFlightDurationSeconds * 1000,
        });
      }
    },
    [crossModal.result],
  );

  if (error) {
    return (
      <div className="pointer-events-auto absolute inset-0 flex items-center justify-center p-6">
        <ErrorState error={error} />
      </div>
    );
  }

  if (isLoading || !investigation) {
    // Sized to the inputs panel it replaces, so nothing jumps when the record arrives.
    return (
      <div className="pointer-events-none absolute inset-0 flex gap-3 p-3">
        <div style={{ width: dataPanelWidth }} className="shrink-0">
          <PanelSkeleton rowCount={5} rowHeight={64} />
        </div>
      </div>
    );
  }

  return (
    <>
      {/* Full-bleed, beneath the panels: the split runs across the whole scene, not just the gap. */}
      <SplitHandle />
      <TargetLockOverlay />

      {regionSelection.activeRegion ? (
        <div className="pointer-events-none absolute inset-0">
          <RegionPromptPopover
            region={regionSelection.activeRegion}
            suggestions={regionSelection.suggestions}
            isLoading={regionSelection.isLoadingSuggestions}
            onAsk={(prompt) => ask(prompt)}
            onDismiss={() => regionSelection.setActiveRegion(null)}
          />
        </div>
      ) : null}

      {isPresentMode ? null : (
        <div className="pointer-events-none absolute inset-0 flex flex-col gap-3 p-3">
          <PanelErrorBoundary panelName="Investigation header">
            <InvestigationHeader
              investigation={investigation}
              onFocusScene={handleFocusScene}
            />
          </PanelErrorBoundary>

          <div className="flex min-h-0 flex-1 gap-3">
            <PanelContainer
              side="left"
              isOpen={isDataPanelOpen}
              width={dataPanelWidth}
              onWidthCommit={setDataPanelWidth}
              revealDelaySeconds={BOOT_SEQUENCE_DELAY.dataPanel}
              ariaLabel="Inputs and evidence layers"
            >
              <PanelErrorBoundary panelName="Inputs">
                <LeftPanelTabs
                  readiness={analysisReadiness}
                  onRunOperation={handleRunOperation}
                  activeOverlayIds={activeOverlayIds}
                  activeLensIds={crossModal.isActive ? [CROSS_MODAL_OPERATION_ID] : []}
                  sensorsSection={
                    crossModal.isActive ? (
                      <SensorsSection
                        result={crossModal.result}
                        isLoading={crossModal.isLoading}
                        error={crossModal.error}
                        soloSensor={crossModal.soloSensor}
                        onToggleSolo={(sensor) =>
                          crossModal.setSoloSensor(
                            crossModal.soloSensor === sensor ? null : sensor,
                          )
                        }
                        polarisation={crossModal.polarisation}
                        onPolarisationChange={crossModal.setPolarisation}
                        isExpanded={isSensorsExpanded}
                        onToggleExpanded={() => setIsSensorsExpanded((current) => !current)}
                        onClose={() => setCrossModalLensActive(false)}
                      />
                    ) : undefined
                  }
                  sceneSlots={sceneSlots}
                  acquisitions={acquisitions}
                  roleBySceneId={roleBySceneId}
                  openSceneIds={scenePopout.openSceneIds}
                  onOpenScene={scenePopout.openScene}
                  layers={layers}
                  regions={regionSelection.regions}
                  activeRegionId={regionSelection.activeRegion?.id ?? null}
                  onSelectRegion={regionSelection.setActiveRegion}
                  onRemoveRegion={regionSelection.removeRegion}
                  onFocusScene={handleFocusScene}
                />
              </PanelErrorBoundary>
            </PanelContainer>

            {/*
              The free space between the panels. The scene's own controls live here rather than being
              anchored to the viewport, so they can never end up underneath a panel at any panel width.
            */}
            <div className="pointer-events-none relative flex min-w-0 flex-1 flex-col items-center gap-2">
              {/* Geometry tools sit at the top of the free column, nearest the scene they act on. */}
              <DrawToolbar
                activeTool={regionSelection.activeTool}
                onSelectTool={regionSelection.selectTool}
              />

              {/*
                The key takes the corner opposite the inspector. Both are anchored to the free column
                rather than the viewport, so neither can slide under a panel at any panel width.
              */}
              <div className="absolute top-0 left-0 z-10">
                <EvidenceLegend layers={layers} />
              </div>

              {inspection ? (
                <div className="pointer-events-none absolute top-0 right-0 z-10">
                  <FeatureInspector
                    feature={inspection.feature}
                    layer={inspection.layer}
                    claims={inspection.claims}
                    onFocusClaim={handleFocusEvidence}
                    onClose={() => setInspectedFeature(null)}
                  />
                </div>
              ) : null}

              <div className="flex-1" aria-hidden="true" />

              <SceneReadout />
              <div className="flex flex-wrap items-end justify-center gap-2">
                <ProjectionToggle projection={projection} onChange={setProjection} />
                <CameraControls />
                <ViewerToolCluster />
              </div>
              <TimelineScrubber
                timeline={timeline}
                hasCrossModalScene={sceneSlots.some((slot) => slot.role === "sar")}
                archive={{
                  isSearching: catalogue.isSearching,
                  error: catalogue.error,
                  coverageGaps: catalogue.coverageGaps,
                  recommendation: catalogue.recommendation,
                  advisory: catalogue.advisory,
                  onSearch: handleArchiveSearch,
                  onDismissRecommendation: catalogue.dismissRecommendation,
                }}
              />
            </div>

            <PanelContainer
              side="right"
              isOpen={isAssistantPanelOpen}
              width={assistantPanelWidth}
              onWidthCommit={setAssistantPanelWidth}
              revealDelaySeconds={BOOT_SEQUENCE_DELAY.assistantPanel}
              ariaLabel="AERIS answer panel"
            >
              <PanelErrorBoundary panelName="AERIS">
                <AnswerPanel
                  verdictSection={
                    crossModal.isActive ? (
                      <AgreementSection
                        result={crossModal.result}
                        isLoading={crossModal.isLoading}
                        counts={crossModal.counts}
                        rows={crossModal.rows}
                        selectedRowId={crossModal.selectedRowId}
                        onSelectRow={crossModal.selectRow}
                        isExpanded={isAgreementExpanded}
                        onToggleExpanded={() => setIsAgreementExpanded((current) => !current)}
                        onAskAboutRow={handleAskAboutRow}
                        onFocusRow={handleFocusRow}
                      />
                    ) : undefined
                  }
                  runs={runs}
                  isRunning={isRunning}
                  claimsById={graph.claimsById}
                  evidenceById={graph.evidenceById}
                  activePlan={activePlan}
                  onAsk={ask}
                  onStop={stop}
                  onInvestigate={handleInvestigate}
                  onFocusEvidence={handleFocusEvidence}
                  onTogglePlanStep={togglePlanStep}
                  onExecutePlan={autonomous.execute}
                  onDismissPlan={autonomous.dismiss}
                />
              </PanelErrorBoundary>
            </PanelContainer>
          </div>

          <PanelErrorBoundary panelName="Execution trace">
            <ExecutionSpine run={runs.at(-1) ?? null} />
          </PanelErrorBoundary>
        </div>
      )}

      <ReportDrawer investigationId={investigationId} investigationName={investigation.name} />
    </>
  );
}

/**
 * The extent covering every feature behind a claim.
 *
 * Framing the union rather than the first feature matters when a change is distributed: an answer about
 * "the north-eastern quarter" that flies to one polygon out of eleven has shown the operator a detail and
 * called it the finding.
 */
function unionOfFeatureBounds(
  layersById: Record<string, { features: readonly { id: string; geometry: unknown }[] }>,
  featureIds: Set<string>,
): { west: number; south: number; east: number; north: number } | null {
  let west = Number.POSITIVE_INFINITY;
  let south = Number.POSITIVE_INFINITY;
  let east = Number.NEGATIVE_INFINITY;
  let north = Number.NEGATIVE_INFINITY;
  let hasAny = false;

  const include = (longitude: number, latitude: number) => {
    hasAny = true;
    west = Math.min(west, longitude);
    east = Math.max(east, longitude);
    south = Math.min(south, latitude);
    north = Math.max(north, latitude);
  };

  for (const layer of Object.values(layersById)) {
    for (const feature of layer.features) {
      if (!featureIds.has(feature.id)) {
        continue;
      }

      const geometry = feature.geometry as
        | { type: "polygon"; ring: { latitude: number; longitude: number }[] }
        | { type: "point"; position: { latitude: number; longitude: number } }
        | { type: "bbox"; bounds: { west: number; south: number; east: number; north: number } };

      if (geometry.type === "polygon") {
        for (const point of geometry.ring) {
          include(point.longitude, point.latitude);
        }
      } else if (geometry.type === "point") {
        include(geometry.position.longitude, geometry.position.latitude);
      } else {
        include(geometry.bounds.west, geometry.bounds.south);
        include(geometry.bounds.east, geometry.bounds.north);
      }
    }
  }

  return hasAny ? { west, south, east, north } : null;
}

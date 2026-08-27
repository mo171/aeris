// features/investigation/hooks/use-scene-stage-binding.ts — connects the workspace to the shared 3D stage.
//
// what  : Puts the stage into scene mode, completes the descent, pushes layers, binds the comparator to
//         scene roles, drives the spotlight and volumetric mode, and routes region draws and feature
//         clicks back into the feature.
// where : Called once by InvestigationScreen. Nothing else in this feature touches the stage directly.
// how   : This is the workspace half of the adapter that keeps the renderer swappable. Everything above
//         it speaks in claims, layers and roles; the stage speaks in primitives. The translation happens
//         only here.
//
//         The descent is the important part. Mission Command starts the camera flying and routes without
//         waiting for it, so this hook mounts around a camera that is ALREADY in motion. It consumes the
//         pending descent to learn that, and deliberately does not re-issue the flight — restarting it
//         would visibly jerk the camera at exactly the moment the transition is meant to feel seamless.
//         Arriving by a direct URL instead means no pending descent, so it frames the area of interest
//         from wherever the camera happens to be.
//
//         Layers are pushed as a whole list on every change, not diffed here. The stage does its own
//         diffing against what it already holds, which keeps this hook declarative and means an operator
//         toggling a layer never causes a rebuild of the ones around it.

"use client";

import { useEffect, useRef } from "react";

import { COMPARATOR_BINDING, INVESTIGATION_CAMERA } from "@/lib/constants/investigation";
import { useGeoStageStore } from "@/store/geo-stage-store";

import { useInvestigationStore } from "../store/investigation-store";
import type { Investigation } from "../types/investigation.types";
import type { EvidenceLayer } from "../types/layer.types";

interface SceneStageBindingOptions {
  investigation: Investigation | undefined;
  layers: EvidenceLayer[];
  /** Resolves the claim under the pointer into the stage features that support it. */
  featureIdsForClaim: (claimId: string) => string[];
}

export function useSceneStageBinding({
  investigation,
  layers,
  featureIdsForClaim,
}: SceneStageBindingOptions): void {
  const stage = useGeoStageStore((state) => state.handle);
  const consumeDescent = useGeoStageStore((state) => state.consumeDescent);

  const comparatorBinding = useInvestigationStore((state) => state.comparatorBinding);
  const renderMode = useInvestigationStore((state) => state.renderMode);
  const spotlightClaimId = useInvestigationStore((state) => state.spotlightClaimId);
  const artefactLayerId = useInvestigationStore((state) => state.artefactLayerId);
  const isRegionDrawArmed = useInvestigationStore((state) => state.isRegionDrawArmed);
  const isPlaybackRunning = useInvestigationStore((state) => state.isPlaybackRunning);
  const isPresentMode = useInvestigationStore((state) => state.isPresentMode);

  // Mirrored so the spotlight effect never re-runs when the resolver changes identity.
  const featureIdsForClaimRef = useRef(featureIdsForClaim);
  useEffect(() => {
    featureIdsForClaimRef.current = featureIdsForClaim;
  }, [featureIdsForClaim]);

  const investigationId = investigation?.id;

  // ── Mode, area of interest and the descent ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!stage || !investigation) {
      return;
    }

    stage.appearance.setMode("scene");
    stage.sceneLayers.setAreaOfInterestOutline(investigation.areaOfInterest);

    const pendingDescent = consumeDescent(investigation.id);
    if (!pendingDescent) {
      // Direct arrival: no flight is in progress, so frame the area of interest ourselves. A saved
      // bookmark wins, because it is where the operator actually left off.
      if (investigation.cameraBookmark) {
        stage.camera.applyBookmark(investigation.cameraBookmark);
      } else {
        stage.camera.flyToBoundingBox(investigation.areaOfInterest, {
          durationMs: INVESTIGATION_CAMERA.localFlightDurationSeconds * 1000,
        });
      }
    }

    return () => {
      stage.sceneLayers.clear();
      stage.appearance.setMode("globe");
    };
  }, [consumeDescent, investigation, stage]);

  // ── Layers ───────────────────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!stage) {
      return;
    }

    // A peeked artefact is forced visible for as long as the operator is holding that trace step open.
    // It is a temporary inspection, so it never becomes a persistent visibility override in the store.
    const renderedLayers =
      artefactLayerId === null
        ? layers
        : layers.map((layer) =>
            layer.id === artefactLayerId ? { ...layer, isVisible: true } : layer,
          );

    stage.sceneLayers.setLayers(renderedLayers);
  }, [artefactLayerId, layers, stage]);

  useEffect(() => {
    stage?.sceneLayers.setRenderMode(renderMode);
  }, [renderMode, stage]);

  // ── Comparator ───────────────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!stage || !investigation) {
      return;
    }

    const binding = COMPARATOR_BINDING[comparatorBinding];
    const layerIdForRole = (role: string) =>
      investigation.sceneSlots.find((slot) => slot.role === role)?.layerId ?? null;

    stage.comparator.bind(layerIdForRole(binding.left), layerIdForRole(binding.right));
  }, [comparatorBinding, investigation, stage]);

  useEffect(() => {
    stage?.comparator.setPlayback(isPlaybackRunning);
  }, [isPlaybackRunning, stage]);

  // ── Spotlight ────────────────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!stage) {
      return;
    }

    if (spotlightClaimId === null) {
      stage.sceneLayers.setSpotlight(null);
      return;
    }

    stage.sceneLayers.setSpotlight(featureIdsForClaimRef.current(spotlightClaimId));
  }, [spotlightClaimId, stage]);

  // ── Region drawing ───────────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!stage) {
      return;
    }

    if (isRegionDrawArmed) {
      stage.regionDraw.begin("rectangle");
      return;
    }

    if (stage.regionDraw.isDrawing()) {
      stage.regionDraw.cancel();
    }
  }, [isRegionDrawArmed, stage]);

  useEffect(() => {
    if (!stage) {
      return;
    }

    return stage.regionDraw.subscribe((region) => {
      // A null region means the operator cancelled or clicked without dragging; treating that as a
      // cleared selection is what makes escaping the tool feel unambiguous.
      useInvestigationStore.getState().setDrawnRegion(region);
    });
  }, [stage]);

  // ── Clicking evidence on the scene ───────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!stage) {
      return;
    }

    stage.sceneLayers.setFeatureClickHandler((featureId) => {
      const store = useInvestigationStore.getState();
      const graphClaimId = findClaimIdForFeature(featureId, featureIdsForClaimRef.current);
      // Clicking a polygon on the scene is the same gesture as hovering its claim in the answer, run
      // backwards. Both end at the same spotlight, so the two directions cannot disagree.
      store.setSpotlightClaimId(graphClaimId);
    });

    return () => {
      stage.sceneLayers.setFeatureClickHandler(null);
    };
  }, [stage]);

  // ── Present mode ─────────────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    stage?.camera.setAutoRotate(isPresentMode);
  }, [isPresentMode, stage]);

  // Leaving the workspace must return the stage to an orbital instrument, even if the route change came
  // from somewhere other than the effect above.
  useEffect(() => {
    if (!investigationId) {
      return;
    }
    return () => {
      useInvestigationStore.getState().setSpotlightClaimId(null);
    };
  }, [investigationId]);
}

/**
 * Reverse lookup from a clicked feature back to the claim it supports.
 *
 * The forward direction is cheap because a claim names its evidence; the reverse needs a scan. It runs
 * once per click rather than per frame, so a scan is the right trade against maintaining a second index
 * that would have to be kept in step with every streamed layer.
 */
function findClaimIdForFeature(
  featureId: string,
  featureIdsForClaim: (claimId: string) => string[],
): string | null {
  const { runs } = useInvestigationStore.getState();
  const claimIds = runs.flatMap((run) => run.claimIds);

  for (const claimId of claimIds) {
    if (featureIdsForClaim(claimId).includes(featureId)) {
      return claimId;
    }
  }

  return null;
}

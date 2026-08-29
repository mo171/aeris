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

import type { StageLayer } from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";
import { COMPARATOR_BINDING, INVESTIGATION_CAMERA } from "@/lib/constants/investigation";
import { RASTER_CROSS_FADE_MS } from "@/lib/constants/layers";
import { useGeoStageStore } from "@/store/geo-stage-store";

import { useInvestigationStore } from "../store/investigation-store";
import type { Investigation } from "../types/investigation.types";
import type { EvidenceLayer } from "../types/layer.types";

interface SceneStageBindingOptions {
  investigation: Investigation | undefined;
  layers: EvidenceLayer[];
  /**
   * Imagery the timeline scrubbed to that no role slot already draws. Pushed BENEATH the evidence,
   * because it is the ground an analysis ran on rather than a product of one — evidence drawn under the
   * pixels it describes would be evidence nobody can see.
   */
  baseLayers?: readonly StageLayer[];
  /**
   * Context layers, split by where they belong in the draw order.
   *
   * `under` is ground the imagery sits on — shaded relief. `over` is annotation that would be invisible
   * beneath it — boundaries, roads. Both are pushed as plain stage layers with no provenance, because
   * nothing asserted them.
   */
  referenceLayers?: { under: readonly StageLayer[]; over: readonly StageLayer[] };
  /**
   * Comparator sides chosen on the timeline. Null leaves the role-based binding in charge, which is the
   * state on arrival and whenever the cross-modal binding is active.
   */
  comparatorOverride?: { left: string | null; right: string | null } | null;
  /** Resolves the claim under the pointer into the stage features that support it. */
  featureIdsForClaim: (claimId: string) => string[];
  /**
   * Capture time of the observation currently on the right of the comparator.
   *
   * Drives the scene's sun, so the shadows rendered are the shadows in the pixels. Shadow direction and
   * length are how an analyst reads building height and separates a genuine new structure from a shadow
   * that moved — a scene lit from the wrong side quietly contradicts its own imagery.
   */
  illuminationTime?: string | null;
}

export function useSceneStageBinding({
  investigation,
  layers,
  baseLayers,
  referenceLayers,
  comparatorOverride,
  featureIdsForClaim,
  illuminationTime,
}: SceneStageBindingOptions): void {
  const stage = useGeoStageStore((state) => state.handle);
  const consumeDescent = useGeoStageStore((state) => state.consumeDescent);

  const comparatorBinding = useInvestigationStore((state) => state.comparatorBinding);
  const renderMode = useInvestigationStore((state) => state.renderMode);
  const projection = useInvestigationStore((state) => state.projection);
  const buildingMode = useInvestigationStore((state) => state.buildingMode);
  const buildingStyleId = useInvestigationStore((state) => state.buildingStyleId);
  const terrainExaggeration = useInvestigationStore((state) => state.terrainExaggeration);
  const spotlightClaimId = useInvestigationStore((state) => state.spotlightClaimId);
  const artefactLayerId = useInvestigationStore((state) => state.artefactLayerId);
  const activeDrawTool = useInvestigationStore((state) => state.activeDrawTool);
  const isPlaybackRunning = useInvestigationStore((state) => state.isPlaybackRunning);
  const isTimelineScrubbing = useInvestigationStore((state) => state.isTimelineScrubbing);
  const isTimelinePlaying = useInvestigationStore((state) => state.isTimelinePlaying);
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

    // Draw order IS descriptor order, so this list is the stack from the ground up: relief, then the
    // operator's imagery, then annotation over it, then the evidence on top of everything.
    stage.sceneLayers.setLayers([
      ...(referenceLayers?.under ?? []),
      ...(baseLayers ?? []),
      ...renderedLayers.filter((layer) => layer.kind === "raster-tiles"),
      ...(referenceLayers?.over ?? []),
      ...renderedLayers.filter((layer) => layer.kind !== "raster-tiles"),
    ]);
  }, [artefactLayerId, baseLayers, layers, referenceLayers, stage]);

  useEffect(() => {
    stage?.sceneLayers.setRenderMode(renderMode);
  }, [renderMode, stage]);

  // Magnitude moves from height to colour exactly when the scene has no height to spend: a flat
  // projection cannot extrude at all, and draped mode chooses not to. Without this every change region
  // renders identically however much changed, dropping the most important number on the feature.
  useEffect(() => {
    stage?.sceneLayers.setMagnitudeShading(projection === "2D" || renderMode === "draped");
  }, [projection, renderMode, stage]);

  // A scrub replaces the imagery on every step. The fade tuned for a deliberate layer change reads as lag
  // when it happens ten times inside one drag, so it shortens while the operator is moving through time
  // and returns to normal the moment they stop.
  useEffect(() => {
    stage?.sceneLayers.setCrossFadeMs(
      isTimelineScrubbing || isTimelinePlaying
        ? RASTER_CROSS_FADE_MS.scrubbing
        : RASTER_CROSS_FADE_MS.settled,
    );
  }, [isTimelinePlaying, isTimelineScrubbing, stage]);

  useEffect(() => {
    stage?.appearance.setProjection(projection);
  }, [projection, stage]);

  // Relief is pushed after the mode switch has already applied its defaults, so an operator override
  // survives — entering scene mode sets a starting point, it does not overrule a choice already made.
  useEffect(() => {
    stage?.appearance.setBuildingMode(buildingMode);
  }, [buildingMode, stage]);

  useEffect(() => {
    // Applied after the mode, and independently of it: the tileset may not exist yet when the style is
    // chosen, and setBuildingMode re-applies the current style whenever it creates one.
    stage?.appearance.setBuildingStyle(buildingStyleId);
  }, [buildingStyleId, stage]);

  // Building massing and terrain exaggeration are alternative ways to convey height, and they fight each
  // other. In a city the vertical information is in the BUILDINGS — a 30 m-posting elevation model holds
  // none of it — so exaggerating the ground under un-exaggerated massing only breaks the relationship
  // between them. In open landscape there are no buildings and exaggeration is exactly the right tool.
  // Whichever one is carrying the height gets to be the one that does.
  useEffect(() => {
    stage?.appearance.setTerrainExaggeration(
      buildingMode === "none" ? terrainExaggeration : 1,
    );
  }, [buildingMode, stage, terrainExaggeration]);

  useEffect(() => {
    stage?.appearance.setIlluminationTime(illuminationTime ?? null);
  }, [illuminationTime, stage]);

  // ── Comparator ───────────────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!stage || !investigation) {
      return;
    }

    const binding = COMPARATOR_BINDING[comparatorBinding];
    const layerIdForRole = (role: string) =>
      investigation.sceneSlots.find((slot) => slot.role === role)?.layerId ?? null;

    // The timeline wins when it has an opinion. A side it could not resolve — an acquisition the archive
    // has catalogued but not tiled — falls back to its role slot rather than binding to nothing, so a
    // scrub onto an untiled date leaves the previous imagery up instead of emptying half the scene.
    const left = comparatorOverride?.left ?? layerIdForRole(binding.left);
    const right = comparatorOverride?.right ?? layerIdForRole(binding.right);

    stage.comparator.bind(left, right);
  }, [comparatorBinding, comparatorOverride, investigation, stage]);

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

  // ── Drawing and measurement ──────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!stage) {
      return;
    }

    if (activeDrawTool) {
      stage.draw.begin(activeDrawTool);
      return;
    }

    // Disarming has to reach the stage even when nothing was mid-shape, because that is what restores
    // camera input. Leaving it armed is how a draw tool ends up silently eating every drag.
    stage.draw.cancel();
  }, [activeDrawTool, stage]);

  useEffect(() => {
    if (!stage) {
      return;
    }

    return stage.draw.subscribeRegions((regions) => {
      const store = useInvestigationStore.getState();
      store.setDrawnRegions(regions);
      // Committing a shape ends the tool. Staying armed after a commit means the next drag starts a
      // second shape the operator did not ask for.
      if (regions.length > store.drawnRegions.length) {
        store.setActiveDrawTool(null);
      }
    });
  }, [stage]);

  // ── Clicking evidence on the scene ───────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!stage) {
      return;
    }

    stage.sceneLayers.setFeatureClickHandler((featureId, layerId) => {
      const store = useInvestigationStore.getState();
      const graphClaimId = findClaimIdForFeature(featureId, featureIdsForClaimRef.current);
      // Clicking a polygon on the scene is the same gesture as hovering its claim in the answer, run
      // backwards. Both end at the same spotlight, so the two directions cannot disagree.
      store.setSpotlightClaimId(graphClaimId);
      // And the click also opens the record. Highlighting a detection while refusing to say what it is
      // was the largest working gap on this surface.
      store.setInspectedFeature({ layerId, featureId });
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

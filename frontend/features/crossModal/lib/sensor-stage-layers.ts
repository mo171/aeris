// features/crossModal/lib/sensor-stage-layers.ts — two sensors' evidence, composed into one stage stack.
//
// what  : Turns a cross-modal result plus the operator's solo choice into the ordered stage layers the
//         workspace should draw while the cross-modal lens is open.
// where : Called by useSceneStageBinding, which is the ONLY thing in the application that pushes layers
//         to the stage. Nothing here touches the stage itself.
// how   : A pure function rather than a hook, and that is the whole point. This logic used to live in
//         useCrossModalStageBinding, which called stage.sceneLayers.setLayers at the same time as
//         useSceneStageBinding did — two hooks writing one stage, resolved by whichever effect happened to
//         run last. Reduced to a function, it composes INTO the workspace's single writer instead of
//         competing with it.
//
//         THE SPLIT IS THE COMPARISON. Radar claims the left half and optical the right, so dragging the
//         comparator handle sweeps one sensor into the other over the same ground — the most direct
//         expression of "do these agree" available, and it costs nothing because Cesium splits natively.
//         When one sensor is soloed the split is meaningless, so the surviving layers claim both halves.
//
//         SOLOING NEVER RE-RUNS ANYTHING. Both analyses are complete before the lens opens; soloing only
//         changes what is drawn. An operator checking one sensor's claim in isolation must never wonder
//         whether they changed the result by looking at it.
//
//         Radar's geometry masks are forced VISIBLE while radar is on screen. Layover and shadow are the
//         first thing that invalidates a radar reading, so the operator should meet them before they meet
//         a finding rather than after doubting one.

import type { StageLayer } from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";

import type { CrossModalResult, SensorId } from "../types/cross-modal.types";

/** Layover and shadow — radar's own blindness, distinct from a product it produced. */
const RADAR_GEOMETRY_MASK_IDS: readonly string[] = ["mask-sar-layover", "mask-sar-shadow"];

interface SensorLayerOptions {
  result: CrossModalResult | undefined;
  soloSensor: SensorId | null;
}

/**
 * The layer stack for the cross-modal lens, radar beneath optical.
 *
 * Radar first because it sits under the optical imagery — the same stacking the workspace already uses for
 * anything the operator reads the scene against.
 */
export function composeSensorLayers({ result, soloSensor }: SensorLayerOptions): StageLayer[] {
  if (!result) {
    return [];
  }

  const isOpticalVisible = soloSensor !== "radar";
  const isRadarVisible = soloSensor !== "optical";
  // Comparator side is per SENSOR, not per layer, which is what makes the handle a sensor sweep rather
  // than an arbitrary reveal.
  const side = soloSensor === null;

  const opticalLayers: StageLayer[] = result.optical.layers.map((layer) => ({
    ...layer,
    isVisible: layer.isVisible && isOpticalVisible,
    comparatorSide: side ? "right" : "both",
  }));

  const radarLayers: StageLayer[] = (result.radar?.layers ?? []).map((layer) => ({
    ...layer,
    isVisible: isRadarVisible && (layer.isVisible || isGeometryMask(layer)),
    comparatorSide: side ? "left" : "both",
  }));

  return [...radarLayers, ...opticalLayers];
}

/**
 * Every feature both sensors contributed to one agreement row.
 *
 * Both sides, so selecting a corroborated finding raises what EACH sensor saw rather than only the half
 * that happens to be drawn on top.
 */
export function spotlightIdsForRow(
  result: CrossModalResult | undefined,
  selectedRowId: string | null,
): string[] | null {
  if (!result || selectedRowId === null) {
    return null;
  }

  const row = result.verdict?.rows.find((candidate) => candidate.id === selectedRowId);
  return row ? [...row.opticalFeatureIds, ...row.radarFeatureIds] : null;
}

function isGeometryMask(layer: { overlayId: string | null }): boolean {
  return layer.overlayId !== null && RADAR_GEOMETRY_MASK_IDS.includes(layer.overlayId);
}

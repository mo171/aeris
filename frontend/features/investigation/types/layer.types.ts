// features/investigation/types/layer.types.ts — the renderable-layer types.
//
// what  : TypeScript types inferred from layer.schema.ts.
// where : Imported by the layer stack, the stage binding hook and every service returning drawables.
// how   : EvidenceLayer is deliberately shaped to satisfy the shared stage contract, StageLayer. That
//         assignability is proven at the call site — use-scene-stage-binding hands an EvidenceLayer array
//         straight to stage.sceneLayers.setLayers — so a drift between the wire format and what the
//         renderer can actually draw is a compile error, with no adapter code to keep in sync.

import type { z } from "zod";

import type {
  colorRampIdSchema,
  comparatorSideSchema,
  evidenceFeatureSchema,
  evidenceLayerSchema,
  featureGeometrySchema,
  layerKindSchema,
  layerProvenanceSchema,
  layerRenderModeSchema,
} from "../schemas/layer.schema";

export type LayerKind = z.infer<typeof layerKindSchema>;
export type LayerRenderMode = z.infer<typeof layerRenderModeSchema>;
export type ComparatorSide = z.infer<typeof comparatorSideSchema>;
export type ColorRampId = z.infer<typeof colorRampIdSchema>;
export type FeatureGeometry = z.infer<typeof featureGeometrySchema>;
export type EvidenceFeature = z.infer<typeof evidenceFeatureSchema>;
export type LayerProvenance = z.infer<typeof layerProvenanceSchema>;
export type EvidenceLayer = z.infer<typeof evidenceLayerSchema>;

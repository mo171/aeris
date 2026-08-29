// features/investigation/schemas/layer.schema.ts — the renderable-layer contract, validated at the boundary.
//
// what  : Zod schemas for an evidence layer descriptor, its geometry features and its provenance block.
// where : Composed by evidence.schema.ts and analysis.schema.ts; parsed by every service that returns
//         something drawable. The inferred type is handed straight to the shared stage.
// how   : A layer is DATA, not a component. Adding a new analysis product — a flood mask, a backscatter
//         difference, a confidence field — means the backend emits one more descriptor and no frontend
//         file changes. That is the single decision that stops this surface from growing linearly with
//         the science behind it.
//
//         Every feature carries magnitude, confidence and area because those are what an analyst reasons
//         about: magnitude drives extrusion height, confidence drives the muted rendering of uncertain
//         regions, and area is what the answer panel quotes. Geometry without them can be drawn but
//         cannot be argued with, so they are required fields rather than optional ones.
//
//         Provenance sits on the layer itself rather than being looked up separately. A layer that cannot
//         say which model version produced it has no business being presented as evidence.

import { z } from "zod";

import { geoBoundingBoxSchema, geoPointSchema } from "@/lib/schemas/geo.schema";

export const layerKindSchema = z.enum([
  "raster-tiles",
  "raster-mask",
  "polygon-vector",
  "point-vector",
  "bbox-vector",
  /** Polygons carrying a value, ramped and extruded by it — contour bands of a continuous surface. */
  "heatmap-surface",
]);

/**
 * Draped classification and extrusion are different Cesium primitives, so this is not a boolean.
 *
 * `classified` colours each feature by its class rather than by the layer, and `heatmap` colours by the
 * measured value. Both are separate modes rather than flags because they change what the colour MEANS,
 * and a renderer that guessed from the data would produce a picture the legend could not describe.
 */
export const layerRenderModeSchema = z.enum(["draped", "extruded", "classified", "heatmap"]);

export const comparatorSideSchema = z.enum(["left", "right", "both"]);

export const colorRampIdSchema = z.enum([
  "true-color",
  "sar-grayscale",
  "change-diverging",
  "index-vegetation",
  "confidence-magma",
  "detection-teal",
  "mask-amber",
  "artefact-neutral",
]);

export const featureGeometrySchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("polygon"), ring: z.array(geoPointSchema).min(3) }),
  z.object({ type: z.literal("point"), position: geoPointSchema }),
  z.object({ type: z.literal("bbox"), bounds: geoBoundingBoxSchema }),
]);

export const evidenceFeatureSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  geometry: featureGeometrySchema,
  /** Zero to one significance. Drives extrusion height and the order evidence blooms in. */
  magnitude: z.number().min(0).max(1),
  /** Null where the model declines to assert one. Never coerced to zero. */
  confidence: z.number().min(0).max(1).nullable(),
  areaHectares: z.number().nonnegative().nullable(),

  /**
   * The measured quantity in the layer's own units — NDVI 0.62, height 34 m, backscatter −12 dB.
   *
   * Deliberately NOT the same field as `magnitude`. Magnitude is normalised significance and answers
   * "how much does this matter"; value is the reading and answers "what does the instrument say". A
   * feature carrying only magnitude can be ranked but never read, which is why nothing could show a ramp
   * scale, a unit or a threshold before this field existed. Null where the product has no scalar.
   */
  value: z.number().nullable(),

  /**
   * Which class this feature belongs to, for categorical products. Null where the product has no classes.
   *
   * An id, never a colour — the backend names the class and the frontend owns the palette, so re-theming
   * never touches a model and a model can never dictate the appearance of the interface.
   */
  classId: z.string().nullable(),
});

export const layerProvenanceSchema = z.object({
  modelId: z.string().min(1),
  modelVersion: z.string().min(1),
  /** Which pipeline stage produced this layer. Links the layer stack to the execution spine. */
  traceStepId: z.string().min(1),
  confidence: z.number().min(0).max(1).nullable(),
});

export const evidenceLayerSchema = z.object({
  id: z.string().min(1),
  kind: layerKindSchema,
  renderMode: layerRenderModeSchema,
  title: z.string().min(1),

  /**
   * Which product this is, as a key into the overlay catalogue.
   *
   * The field that carries MEANING. `colorRampId` below used to do this job as a side effect of choosing
   * a palette, which is why NDVI, NDWI and NDBI all rendered green — three different questions sharing
   * one ramp id. The catalogue entry behind this id supplies the encoding, the units, the legend, the
   * reading thresholds and the stated limitations.
   *
   * Nullable so a build that has not learned about a new product still renders it from its own title and
   * a neutral palette. Refusing to draw an unknown overlay would make every backend deploy a breaking
   * change for the client.
   */
  overlayId: z.string().min(1).nullable(),

  /**
   * The range actually observed in this scene, when it is narrower than the product's theoretical one.
   *
   * NDVI's domain is −1 to +1; this scene's real spread might be 0.1 to 0.7. Ramping across the
   * theoretical domain would waste most of the ramp on values that are not present and flatten every
   * distinction that is. Null falls back to the catalogue's domain.
   */
  valueDomain: z
    .object({ minimum: z.number(), maximum: z.number() })
    .nullable()
    .default(null),

  /** Palette override for this run only. The catalogue supplies the default; this is rarely set. */
  colorRampId: colorRampIdSchema,
  opacity: z.number().min(0).max(1),
  isVisible: z.boolean(),
  comparatorSide: comparatorSideSchema,

  /** Raster layers only. An XYZ template carrying the usual z, x and y placeholders. */
  tileUrlTemplate: z.string().nullable(),
  attribution: z.string().nullable(),
  /**
   * Coverage. Required in practice for rasters: without it Cesium requests tiles across the whole planet
   * and collects 404s from a tiler that only holds one scene. That is the most common first-day failure
   * when wiring a real tile service, so the contract asks for it explicitly.
   */
  bounds: geoBoundingBoxSchema.nullable(),
  minimumZoom: z.number().int().nonnegative().nullable(),
  maximumZoom: z.number().int().nonnegative().nullable(),

  features: z.array(evidenceFeatureSchema),
  provenance: layerProvenanceSchema,
});

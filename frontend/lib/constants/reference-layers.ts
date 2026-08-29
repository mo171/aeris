// lib/constants/reference-layers.ts — the context layers an analyst reads the scene against.
//
// what  : The curated catalogue of reference data available on every investigation — terrain shading,
//         administrative boundaries and the transport network — with where each one comes from and where
//         it sits in the draw order.
// where : Turned into stage layer descriptors by use-reference-layers.ts and listed in the inputs panel.
// how   : REFERENCE IS NOT EVIDENCE, and the separation is the point of this file. An evidence layer is
//         something a model produced and must carry the model, the version and the confidence behind it.
//         A reference layer is context nobody is asserting anything about — a coastline, a district
//         boundary, a road. Keeping them in different structures means a boundary can never be presented
//         as a finding, and an operator can never mistake the basemap for an output.
//
//         Curated here rather than fetched, because which hillshade and whose boundaries are product and
//         licensing decisions, not per-investigation data. They are identical for every area on Earth. If
//         licensing ever has to vary by deployment this becomes an endpoint; until then an endpoint would
//         be a round trip to be told something already known.
//
//         `stackPosition` matters and is easy to get wrong. Hillshade is GROUND: it belongs under the
//         operator's imagery, giving it relief to sit on. Boundaries and roads are ANNOTATION: they belong
//         above the imagery or they are invisible under it. Same file, opposite ends of the stack.

import type { StageColorRampId } from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";

/** Whether a reference layer is ground the imagery sits on, or annotation drawn over it. */
export type ReferenceStackPosition = "under-imagery" | "over-imagery";

export interface ReferenceLayerDefinition {
  id: string;
  title: string;
  /** What it is and when an analyst would reach for it, in their terms. */
  description: string;
  tileUrlTemplate: string;
  attribution: string;
  maximumZoom: number;
  stackPosition: ReferenceStackPosition;
  colorRampId: StageColorRampId;
  /** Opacity it starts at. Annotation layers start below full so they never bury the imagery. */
  defaultOpacity: number;
  /** Only the ones an operator needs on arrival. The rest are one click away. */
  isVisibleByDefault: boolean;
}

const ESRI_ATTRIBUTION = "Esri, HERE, Garmin, USGS, NGA";

export const REFERENCE_LAYERS: readonly ReferenceLayerDefinition[] = [
  {
    id: "reference-hillshade",
    title: "Terrain shading",
    description:
      "Shaded relief under the imagery. Reads slope and landform without exaggerating the terrain, which is what you want when the question is about where water goes or what a site is cut into.",
    tileUrlTemplate:
      "https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}",
    attribution: ESRI_ATTRIBUTION,
    maximumZoom: 16,
    stackPosition: "under-imagery",
    colorRampId: "sar-grayscale",
    defaultOpacity: 1,
    isVisibleByDefault: false,
  },
  {
    id: "reference-boundaries",
    title: "Boundaries & places",
    description:
      "Administrative boundaries and settlement names. Answers which district a detection falls in — the question that turns a polygon into something an authority can act on.",
    tileUrlTemplate:
      "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    attribution: ESRI_ATTRIBUTION,
    maximumZoom: 18,
    stackPosition: "over-imagery",
    colorRampId: "artefact-neutral",
    defaultOpacity: 0.85,
    isVisibleByDefault: false,
  },
  {
    id: "reference-transportation",
    title: "Roads & transport",
    description:
      "The road and rail network. New construction that a road already reaches is a different finding from new construction with no access to it.",
    tileUrlTemplate:
      "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}",
    attribution: ESRI_ATTRIBUTION,
    maximumZoom: 18,
    stackPosition: "over-imagery",
    colorRampId: "artefact-neutral",
    defaultOpacity: 0.75,
    isVisibleByDefault: false,
  },
];

// lib/constants/overlays/overlay-catalogue.ts — everything the system can mask, shade or classify.
//
// what  : The registry of overlay products, keyed by the `overlayId` a layer descriptor carries. Each
//         entry declares how its values are encoded, how it renders, which pipeline stage produced it,
//         how to read it and what it cannot be trusted to say.
// where : The single source of truth behind the legend, the layer stack sections, the overlay browser
//         and the colour the evidence vector layer resolves per feature.
// how   : THIS IS A DICTIONARY OF RENDERING SEMANTICS, NOT A LIST OF LAYERS. The backend still decides
//         what a run produces and emits descriptors for it; this file says what "ndvi" or "land-cover"
//         MEANS when one arrives. Adding a product is one entry here and zero component changes, which is
//         the promise layer.schema.ts already makes and could not previously keep — the legend used to
//         hold a hardcoded map of ramp id to meaning, so every product edited a component.
//
//         `encoding` is the load-bearing field, and there are exactly three shapes a value can take:
//         CONTINUOUS is one number over a domain and reads as more-or-less; CATEGORICAL is one class from
//         a closed set and reads as a different thing entirely; GRADUATED is continuous cut into ordered
//         bands and reads as which-band. Every product ever added is one of the three, so the renderer
//         and the legend each need one branch per shape and never a special case per product.
//
//         `group` decides which section of the layer stack an overlay lands in, and the split is
//         epistemic rather than visual. FINDING and INDEX are asserted by a model and carry provenance.
//         MASK says where nothing can be asserted. STRUCTURE and CONTEXT assert nothing at all — OSM
//         building types are crowd-sourced attributes, so they can inform a question and must never be
//         allowed to support a claim.
//
//         Overlays STACK FREELY. There is deliberately no conflict rule and no forced swap: an analyst
//         may run everything at once, isolate one layer, or hold any combination. `stackHint` exists only
//         to order the draw so a fill does not bury an outline, and it is a rendering detail, never a
//         restriction on what can be visible together.

import type { PipelineStageCode } from "../pipeline-stages";
import type { BinSchemeId } from "./bin-schemes";
import type { ClassPaletteId } from "./class-palettes";
import type { OverlayRampId } from "./color-ramps";
import type { OverlayUnitId } from "./overlay-units";
import { SPECTRAL_INDICES, type SpectralIndexId } from "./spectral-indices";
import { QUALITY_MASKS, type QualityMaskId } from "./quality-masks";

export const OVERLAY_GROUPS = ["finding", "index", "mask", "structure", "context"] as const;
export type OverlayGroup = (typeof OVERLAY_GROUPS)[number];

/** Which section of the layer stack a group belongs to, and what that section is claiming. */
export const OVERLAY_SECTIONS = {
  findings: {
    id: "findings",
    label: "Findings",
    caption: "Asserted by a model. Every one carries the version that produced it.",
    groups: ["finding", "index"] as const,
  },
  masks: {
    id: "masks",
    label: "Masks",
    caption: "Where the answer cannot be trusted, and why.",
    groups: ["mask"] as const,
  },
  context: {
    id: "context",
    label: "Context",
    caption: "The map the findings were made against. Asserts nothing.",
    groups: ["structure", "context"] as const,
  },
} as const;

export type OverlaySectionId = keyof typeof OVERLAY_SECTIONS;

/** How the values on an overlay are shaped. The renderer and the legend branch on exactly this. */
export type OverlayEncoding =
  | {
      kind: "continuous";
      rampId: OverlayRampId;
      /** Theoretical range of the product. The observed range travels on the layer descriptor. */
      domain: { minimum: number; maximum: number };
      unitId: OverlayUnitId;
    }
  | { kind: "categorical"; paletteId: ClassPaletteId }
  | { kind: "graduated"; schemeId: BinSchemeId; unitId: OverlayUnitId };

/**
 * Where an overlay sits in the draw order. Lower numbers draw first, so higher numbers sit on top.
 *
 * Ordering, not exclusion. A continuous surface under an outline is legible; the reverse is a fill that
 * swallows the geometry it is meant to sit behind.
 */
export const OVERLAY_STACK_HINTS = {
  surface: 10,
  region: 20,
  outline: 30,
  marker: 40,
} as const;

export type OverlayStackHint = (typeof OVERLAY_STACK_HINTS)[keyof typeof OVERLAY_STACK_HINTS];

export interface OverlayDefinition {
  id: string;
  label: string;
  group: OverlayGroup;
  /** What it shows and when an analyst reaches for it, in their terms. */
  description: string;
  encoding: OverlayEncoding;
  defaultOpacity: number;
  stackHint: OverlayStackHint;
  /** Masks hatch rather than fill so they can never be misread as a coloured finding. */
  rendersAsHatch: boolean;
  producedBy: PipelineStageCode;
  /** How to read a value. Null where the encoding is self-explanatory, as a class list is. */
  interpretation: string | null;
  /** What this product cannot be trusted to say. Shown wherever a claim rests on it. */
  limitations: readonly string[];
  /** Set where the overlay is an index, linking it to its formula, bands and published caveats. */
  spectralIndexId: SpectralIndexId | null;
  /** Set where the overlay is a validity mask, linking it to what it invalidates. */
  qualityMaskId: QualityMaskId | null;
}

/** Builds the entry for a spectral index so the formula, caveats and thresholds are never restated. */
function indexOverlay(
  indexId: SpectralIndexId,
  rampId: OverlayRampId,
  overrides: Partial<OverlayDefinition> = {},
): OverlayDefinition {
  const index = SPECTRAL_INDICES[indexId];
  const readableBand = index.interpretation[index.interpretation.length - 1];

  return {
    id: indexId,
    label: `${index.label} · ${index.fullName.split(" ").slice(-1)[0].toLowerCase()}`,
    group: "index",
    description: index.meaning,
    encoding: { kind: "continuous", rampId, domain: index.domain, unitId: "index" },
    defaultOpacity: 0.78,
    stackHint: OVERLAY_STACK_HINTS.surface,
    rendersAsHatch: false,
    producedBy: "S12",
    interpretation: `${readableBand.from} to ${readableBand.to} = ${readableBand.label.toLowerCase()}`,
    limitations: index.limitations,
    spectralIndexId: indexId,
    qualityMaskId: null,
    ...overrides,
  };
}

/** Builds the entry for a validity mask so severity and remedy live in one place. */
function maskOverlay(maskId: QualityMaskId, overrides: Partial<OverlayDefinition> = {}): OverlayDefinition {
  const mask = QUALITY_MASKS[maskId];

  return {
    id: `mask-${maskId}`,
    label: mask.label,
    group: "mask",
    description: mask.description,
    encoding: { kind: "categorical", paletteId: "mask-severity" },
    defaultOpacity: 0.6,
    stackHint: OVERLAY_STACK_HINTS.region,
    rendersAsHatch: true,
    producedBy: mask.producedBy,
    interpretation: mask.invalidates,
    limitations: [],
    spectralIndexId: null,
    qualityMaskId: maskId,
    ...overrides,
  };
}

const OVERLAY_LIST: readonly OverlayDefinition[] = [
  // ── Findings — a model asserted these ──────────────────────────────────────────────────────────
  {
    id: "change-mask",
    label: "Change mask",
    group: "finding",
    description:
      "Where the ground differs between the baseline and the comparison, with each region scored by how much of it changed.",
    encoding: { kind: "graduated", schemeId: "change-intensity", unitId: "percentage" },
    defaultOpacity: 0.55,
    stackHint: OVERLAY_STACK_HINTS.region,
    rendersAsHatch: false,
    producedBy: "S13",
    interpretation: "Banded by how much of the region changed, not by what it changed into.",
    limitations: [
      "Seasonal difference between the two dates can present as change — check the pair advisory.",
      "Misregistration along edges produces change that is not on the ground.",
    ],
    spectralIndexId: null,
    qualityMaskId: null,
  },
  {
    id: "change-magnitude",
    label: "Change magnitude",
    group: "finding",
    description:
      "The same comparison read as a continuous surface rather than banded, for judging where change is concentrated.",
    encoding: {
      kind: "continuous",
      rampId: "change-diverging",
      domain: { minimum: -1, maximum: 1 },
      unitId: "ratio",
    },
    defaultOpacity: 0.7,
    stackHint: OVERLAY_STACK_HINTS.surface,
    rendersAsHatch: false,
    producedBy: "S13",
    interpretation: "Teal is gain, amber is loss, neutral slate is no measurable difference.",
    limitations: ["Direction is only meaningful where both dates observed the surface."],
    spectralIndexId: null,
    qualityMaskId: null,
  },
  {
    id: "detected-objects",
    label: "Detected objects",
    group: "finding",
    description: "Discrete objects the detector found, each outlined and classified.",
    encoding: { kind: "categorical", paletteId: "object-class" },
    defaultOpacity: 0.9,
    stackHint: OVERLAY_STACK_HINTS.outline,
    rendersAsHatch: false,
    producedBy: "S13",
    interpretation: null,
    limitations: ["Detection recall falls sharply below the resolution each class needs."],
    spectralIndexId: null,
    qualityMaskId: null,
  },
  {
    id: "detection-density",
    label: "Detection density",
    group: "finding",
    description:
      "Where detections concentrate, as a surface. Answers whether activity is one site or scattered across the area.",
    encoding: { kind: "graduated", schemeId: "detection-density", unitId: "per-square-kilometer" },
    defaultOpacity: 0.72,
    stackHint: OVERLAY_STACK_HINTS.surface,
    rendersAsHatch: false,
    producedBy: "S15",
    interpretation: "Bands are counts per square kilometre, computed on the analysis grid.",
    limitations: ["Density inherits every false positive in the detections beneath it."],
    spectralIndexId: null,
    qualityMaskId: null,
  },
  {
    id: "land-cover",
    label: "Land cover",
    group: "finding",
    description: "Every pixel classified into a land-cover class, with the share of the area each covers.",
    encoding: { kind: "categorical", paletteId: "land-cover" },
    defaultOpacity: 0.62,
    stackHint: OVERLAY_STACK_HINTS.region,
    rendersAsHatch: false,
    producedBy: "S13",
    interpretation: null,
    limitations: [
      "Class boundaries are mixed pixels at 10 m — a shoreline is a band, not a line.",
      "Bare soil and built-up are the pair most often confused.",
    ],
    spectralIndexId: null,
    qualityMaskId: null,
  },
  {
    id: "water-extent",
    label: "Water extent",
    group: "finding",
    description: "Open water at the comparison date, classified as permanent, newly inundated or receded.",
    encoding: { kind: "categorical", paletteId: "water-state" },
    defaultOpacity: 0.65,
    stackHint: OVERLAY_STACK_HINTS.region,
    rendersAsHatch: false,
    producedBy: "S13",
    interpretation: null,
    limitations: [
      "Turbid and very shallow water is ambiguous to every index.",
      "A seasonal cycle can present as inundation unless the pair is season-matched.",
    ],
    spectralIndexId: null,
    qualityMaskId: null,
  },
  {
    id: "water-change",
    label: "Water change",
    group: "finding",
    description:
      "Gain and loss of open water between the two dates, as a signed surface. Flood and drawdown are opposite findings and never share a colour.",
    encoding: {
      kind: "continuous",
      rampId: "water-change-diverging",
      domain: { minimum: -1, maximum: 1 },
      unitId: "ratio",
    },
    defaultOpacity: 0.72,
    stackHint: OVERLAY_STACK_HINTS.surface,
    rendersAsHatch: false,
    producedBy: "S13",
    interpretation: "Blue is water gained, amber is water lost, neutral slate is unchanged.",
    limitations: ["Requires a season-matched pair, or a normal cycle reads as an event."],
    spectralIndexId: null,
    qualityMaskId: null,
  },
  {
    id: "backscatter",
    label: "SAR backscatter",
    group: "finding",
    description:
      "Radar return strength. Responds to surface roughness and structure rather than colour, and is unaffected by cloud.",
    encoding: {
      kind: "continuous",
      rampId: "backscatter-grayscale",
      domain: { minimum: -25, maximum: 5 },
      unitId: "decibels",
    },
    defaultOpacity: 0.85,
    stackHint: OVERLAY_STACK_HINTS.surface,
    rendersAsHatch: false,
    producedBy: "S13",
    interpretation: "Bright is rough or structured; dark is smooth — or unseen, which the shadow mask separates.",
    limitations: [
      "Speckle is inherent and is not texture.",
      "Layover and shadow make some terrain unreadable — check the radar masks.",
    ],
    spectralIndexId: null,
    qualityMaskId: null,
  },
  {
    id: "model-confidence",
    label: "Model confidence",
    group: "finding",
    description: "How confident the model is across the area, rather than per finding.",
    encoding: {
      kind: "continuous",
      rampId: "confidence-magma",
      domain: { minimum: 0, maximum: 1 },
      unitId: "percentage",
    },
    defaultOpacity: 0.6,
    stackHint: OVERLAY_STACK_HINTS.surface,
    rendersAsHatch: false,
    producedBy: "S15",
    interpretation: "Dim regions are where the model is least sure, not where nothing happened.",
    limitations: ["Confidence is the model's own estimate and is not a probability of being correct."],
    spectralIndexId: null,
    qualityMaskId: null,
  },

  // ── Indices — closed-form band arithmetic, from the design document ────────────────────────────
  indexOverlay("ndvi", "vegetation-sequential"),
  indexOverlay("evi", "vegetation-sequential"),
  indexOverlay("savi", "vegetation-sequential"),
  indexOverlay("ndwi", "water-sequential"),
  indexOverlay("mndwi", "water-sequential"),
  indexOverlay("ndbi", "built-up-sequential"),
  indexOverlay("nbr", "burn-severity", {
    encoding: { kind: "graduated", schemeId: "burn-severity-bands", unitId: "index" },
    interpretation: "Banded to the severity classes used in published burn practice.",
  }),

  // ── Masks — where nothing can be asserted ──────────────────────────────────────────────────────
  maskOverlay("cloud"),
  maskOverlay("cloud-shadow"),
  maskOverlay("no-data"),
  maskOverlay("co-registration", { stackHint: OVERLAY_STACK_HINTS.marker }),
  maskOverlay("sar-layover"),
  maskOverlay("sar-shadow"),

  // ── Structure and context — assert nothing, carry no provenance ────────────────────────────────
  {
    id: "building-footprints",
    label: "Buildings by type",
    group: "structure",
    description:
      "Mapped building footprints coloured by what the building is. Context for a finding, never evidence for one.",
    encoding: { kind: "categorical", paletteId: "building-type" },
    defaultOpacity: 0.9,
    stackHint: OVERLAY_STACK_HINTS.region,
    rendersAsHatch: false,
    producedBy: "S15",
    interpretation: null,
    limitations: [
      "Types are crowd-sourced attributes, not a model output — many footprints carry none.",
      "Coverage is uneven between cities and can be years out of date.",
    ],
    spectralIndexId: null,
    qualityMaskId: null,
  },
  {
    id: "building-height",
    label: "Buildings by height",
    group: "structure",
    description:
      "The same footprints banded by height. Separates a warehouse district from a tower cluster at a glance.",
    encoding: { kind: "graduated", schemeId: "building-height", unitId: "meters" },
    defaultOpacity: 0.9,
    stackHint: OVERLAY_STACK_HINTS.region,
    rendersAsHatch: false,
    producedBy: "S15",
    interpretation: "Bands are storey ranges. Heights are estimates where a survey value is absent.",
    limitations: ["Most heights are estimated from storey counts rather than measured."],
    spectralIndexId: null,
    qualityMaskId: null,
  },
  {
    id: "terrain-relief",
    label: "Terrain relief",
    group: "context",
    description: "Ground height, for reading what a site is cut into and where water would run.",
    encoding: {
      kind: "continuous",
      rampId: "elevation-terrain",
      domain: { minimum: 0, maximum: 3000 },
      unitId: "meters",
    },
    defaultOpacity: 1,
    stackHint: OVERLAY_STACK_HINTS.surface,
    rendersAsHatch: false,
    producedBy: "S8",
    interpretation: null,
    limitations: [],
    spectralIndexId: null,
    qualityMaskId: null,
  },
];

export const OVERLAY_CATALOGUE: Readonly<Record<string, OverlayDefinition>> = Object.fromEntries(
  OVERLAY_LIST.map((overlay) => [overlay.id, overlay]),
);

export const OVERLAY_IDS: readonly string[] = OVERLAY_LIST.map((overlay) => overlay.id);

/**
 * The definition for an overlay id, or null when the backend sends one this build does not know.
 *
 * Null rather than a throw, and callers fall back to the layer's own title and a neutral palette. A
 * product the frontend has not learned about yet must still draw — refusing to render an unknown layer
 * would make every backend deployment a breaking change for the client.
 */
export function findOverlay(overlayId: string | null | undefined): OverlayDefinition | null {
  return overlayId ? (OVERLAY_CATALOGUE[overlayId] ?? null) : null;
}

/** Which stack section an overlay belongs to. Unknown overlays are treated as findings, not hidden. */
export function sectionForOverlay(overlayId: string | null | undefined): OverlaySectionId {
  const overlay = findOverlay(overlayId);
  if (!overlay) {
    return "findings";
  }

  for (const section of Object.values(OVERLAY_SECTIONS)) {
    if ((section.groups as readonly OverlayGroup[]).includes(overlay.group)) {
      return section.id;
    }
  }
  return "findings";
}

export function overlaysInGroup(group: OverlayGroup): readonly OverlayDefinition[] {
  return OVERLAY_LIST.filter((overlay) => overlay.group === group);
}

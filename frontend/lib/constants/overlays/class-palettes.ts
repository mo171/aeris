// lib/constants/overlays/class-palettes.ts — categorical class sets and the colour each class owns.
//
// what  : The closed vocabularies a classified overlay draws from — land cover, building type, water
//         state and detected object class — each class carrying an id, a label, a colour and what it
//         actually means on the ground.
// where : Bound to a product by the overlay catalogue; resolved per feature by the evidence vector layer
//         via `classId`, and listed as swatches by the legend.
// how   : CATEGORICAL IS NOT CONTINUOUS, and conflating them is the mistake this file exists to prevent.
//         A ramp says "more of this"; a class set says "a different thing". Land cover has no order —
//         water is not more than forest — so it must never be drawn with a ramp, or the picture asserts a
//         ranking the data does not contain.
//
//         The class ids are the wire contract. The backend sends `classId: "built-up"`, never a colour,
//         so re-theming the application never touches a model and a model can never dictate the palette.
//         An unrecognised class id is rendered in the neutral fallback rather than dropped — an operator
//         seeing an unlabelled region and asking about it is a far better failure than silently
//         disappearing part of a classification.
//
//         Colours are chosen for SEPARABILITY first and mnemonics second: water reads blue and vegetation
//         green because fighting that costs the operator a lookup on every glance, but the remaining
//         classes are spaced around the wheel rather than shaded, because neighbouring hues in a
//         categorical set are read as related when they are not.

import { AERIS_COLOR_HEX } from "../theme";

export const CLASS_PALETTE_IDS = [
  "land-cover",
  "building-type",
  "water-state",
  "object-class",
  "mask-severity",
] as const;

export type ClassPaletteId = (typeof CLASS_PALETTE_IDS)[number];

export interface OverlayClass {
  id: string;
  label: string;
  color: string;
  /** What this class means on the ground, for the legend tooltip and the agent's tool description. */
  description: string;
}

export interface ClassPalette {
  id: ClassPaletteId;
  label: string;
  classes: readonly OverlayClass[];
}

/** Drawn for any `classId` the palette does not contain. Visible and obviously unclassified. */
export const UNKNOWN_CLASS: OverlayClass = {
  id: "unknown",
  label: "Unclassified",
  color: AERIS_COLOR_HEX.grayDim,
  description: "The model returned a class this build does not recognise.",
};

export const CLASS_PALETTES: Readonly<Record<ClassPaletteId, ClassPalette>> = {
  "land-cover": {
    id: "land-cover",
    label: "Land cover",
    classes: [
      {
        id: "water",
        label: "Water",
        color: AERIS_COLOR_HEX.blue,
        description: "Open water — rivers, lakes, reservoirs, coastal margin.",
      },
      {
        id: "vegetation",
        label: "Vegetation",
        color: AERIS_COLOR_HEX.green,
        description: "Live canopy: forest, plantation, dense scrub.",
      },
      {
        id: "cropland",
        label: "Cropland",
        color: "#8FBF3F",
        description: "Cultivated land. Separated from vegetation because its cycle is seasonal and human.",
      },
      {
        id: "built-up",
        label: "Built-up",
        color: AERIS_COLOR_HEX.amber,
        description: "Constructed surface — buildings, hardstanding, sealed ground.",
      },
      {
        id: "bare-soil",
        label: "Bare soil",
        color: "#A78B6A",
        description: "Exposed earth. The class most often confused with built-up by NDBI alone.",
      },
      {
        id: "rock",
        label: "Rock & sand",
        color: "#C8BCA6",
        description: "Bedrock, desert pavement, sand. Bright and spectrally flat.",
      },
      {
        id: "wetland",
        label: "Wetland",
        color: "#4FA3A0",
        description: "Saturated ground and seasonal marsh — reads as neither land nor open water.",
      },
      {
        id: "snow-ice",
        label: "Snow & ice",
        color: "#E4F1FA",
        description: "Permanent or seasonal cryosphere cover.",
      },
      {
        id: "cloud",
        label: "Cloud",
        color: AERIS_COLOR_HEX.gray,
        description: "Obscured. Present in the class list so obscuration is reported, never guessed past.",
      },
    ],
  },

  "building-type": {
    id: "building-type",
    label: "Building type",
    classes: [
      {
        id: "residential",
        label: "Residential",
        color: "#7FA8D9",
        description: "Housing. The bulk of most urban footprints.",
      },
      {
        id: "commercial",
        label: "Commercial",
        color: AERIS_COLOR_HEX.teal,
        description: "Retail and offices — the class that shifts first when an area gentrifies.",
      },
      {
        id: "industrial",
        label: "Industrial",
        color: AERIS_COLOR_HEX.amber,
        description: "Plant, warehousing, refinery. Large footprints, low roof complexity.",
      },
      {
        id: "civic",
        label: "Civic & institutional",
        color: "#B48FD9",
        description: "Schools, hospitals, government. What an authority needs located during a response.",
      },
      {
        id: "agricultural",
        label: "Agricultural",
        color: "#8FBF3F",
        description: "Barns, silos, glasshouses — rural structures that are not dwellings.",
      },
      {
        id: "unspecified",
        label: "Unspecified",
        color: AERIS_COLOR_HEX.grayDim,
        description: "Mapped as a building with no type recorded. Common in crowd-sourced footprints.",
      },
    ],
  },

  "water-state": {
    id: "water-state",
    label: "Water state",
    classes: [
      {
        id: "permanent",
        label: "Permanent water",
        color: AERIS_COLOR_HEX.blue,
        description: "Present in both observations. The baseline the change is measured against.",
      },
      {
        id: "gained",
        label: "Newly inundated",
        color: "#38BDF8",
        description: "Absent before, present now — flooding, reservoir fill, channel migration.",
      },
      {
        id: "lost",
        label: "Receded",
        color: AERIS_COLOR_HEX.amber,
        description: "Present before, absent now — drawdown, drought, drainage.",
      },
      {
        id: "seasonal",
        label: "Seasonal",
        color: "#4FA3A0",
        description: "Known to alternate. Flagged so a normal cycle is not reported as an event.",
      },
    ],
  },

  /**
   * Masks are classified by what they COST an answer, not by what they are made of.
   *
   * A cloud and a radar shadow are different phenomena but the same instruction to the analyst: nothing
   * can be read here. Colouring by severity puts that instruction in the picture, where colouring by
   * phenomenon would leave the operator to work out which obscuration matters.
   */
  "mask-severity": {
    id: "mask-severity",
    label: "Mask severity",
    classes: [
      {
        id: "blocking",
        label: "Blocking",
        color: AERIS_COLOR_HEX.amber,
        description: "The surface was not observed. No claim inside this region can be made.",
      },
      {
        id: "degrading",
        label: "Degrading",
        color: AERIS_COLOR_HEX.gray,
        description: "Observed, but distorted. Claims here carry a stated caveat.",
      },
      {
        id: "advisory",
        label: "Advisory",
        color: AERIS_COLOR_HEX.grayDim,
        description: "Worth knowing; does not change the reading.",
      },
    ],
  },

  "object-class": {
    id: "object-class",
    label: "Detected object",
    classes: [
      {
        id: "building",
        label: "Building",
        color: AERIS_COLOR_HEX.teal,
        description: "A discrete structure with a roof footprint.",
      },
      {
        id: "vehicle",
        label: "Vehicle",
        color: "#38BDF8",
        description: "Road vehicle. Requires sub-metre resolution to be meaningful.",
      },
      {
        id: "vessel",
        label: "Vessel",
        color: "#B48FD9",
        description: "Ship or boat, including wake where the detector reports one.",
      },
      {
        id: "aircraft",
        label: "Aircraft",
        color: "#F0ABFC",
        description: "Airframe on apron or runway.",
      },
      {
        id: "storage-tank",
        label: "Storage tank",
        color: AERIS_COLOR_HEX.amber,
        description: "Circular bulk storage. Roof height also indicates fill level.",
      },
      {
        id: "infrastructure",
        label: "Infrastructure",
        color: "#8FBF3F",
        description: "Fixed plant — pylons, towers, cranes, bridges.",
      },
    ],
  },
};

/** Resolves a class id against a palette, falling back to the visible unknown class. Never throws. */
export function resolveOverlayClass(paletteId: ClassPaletteId, classId: string | null): OverlayClass {
  if (!classId) {
    return UNKNOWN_CLASS;
  }
  return CLASS_PALETTES[paletteId].classes.find((entry) => entry.id === classId) ?? UNKNOWN_CLASS;
}

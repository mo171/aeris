// lib/constants/overlays/building-attribution.ts — reading a building tileset's own attributes.
//
// what  : Which properties the OSM building tileset carries, how its `building` tag values map onto our
//         building-type classes, and the three ways the massing can be coloured.
// where : Turned into a Cesium3DTileStyle by geoStage/cesium-runtime.ts; the mode is chosen from the
//         camera controls and held in the investigation store.
// how   : The massing tileset is ALREADY LOADED and already carries per-feature attributes — a building
//         tag and an estimated height. Colouring by them costs one style expression and no extra request,
//         which is why "different types of building, different increments" is a styling change rather
//         than a data pipeline.
//
//         THIS IS CONTEXT, NOT EVIDENCE, and the distinction is load-bearing rather than pedantic. These
//         are crowd-sourced attributes with uneven coverage that can be years stale — nothing here was
//         asserted by a model against imagery. A building type can inform a question ("is this an
//         industrial district?") and must never be allowed to support a claim, which is why the overlays
//         it drives sit in the `structure` group with no provenance block.
//
//         The tag mapping is deliberately incomplete and ends in a fallback. OSM's building key has
//         hundreds of values and grows; enumerating them would be a losing race, and an unmapped tag
//         landing in "Unspecified" is honest, whereas guessing at it would invent a classification.

import { BIN_SCHEMES } from "./bin-schemes";
import type { OverlayClass } from "./class-palettes";
import { CLASS_PALETTES } from "./class-palettes";

/** Feature properties the Cesium OSM Buildings tileset exposes. Read by the style expressions. */
export const OSM_BUILDING_PROPERTIES = {
  /** The OSM `building` tag. Often the literal string "yes", which carries no type at all. */
  type: "building",
  /** Cesium's own estimate, in metres. Derived from storey count where no survey height exists. */
  estimatedHeight: "cesium#estimatedHeight",
} as const;

/** How the massing is coloured. `uniform` is the existing flat slate and stays the default. */
export const BUILDING_STYLE_IDS = ["uniform", "type", "height"] as const;
export type BuildingStyleId = (typeof BUILDING_STYLE_IDS)[number];

export interface BuildingStyleOption {
  id: BuildingStyleId;
  label: string;
  /** What the colour is encoding, in one line, for the control's hint. */
  hint: string;
  /** Catalogue key whose legend describes this styling. Null for uniform, which encodes nothing. */
  overlayId: string | null;
}

export const BUILDING_STYLE_OPTIONS: readonly BuildingStyleOption[] = [
  {
    id: "uniform",
    label: "Plain",
    hint: "One tone. Buildings are shape and shadow only, so nothing competes with the evidence.",
    overlayId: null,
  },
  {
    id: "type",
    label: "By type",
    hint: "Coloured by what the building is — residential, commercial, industrial, civic.",
    overlayId: "building-footprints",
  },
  {
    id: "height",
    label: "By height",
    hint: "Banded by height, so a warehouse district separates from a tower cluster at a glance.",
    overlayId: "building-height",
  },
];

/**
 * OSM `building` tag values grouped onto our classes.
 *
 * Ordered most specific first within each group, because the style expression evaluates in order and an
 * early broad match would swallow a later precise one.
 */
export const OSM_BUILDING_TAG_CLASSES: Readonly<Record<string, readonly string[]>> = {
  residential: [
    "residential",
    "apartments",
    "house",
    "detached",
    "semidetached_house",
    "terrace",
    "bungalow",
    "dormitory",
    "hut",
  ],
  commercial: ["commercial", "retail", "office", "supermarket", "kiosk", "hotel"],
  industrial: ["industrial", "warehouse", "factory", "manufacture", "hangar", "silo", "storage_tank"],
  civic: [
    "civic",
    "government",
    "public",
    "school",
    "university",
    "college",
    "kindergarten",
    "hospital",
    "church",
    "mosque",
    "temple",
    "cathedral",
    "train_station",
    "transportation",
    "stadium",
  ],
  agricultural: ["farm", "farm_auxiliary", "barn", "cowshed", "greenhouse", "stable"],
};

/** The class a building tag belongs to, with its colour. Unmapped tags land in "Unspecified". */
export function classForBuildingTag(tag: string | null): OverlayClass {
  const palette = CLASS_PALETTES["building-type"];
  const fallback = palette.classes[palette.classes.length - 1];

  if (!tag) {
    return fallback;
  }

  const matchedClassId = Object.entries(OSM_BUILDING_TAG_CLASSES).find(([, tags]) =>
    tags.includes(tag),
  )?.[0];

  return palette.classes.find((entry) => entry.id === matchedClassId) ?? fallback;
}

/** The height bands, as the building-height scheme defines them. Re-exported so the style reads one list. */
export const BUILDING_HEIGHT_SCHEME = BIN_SCHEMES["building-height"];

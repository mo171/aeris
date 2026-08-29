// lib/constants/overlays/index.ts — the one import path into the overlay catalogue.
//
// what  : Re-exports every overlay vocabulary — the registry, the three encodings' lookup tables, the
//         spectral indices, the quality masks and the unit formatting.
// where : Imported by the geoStage layer renderers, the legend, the layer stack, the overlay browser and
//         the mock generator. Nothing outside this folder reaches past the barrel into a member file.
// how   : One entry point so the folder can be reorganised without a repo-wide import rewrite, and so
//         the catalogue reads as a single vocabulary rather than seven loose constant files. Types are
//         re-exported alongside values because almost every consumer needs both.

export {
  COLOR_RAMPS,
  OVERLAY_RAMP_IDS,
  mixHexColors,
  rampToCssGradient,
  sampleRamp,
  type ColorRamp,
  type OverlayRampId,
  type RampStop,
} from "./color-ramps";

export {
  CLASS_PALETTES,
  CLASS_PALETTE_IDS,
  UNKNOWN_CLASS,
  resolveOverlayClass,
  type ClassPalette,
  type ClassPaletteId,
  type OverlayClass,
} from "./class-palettes";

export {
  BUILDING_HEIGHT_SCHEME,
  BUILDING_STYLE_IDS,
  BUILDING_STYLE_OPTIONS,
  OSM_BUILDING_PROPERTIES,
  OSM_BUILDING_TAG_CLASSES,
  classForBuildingTag,
  type BuildingStyleId,
  type BuildingStyleOption,
} from "./building-attribution";

export {
  BIN_SCHEMES,
  BIN_SCHEME_IDS,
  binIndexForValue,
  binRampPosition,
  type Bin,
  type BinScheme,
  type BinSchemeId,
} from "./bin-schemes";

export {
  SPECTRAL_INDICES,
  SPECTRAL_INDEX_IDS,
  interpretIndexValue,
  type IndexInterpretationBand,
  type SpectralBand,
  type SpectralIndex,
  type SpectralIndexId,
} from "./spectral-indices";

export {
  MASK_SEVERITY_COPY,
  MASK_SEVERITY_ORDER,
  QUALITY_MASKS,
  QUALITY_MASK_IDS,
  type MaskSeverity,
  type QualityMask,
  type QualityMaskId,
} from "./quality-masks";

export {
  OVERLAY_UNITS,
  OVERLAY_UNIT_IDS,
  formatOverlayValue,
  type OverlayUnit,
  type OverlayUnitId,
} from "./overlay-units";

export {
  OVERLAY_CATALOGUE,
  OVERLAY_GROUPS,
  OVERLAY_IDS,
  OVERLAY_SECTIONS,
  OVERLAY_STACK_HINTS,
  findOverlay,
  overlaysInGroup,
  sectionForOverlay,
  type OverlayDefinition,
  type OverlayEncoding,
  type OverlayGroup,
  type OverlaySectionId,
  type OverlayStackHint,
} from "./overlay-catalogue";

// lib/constants/overlays/spectral-indices.ts — the seven indices, with what their numbers mean.
//
// what  : NDVI, EVI, SAVI, NDWI, MNDWI, NDBI and NBR — formula, required bands, physical meaning, the
//         value bands that make a reading interpretable, and the stated limitations of each.
// where : Read by the overlay catalogue (an index product binds to an entry here), by
//         analysis-operations.ts so an operation and its output share one definition, and by the answer
//         panel when a claim rests on an index and must carry its caveat.
// how   : Transcribed from §3.3 of the project design document. Not invented, not paraphrased from
//         memory — the formulas, the Sentinel-2 band mappings and the limitations are the ones the
//         system was specified against, so this file and the backend's index engine describe the same
//         computation. Where a threshold is stated ("dense healthy vegetation typically > 0.4") it is
//         reproduced rather than rounded.
//
//         THE INTERPRETATION BANDS ARE THE POINT OF THE FILE. A legend that says "green means high NDVI"
//         has told the operator nothing they could not see; "above 0.4 is dense healthy canopy, below
//         zero is water" is what lets them answer "is the ground fertile" without leaving the workspace.
//         That single sentence is the difference between a coloured picture and an instrument.
//
//         `limitations` is not documentation. The design document is explicit that NDVI saturates over
//         dense canopy and that NDBI confuses bare soil with buildings, and a system that renders a
//         built-up map without saying so is overclaiming. Any claim resting on an index shows these.

/** Sentinel-2 band identifiers, kept as the canonical naming the design document uses. */
export type SpectralBand = "Blue" | "Green" | "Red" | "NIR" | "SWIR1" | "SWIR2";

export const SPECTRAL_INDEX_IDS = ["ndvi", "evi", "savi", "ndwi", "mndwi", "ndbi", "nbr"] as const;

export type SpectralIndexId = (typeof SPECTRAL_INDEX_IDS)[number];

/** One readable band of an index's range, and what a value inside it indicates on the ground. */
export interface IndexInterpretationBand {
  from: number;
  to: number;
  label: string;
  meaning: string;
}

export interface SpectralIndex {
  id: SpectralIndexId;
  /** Short form as an analyst says it. */
  label: string;
  fullName: string;
  /** Written as it appears in the design document, in plain text so it renders anywhere. */
  formula: string;
  /** The same formula in Sentinel-2 band numbers, which is what an operator checks against metadata. */
  sentinel2Formula: string;
  requiredBands: readonly SpectralBand[];
  /** The physics. Why the arithmetic separates what it separates. */
  meaning: string;
  /** Theoretical range. The observed range in a given scene is narrower and travels on the layer. */
  domain: { minimum: number; maximum: number };
  /** The question an operator would type to get this. Keeps the typed and named routes converging. */
  typicalQuery: string;
  interpretation: readonly IndexInterpretationBand[];
  /** Reproduced from the design document. Shown wherever a claim rests on this index. */
  limitations: readonly string[];
}

export const SPECTRAL_INDICES: Readonly<Record<SpectralIndexId, SpectralIndex>> = {
  ndvi: {
    id: "ndvi",
    label: "NDVI",
    fullName: "Normalised Difference Vegetation Index",
    formula: "(NIR − Red) / (NIR + Red)",
    sentinel2Formula: "(B08 − B04) / (B08 + B04)",
    requiredBands: ["NIR", "Red"],
    meaning:
      "Healthy vegetation absorbs red light and reflects near-infrared strongly, so the ratio separates live canopy from bare ground.",
    domain: { minimum: -1, maximum: 1 },
    typicalQuery: "Show me areas with unhealthy vegetation.",
    interpretation: [
      { from: -1, to: 0, label: "Water", meaning: "Open water and deep shadow return negative values." },
      { from: 0, to: 0.2, label: "Bare or built", meaning: "Soil, rock, sand and constructed surfaces." },
      { from: 0.2, to: 0.4, label: "Sparse vegetation", meaning: "Stressed canopy, senescent crop, or thin cover over soil." },
      { from: 0.4, to: 1, label: "Dense healthy vegetation", meaning: "Vigorous canopy — the threshold the design document names." },
    ],
    limitations: [
      "Saturates over dense canopy, so the strongest growth is understated.",
      "Sensitive to soil background and atmospheric state.",
      "Not directly comparable across sensors without calibration.",
    ],
  },

  evi: {
    id: "evi",
    label: "EVI",
    fullName: "Enhanced Vegetation Index",
    formula: "2.5 × (NIR − Red) / (NIR + 6·Red − 7.5·Blue + 1)",
    sentinel2Formula: "2.5 × (B08 − B04) / (B08 + 6·B04 − 7.5·B02 + 1)",
    requiredBands: ["NIR", "Red", "Blue"],
    meaning:
      "Like NDVI but corrects for aerosol and soil effects, and resists the saturation NDVI suffers in high-biomass areas.",
    domain: { minimum: -1, maximum: 1 },
    typicalQuery: "Compare vegetation vigour between these dates.",
    interpretation: [
      { from: -1, to: 0.2, label: "Non-vegetated", meaning: "Water, bare ground or built surface." },
      { from: 0.2, to: 0.5, label: "Moderate vigour", meaning: "Established but not dense canopy." },
      { from: 0.5, to: 1, label: "High vigour", meaning: "High biomass, where EVI still discriminates and NDVI has flattened." },
    ],
    limitations: [
      "Needs the blue band, so it is unavailable on sensors without one.",
      "Coefficients are empirical and MODIS-derived rather than universal.",
      "Can be noisy in arid regions.",
    ],
  },

  savi: {
    id: "savi",
    label: "SAVI",
    fullName: "Soil-Adjusted Vegetation Index",
    formula: "(1 + L) × (NIR − Red) / (NIR + Red + L), L = 0.5",
    sentinel2Formula: "1.5 × (B08 − B04) / (B08 + B04 + 0.5)",
    requiredBands: ["NIR", "Red"],
    meaning:
      "NDVI with a soil-brightness correction factor, which makes it the better reading over sparse vegetation and exposed soil.",
    domain: { minimum: -1, maximum: 1 },
    typicalQuery: "Vegetation cover in this semi-arid region?",
    interpretation: [
      { from: -1, to: 0.1, label: "Bare", meaning: "Soil dominates the pixel." },
      { from: 0.1, to: 0.35, label: "Sparse cover", meaning: "The band SAVI exists to read, where NDVI is distorted by soil." },
      { from: 0.35, to: 1, label: "Established cover", meaning: "Canopy is the dominant signal." },
    ],
    limitations: [
      "The L factor is scene-dependent; 0.5 is a typical value, not a correct one.",
      "Still saturates at high biomass.",
    ],
  },

  ndwi: {
    id: "ndwi",
    label: "NDWI",
    fullName: "Normalised Difference Water Index",
    formula: "(Green − NIR) / (Green + NIR)",
    sentinel2Formula: "(B03 − B08) / (B03 + B08)",
    requiredBands: ["Green", "NIR"],
    meaning:
      "Open water reflects green and absorbs near-infrared, so positive values indicate water.",
    domain: { minimum: -1, maximum: 1 },
    typicalQuery: "Where are the water bodies?",
    interpretation: [
      { from: -1, to: 0, label: "Land", meaning: "No open water in the pixel." },
      { from: 0, to: 0.3, label: "Wet or mixed", meaning: "Saturated ground, shallow margin, or a mixed shoreline pixel." },
      { from: 0.3, to: 1, label: "Open water", meaning: "Confidently water." },
    ],
    limitations: [
      "Confounded by built-up land and wet soil.",
      "McFeeters NDWI is not ideal over mixed urban and water scenes — prefer MNDWI there.",
    ],
  },

  mndwi: {
    id: "mndwi",
    label: "MNDWI",
    fullName: "Modified Normalised Difference Water Index",
    formula: "(Green − SWIR) / (Green + SWIR)",
    sentinel2Formula: "(B03 − B11) / (B03 + B11)",
    requiredBands: ["Green", "SWIR1"],
    meaning:
      "Suppresses built-up noise, which makes it the standard choice for water extraction in urbanised scenes.",
    domain: { minimum: -1, maximum: 1 },
    typicalQuery: "Map flood extent.",
    interpretation: [
      { from: -1, to: 0, label: "Land", meaning: "Including built-up surfaces that NDWI would misread as wet." },
      { from: 0, to: 0.3, label: "Shallow or turbid", meaning: "Water present but ambiguous — sediment load or very shallow." },
      { from: 0.3, to: 1, label: "Open water", meaning: "Robust water detection, including flood extent." },
    ],
    limitations: [
      "Needs SWIR, which is 20 m on Sentinel-2 and must be resampled to the analysis grid.",
      "Turbid or shallow water remains ambiguous.",
    ],
  },

  ndbi: {
    id: "ndbi",
    label: "NDBI",
    fullName: "Normalised Difference Built-up Index",
    formula: "(SWIR − NIR) / (SWIR + NIR)",
    sentinel2Formula: "(B11 − B08) / (B11 + B08)",
    requiredBands: ["SWIR1", "NIR"],
    meaning:
      "Built-up areas reflect shortwave infrared more than near-infrared — the spectral mirror of NDVI.",
    domain: { minimum: -1, maximum: 1 },
    typicalQuery: "Show built-up regions.",
    interpretation: [
      { from: -1, to: -0.1, label: "Vegetated or water", meaning: "The NIR-dominant end of the range." },
      { from: -0.1, to: 0.1, label: "Mixed", meaning: "Neither clearly built nor clearly vegetated." },
      { from: 0.1, to: 1, label: "Built-up likelihood", meaning: "Constructed surface — or bare soil, which this index cannot separate." },
    ],
    limitations: [
      "Confuses bare soil with buildings.",
      "The design document is explicit: use as a feature or prior, never as a sole detector.",
    ],
  },

  nbr: {
    id: "nbr",
    label: "NBR",
    fullName: "Normalised Burn Ratio",
    formula: "(NIR − SWIR2) / (NIR + SWIR2), ΔNBR = NBR_pre − NBR_post",
    sentinel2Formula: "(B08 − B12) / (B08 + B12)",
    requiredBands: ["NIR", "SWIR2"],
    meaning:
      "Burned areas show a strong shortwave-infrared response; the difference between a pre and post pair quantifies burn severity.",
    domain: { minimum: -1, maximum: 1 },
    typicalQuery: "Assess fire damage in this region.",
    interpretation: [
      { from: -1, to: 0.1, label: "Unburned", meaning: "Below the unburned threshold in common practice." },
      { from: 0.1, to: 0.27, label: "Low severity", meaning: "Surface fuel consumed, canopy largely intact." },
      { from: 0.27, to: 0.66, label: "Moderate severity", meaning: "Partial canopy loss with surviving structure." },
      { from: 0.66, to: 1, label: "High severity", meaning: "Canopy consumed; recovery measured in years." },
    ],
    limitations: [
      "Seasonal and illumination differences mimic severity.",
      "Needs a co-registered pre/post pair — a single date cannot give ΔNBR.",
    ],
  },
};

/** The band a value falls in, for the readout and the legend. Null when the value is outside the domain. */
export function interpretIndexValue(
  indexId: SpectralIndexId,
  value: number,
): IndexInterpretationBand | null {
  return (
    SPECTRAL_INDICES[indexId].interpretation.find(
      (band) => value >= band.from && value <= band.to,
    ) ?? null
  );
}

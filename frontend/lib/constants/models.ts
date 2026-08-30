// lib/constants/models.ts — the specialist model catalogue: what each model is and when the router picks it.
//
// what  : Every specialist model AERIS can dispatch to, with its capability, the pipeline stages it serves,
//         why the router selects it, and what it cannot do.
// where : Read by the Model Observatory, by TraceStepNode (which resolves a step's model id to its
//         rationale), and by model.schema.ts, which builds its wire enums from the ids and capabilities
//         declared here.
// how   : Same split as lib/constants/pipeline-stages.ts, and for the same reason: THE WIRE CARRIES THE ID,
//         THE COPY LIVES HERE. A status payload says `mdl_changeformer` is degraded; what ChangeFormer is
//         and when it gets chosen is authored text that should be editable without a backend deploy. It
//         also means an unknown model id fails at the schema boundary instead of rendering as a blank row.
//
//         ONE ID VOCABULARY. The trace steps, the claims, the cross-modal runs and the fleet status feed
//         all name models, and before this file they named them differently — a claim said `changeformer`
//         while the fleet said `mdl_changeformer`, so "which model produced this claim, and why was it
//         chosen" could not be answered by joining the two. These ids are the only ones any of them may
//         use.
//
//         `selectionRationale` is the design document's requirement that the system explain "why they were
//         selected" (§ The Seven Application Pages, 6). It is written as the ROUTING RULE — the condition
//         under which this model wins — rather than as marketing copy, because the operator reading it is
//         asking why they got this model and not another one.

import type { PipelineStageCode } from "./pipeline-stages";

/**
 * What a model does, as a closed set.
 *
 * Declared here rather than in the schema so the catalogue and the wire contract cannot drift; model.schema
 * .ts builds its enum from this array.
 */
export const MODEL_CAPABILITIES = [
  "vision-language",
  "grounding",
  "change-detection",
  "segmentation",
  "object-detection",
  "spectral-index",
  "cross-modal-fusion",
  /** Cloud masking, co-registration, SAR terrain correction — everything upstream of an answer. */
  "preprocessing",
  /** Deterministic measurement over evidence that already exists — area, counts, density. */
  "spatial-statistics",
] as const;

export type ModelCapability = (typeof MODEL_CAPABILITIES)[number];

export const MODEL_CAPABILITY_LABEL: Readonly<Record<ModelCapability, string>> = {
  "vision-language": "Vision-language",
  grounding: "Grounding",
  "change-detection": "Change detection",
  segmentation: "Segmentation",
  "object-detection": "Object detection",
  "spectral-index": "Spectral index",
  "cross-modal-fusion": "Cross-modal fusion",
  preprocessing: "Preprocessing",
  "spatial-statistics": "Spatial statistics",
};

export const MODEL_IDS = [
  "rs-vlm",
  "grounding-dino-sam",
  "changeformer",
  "sar-change",
  "segformer-landcover",
  "dota-detector",
  "index-engine",
  "geospatial-engine",
  "optical-sar-fusion",
  "s2cloudless",
  "co-registration",
  "sar-preprocess",
] as const;

export type ModelId = (typeof MODEL_IDS)[number];

export interface SpecialistModel {
  id: ModelId;
  /** Shown wherever a model is named to an operator. */
  name: string;
  /** The published architecture it derives from, so a reader can go and check it. */
  family: string;
  capability: ModelCapability;
  /** What it produces, in one line. */
  role: string;
  /** The condition under which the router chooses this model over its alternatives. */
  selectionRationale: string;
  /** Where it is known to fail or mislead. Stated because an operator reading a claim needs it. */
  limitations: string;
  /** Pipeline stages this model can serve, so the Observatory can show where it sits. */
  stageCodes: readonly PipelineStageCode[];
}

export const SPECIALIST_MODELS: Readonly<Record<ModelId, SpecialistModel>> = {
  "rs-vlm": {
    id: "rs-vlm",
    name: "GeoChat RS-VLM",
    family: "GeoChat-class remote-sensing VLM",
    capability: "vision-language",
    role: "Explains validated results in language, and answers scene-level questions.",
    selectionRationale:
      "Chosen last in every pipeline, to phrase an answer from results the specialists already produced. It never sees raw pixels alone — a VLM asked to measure would invent a number.",
    limitations:
      "Reads RGB composites only. It cannot see the extra Sentinel-2 bands, so anything spectral must come from the index engine first.",
    stageCodes: ["S16"],
  },
  "grounding-dino-sam": {
    id: "grounding-dino-sam",
    name: "Grounding DINO + SAM",
    family: "Open-vocabulary detection with promptable segmentation",
    capability: "grounding",
    role: "Turns a phrase in the question into boxes and masks on the scene.",
    selectionRationale:
      "Chosen when the question names something the closed-set detectors were never trained on — 'the blue-roofed warehouses' rather than 'buildings'.",
    limitations:
      "Open-vocabulary recall degrades on small objects and on classes with no natural-language handle. Prefer the DOTA detector where the class is one it knows.",
    stageCodes: ["S13"],
  },
  changeformer: {
    id: "changeformer",
    name: "ChangeFormer",
    family: "Transformer bi-temporal change detection (BIT/ChangeFormer-class)",
    capability: "change-detection",
    role: "Produces a change mask from two co-registered observations of the same ground.",
    selectionRationale:
      "Chosen for any question about what changed between two optical dates, once co-registration residual is inside tolerance. Below that tolerance the pipeline refuses rather than running it.",
    limitations:
      "Sensitive to residual misregistration and to seasonal colour change, both of which read as change. Corroborate with radar where structure is the actual claim.",
    stageCodes: ["S13"],
  },
  "sar-change": {
    id: "sar-change",
    name: "SAR Change Detection",
    family: "Log-ratio and coherence change on calibrated backscatter",
    capability: "change-detection",
    role: "Maps change in surface roughness and structure between two radar passes.",
    selectionRationale:
      "Chosen for change questions when the optical pair is unusable — cloud, night, smoke — or when the claim is structural, where radar measures the thing directly and optical only infers it.",
    limitations:
      "Blind in layover and shadow, and speckle sets a floor on the smallest detectable change. Its silence is not evidence of absence until the geometry masks have been checked.",
    stageCodes: ["S13"],
  },
  "segformer-landcover": {
    id: "segformer-landcover",
    name: "SegFormer-B4 LandCover",
    family: "SegFormer-class semantic segmentation",
    capability: "segmentation",
    role: "Assigns every pixel a land-cover class and reports the share each one covers.",
    selectionRationale:
      "Chosen when the question is about composition — how much of this area is what — rather than about discrete objects that need counting.",
    limitations:
      "Class boundaries blur at the 10 m sampling of Sentinel-2. Small fragmented parcels are absorbed into whichever class surrounds them.",
    stageCodes: ["S13"],
  },
  "dota-detector": {
    id: "dota-detector",
    name: "DOTA Object Detector",
    family: "Oriented-bounding-box detector trained on DOTA/DIOR",
    capability: "object-detection",
    role: "Finds and counts discrete objects — buildings, vehicles, vessels, infrastructure.",
    selectionRationale:
      "Chosen when the answer is a count or a location of a class it was trained on. Preferred over grounding for those classes because a closed set gives calibrated confidence.",
    limitations:
      "Only detects its trained classes. A question about anything outside them routes to grounding instead.",
    stageCodes: ["S13", "S15"],
  },
  "index-engine": {
    id: "index-engine",
    name: "Spectral Index Engine",
    family: "Deterministic band arithmetic",
    capability: "spectral-index",
    role: "Computes NDVI, EVI, SAVI, NDWI, MNDWI, NDBI and NBR from the source bands.",
    selectionRationale:
      "Chosen whenever the question maps to a published index. It is arithmetic on calibrated reflectance, so it is preferred over any learned model that would only approximate the same number less checkably.",
    limitations:
      "Requires surface reflectance. Values over cloud, shadow or water are not meaningful and are masked rather than reported.",
    stageCodes: ["S12"],
  },
  "geospatial-engine": {
    id: "geospatial-engine",
    name: "Geospatial Statistics Engine",
    family: "Deterministic geometry and raster statistics",
    capability: "spatial-statistics",
    role: "Measures evidence that already exists — hectares, counts, and density surfaces.",
    selectionRationale:
      "Chosen after a specialist has produced geometry, whenever the answer needs a number. Georeferenced pixel counting rather than estimation, because a quantity a reader will quote must be reproducible.",
    limitations:
      "Measures exactly what it is given. A mask that over-segments produces a confidently wrong area, so its output is only as good as the model upstream of it.",
    stageCodes: ["S15"],
  },
  "optical-sar-fusion": {
    id: "optical-sar-fusion",
    name: "Optical-SAR Late Fusion",
    family: "Decision-level fusion over two independent per-sensor runs",
    capability: "cross-modal-fusion",
    role: "Compares two completed per-sensor analyses and reports where they agree.",
    selectionRationale:
      "Chosen when both an optical and a radar observation exist over the area. Late rather than early fusion, because keeping each sensor's evidence separable is what makes the joint answer auditable.",
    limitations:
      "Refuses to fuse when co-registration is worse than sub-pixel, or when the question is purely spectral or purely structural and one sensor's silence carries no information.",
    stageCodes: ["S14"],
  },
  s2cloudless: {
    id: "s2cloudless",
    name: "s2cloudless",
    family: "Gradient-boosted per-pixel cloud probability",
    capability: "preprocessing",
    role: "Produces the cloud and cloud-shadow mask that bounds every optical claim.",
    selectionRationale:
      "Runs on every optical scene before analysis. Nothing downstream may assert over pixels this marks, so it is not optional and not selected — it is a precondition.",
    limitations:
      "Thin cirrus and bright rooftops are its two failure modes, in opposite directions. Check the mask against the scene where a claim sits near its edge.",
    stageCodes: ["S7"],
  },
  "co-registration": {
    id: "co-registration",
    name: "Co-registration",
    family: "Phase-correlation alignment with sub-pixel refinement",
    capability: "preprocessing",
    role: "Aligns two observations to a common grid and reports the residual it could not remove.",
    selectionRationale:
      "Runs before any bi-temporal or cross-modal comparison. Its residual is what decides whether change detection may run at all.",
    limitations:
      "Alignment is harder across sensors than across dates. A residual larger than the feature under discussion invalidates the comparison rather than merely degrading it.",
    stageCodes: ["S9"],
  },
  "sar-preprocess": {
    id: "sar-preprocess",
    name: "SAR Preprocessing",
    family: "Calibration, speckle filtering and terrain correction",
    capability: "preprocessing",
    role: "Turns a raw SAR acquisition into calibrated backscatter with layover and shadow marked.",
    selectionRationale:
      "Runs on every radar scene. The layover and shadow masks it produces are what let the fusion step tell 'radar saw nothing' apart from 'radar could not see'.",
    limitations:
      "Speckle filtering trades resolution for readability. Terrain correction depends on the elevation model, so it is weakest exactly where relief is steepest.",
    stageCodes: ["S8"],
  },
};

/** Catalogue order for the Observatory: what answers questions first, what supports it after. */
export const MODEL_ORDER: readonly ModelId[] = [
  "rs-vlm",
  "changeformer",
  "sar-change",
  "optical-sar-fusion",
  "dota-detector",
  "segformer-landcover",
  "grounding-dino-sam",
  "index-engine",
  "geospatial-engine",
  "s2cloudless",
  "co-registration",
  "sar-preprocess",
];

/**
 * Resolves a model id from the wire.
 *
 * Returns null rather than throwing so a trace step naming a model this build does not know renders
 * without its rationale instead of taking down the panel around it.
 */
export function getModel(modelId: string | null): SpecialistModel | null {
  if (modelId === null) {
    return null;
  }
  return SPECIALIST_MODELS[modelId as ModelId] ?? null;
}

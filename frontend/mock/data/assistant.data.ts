// mock/data/assistant.data.ts — scripted agent answers and their execution traces.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : Suggested queries plus a small library of scripted answers, each with a realistic execution
//         trace and confidence, selected by keyword match against the operator prompt.
// where : Consumed by mock/streams/assistant-stream.ts, which replays a script as SSE frames.
// how   : The scripts follow the AERIS answer contract exactly — specialist models run first, evidence is
//         bound to regions, and only then does the explanation appear. That means the assistant panel is
//         built and reviewed against the shape of answer the real agent will emit, including trace timing
//         and the quantitative phrasing, rather than against lorem ipsum that would hide layout problems.

import type {
  AssistantSuggestion,
  ExecutionTraceStep,
} from "@/features/missionCommand/types/assistant.types";

export const MOCK_ASSISTANT_SUGGESTIONS: readonly AssistantSuggestion[] = [
  {
    id: "sug_change",
    label: "Has built-up area increased here?",
    prompt: "Compare these two scenes and tell me whether the built-up area increased.",
    pillar: "temporal",
  },
  {
    id: "sug_vegetation",
    label: "Show unhealthy vegetation",
    prompt: "Show me areas with unhealthy vegetation in this scene and quantify the affected area.",
    pillar: "single-image",
  },
  {
    id: "sug_flood",
    label: "Map flood extent from SAR",
    prompt: "Use the SAR acquisition to map the current flood extent and estimate inundated hectares.",
    pillar: "single-image",
  },
  {
    id: "sug_crossmodal",
    label: "Verify this with SAR",
    prompt: "Verify the optical finding against the SAR acquisition and report where they disagree.",
    pillar: "cross-modal",
  },
];

export interface AssistantScript {
  keywords: readonly string[];
  trace: readonly Omit<ExecutionTraceStep, "state">[];
  answer: string;
  confidence: number;
  evidenceRegionCount: number;
}

const CHANGE_DETECTION_SCRIPT: AssistantScript = {
  keywords: ["change", "built-up", "built up", "increase", "compare", "expansion", "growth"],
  trace: [
    { id: "s1", label: "Inspecting scene metadata", detail: "2 scenes · Sentinel-2A · 10 m GSD", durationMs: 240, modelId: null },
    { id: "s2", label: "Classifying intent", detail: "Bi-temporal change quantification", durationMs: 380, modelId: "rs-vlm" },
    { id: "s3", label: "Co-registering T0 and T1", detail: "RMSE 0.42 px", durationMs: 1_180, modelId: null },
    { id: "s4", label: "Masking cloud", detail: "Cloud fraction 4.1% · excluded from statistics", durationMs: 620, modelId: null },
    { id: "s5", label: "Running change detection", detail: "ChangeFormer v3.0.1", durationMs: 3_140, modelId: "changeformer" },
    { id: "s6", label: "Segmenting built-up class", detail: "SegFormer-B4 LandCover", durationMs: 2_260, modelId: "segformer-landcover" },
    { id: "s7", label: "Quantifying change area", detail: "Georeferenced pixel count · EPSG:32643", durationMs: 410, modelId: null },
    { id: "s8", label: "Validating evidence", detail: "3 regions passed sanity checks", durationMs: 300, modelId: null },
  ],
  answer:
    "Built-up area increased by 18.4% between the two acquisitions.\n\n14.2 hectares of new built-up surface were detected, concentrated in the north-east quadrant along the arterial road corridor. Two smaller clusters appear on the southern margin. Change is consistent across both the segmentation mask and the bi-temporal detector, and cloud-affected pixels were excluded before quantification.\n\nConfidence is 91%. Three evidence regions are attached — open the Evidence Explorer to inspect the mask, the georeferenced extent and the model versions behind each claim.",
  confidence: 0.91,
  evidenceRegionCount: 3,
};

const VEGETATION_SCRIPT: AssistantScript = {
  keywords: ["vegetation", "ndvi", "crop", "unhealthy", "stress", "health", "forest"],
  trace: [
    { id: "s1", label: "Inspecting scene metadata", detail: "1 scene · 13 bands · multispectral", durationMs: 210, modelId: null },
    { id: "s2", label: "Classifying intent", detail: "Spectral index + anomaly localisation", durationMs: 340, modelId: "rs-vlm" },
    { id: "s3", label: "Computing NDVI", detail: "(NIR - Red) / (NIR + Red)", durationMs: 190, modelId: "index-engine" },
    { id: "s4", label: "Thresholding stressed vegetation", detail: "NDVI < 0.28 over vegetated mask", durationMs: 260, modelId: null },
    { id: "s5", label: "Segmenting affected parcels", detail: "SegFormer-B4 LandCover", durationMs: 2_050, modelId: "segformer-landcover" },
    { id: "s6", label: "Quantifying affected area", detail: "Georeferenced pixel count", durationMs: 300, modelId: null },
  ],
  answer:
    "Vegetation stress is present across 22.7% of the vegetated area in this scene.\n\nNDVI falls below 0.28 over 61.3 hectares, forming three contiguous parcels in the western half of the frame. The largest parcel borders the irrigation channel, which is consistent with a water-delivery failure rather than disease — though this scene alone cannot separate those causes.\n\nConfidence is 84%. To distinguish cause, I would need a second acquisition from before the onset, or a SAR scene to check soil moisture.",
  confidence: 0.84,
  evidenceRegionCount: 3,
};

const FLOOD_SCRIPT: AssistantScript = {
  keywords: ["flood", "water", "inundat", "sar", "backscatter"],
  trace: [
    { id: "s1", label: "Inspecting scene metadata", detail: "1 scene · Sentinel-1A · VV+VH · 10 m", durationMs: 230, modelId: null },
    { id: "s2", label: "Classifying intent", detail: "Water extent delineation", durationMs: 310, modelId: "rs-vlm" },
    { id: "s3", label: "Applying speckle filter", detail: "Refined Lee · 5x5", durationMs: 880, modelId: null },
    { id: "s4", label: "Thresholding VV backscatter", detail: "Otsu threshold at -16.4 dB", durationMs: 540, modelId: null },
    { id: "s5", label: "Removing permanent water", detail: "Differenced against reference water mask", durationMs: 460, modelId: null },
    { id: "s6", label: "Quantifying inundated area", detail: "Georeferenced pixel count", durationMs: 280, modelId: null },
  ],
  answer:
    "Flood extent covers 1,284 hectares beyond the permanent water baseline.\n\nSAR backscatter drops below -16.4 dB across a contiguous region following the river's eastern floodplain, extending roughly 9.4 km downstream. Permanent water bodies were differenced out, so this figure is new inundation only. SAR is cloud-independent, so this measurement is unaffected by the weather system over the area.\n\nConfidence is 88%. Note that smooth dry surfaces such as tarmac can mimic water in SAR — two small detections near the settlement edge are flagged as low confidence in the evidence panel.",
  confidence: 0.88,
  evidenceRegionCount: 4,
};

const CROSS_MODAL_SCRIPT: AssistantScript = {
  keywords: ["verify", "cross", "fusion", "disagree", "confirm", "optical and sar"],
  trace: [
    { id: "s1", label: "Inspecting scene metadata", detail: "2 scenes · optical + SAR · same AOI", durationMs: 260, modelId: null },
    { id: "s2", label: "Classifying intent", detail: "Cross-modal verification", durationMs: 350, modelId: "rs-vlm" },
    { id: "s3", label: "Co-registering across sensors", detail: "RMSE 0.71 px", durationMs: 1_420, modelId: null },
    { id: "s4", label: "Analysing optical evidence", detail: "SegFormer-B4 LandCover", durationMs: 2_180, modelId: "segformer-landcover" },
    { id: "s5", label: "Analysing SAR evidence", detail: "Backscatter change analysis", durationMs: 1_960, modelId: null },
    { id: "s6", label: "Late fusion", detail: "Optical-SAR Late Fusion v0.9.3", durationMs: 4_120, modelId: "optical-sar-fusion" },
    { id: "s7", label: "Reconciling disagreement", detail: "2 regions in conflict", durationMs: 520, modelId: null },
  ],
  answer:
    "Both sensors agree on the primary finding, with two localised disagreements.\n\nOptical segmentation and SAR backscatter change independently identify the same expansion along the northern boundary — 11.8 of the 14.2 hectares are confirmed by both. Two regions totalling 2.4 hectares appear in the optical evidence only; their SAR signature is unchanged, which usually indicates a surface-material change rather than new structure.\n\nI am reporting the dual-confirmed figure as the headline and holding the optical-only regions as unverified. Confidence is 93% for the confirmed area, 47% for the disputed regions.",
  confidence: 0.93,
  evidenceRegionCount: 6,
};

const GENERAL_SCRIPT: AssistantScript = {
  keywords: [],
  trace: [
    { id: "s1", label: "Parsing question", detail: "Extracting intent, region and time range", durationMs: 280, modelId: "rs-vlm" },
    { id: "s2", label: "Checking available evidence", detail: "Scanning selected scenes and mission history", durationMs: 420, modelId: null },
    { id: "s3", label: "Assessing answerability", detail: "No specialist model can ground this claim", durationMs: 240, modelId: null },
  ],
  answer:
    "I can't ground that in the imagery currently selected.\n\nTo answer it I need at least one scene covering the area in question. Upload imagery from the panel on the left, or select an existing scene from the catalogue, and I will route it to the appropriate specialist models.\n\nI would rather tell you this than produce a fluent answer that no pixel supports.",
  confidence: 0.0,
  evidenceRegionCount: 0,
};

const SCRIPTS: readonly AssistantScript[] = [
  CHANGE_DETECTION_SCRIPT,
  VEGETATION_SCRIPT,
  FLOOD_SCRIPT,
  CROSS_MODAL_SCRIPT,
];

export function selectAssistantScript(prompt: string, hasSceneContext: boolean): AssistantScript {
  const normalisedPrompt = prompt.toLowerCase();

  const matched = SCRIPTS.find((script) =>
    script.keywords.some((keyword) => normalisedPrompt.includes(keyword)),
  );

  if (matched && hasSceneContext) {
    return matched;
  }

  // Without scene context AERIS declines rather than guessing — that is the product's core promise.
  return matched && hasSceneContext ? matched : hasSceneContext ? CHANGE_DETECTION_SCRIPT : GENERAL_SCRIPT;
}

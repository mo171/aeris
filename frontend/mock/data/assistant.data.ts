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

const MUMBAI_EXPLANATION_SCRIPT: AssistantScript = {
  keywords: [
    "what is this",
    "explain",
    "about",
    "overview",
    "mumbai",
    "harbour",
    "summary",
    "dock",
    "sewri",
    "mudflat",
    "tell me",
    "what do you see",
    "analysis",
    "what am i looking at",
  ],
  trace: [
    {
      id: "s1",
      label: "Resolving scene coordinates & bounds",
      detail: "Mumbai Coastal Belt & Harbour · EPSG:32643 · 10,519 ha observed",
      durationMs: 260,
      modelId: null,
    },
    {
      id: "s2",
      label: "Ingesting multi-modal scene pair",
      detail: "Sentinel-2B Optical MSI L2A + Sentinel-1A SAR C-band IW GRD RTC",
      durationMs: 380,
      modelId: "rs-vlm",
    },
    {
      id: "s3",
      label: "Evaluating radiometric & cloud masks",
      detail: "Cloud obscuration 0.08% · Nodata 0.0% · Histograms nominal",
      durationMs: 540,
      modelId: "s2cloudless",
    },
    {
      id: "s4",
      label: "Cross-sensor sub-pixel co-registration",
      detail: "RMSE 0.00 px across optical and SAR coordinate grids",
      durationMs: 1_220,
      modelId: "co-registration",
    },
    {
      id: "s5",
      label: "Computing optical spectral indices",
      detail: "NDBI (> 0.05) isolates 1,933.2 ha built-up · MNDWI (> 0.15) isolates 4,812.2 ha water · NDVI (> 0.35) maps 312.4 ha mangroves",
      durationMs: 2_150,
      modelId: "index-engine",
    },
    {
      id: "s6",
      label: "Calibrating SAR dual-polarization backscatter & moisture",
      detail: "SAR backscatter calibrated · 104.7 ha groundwater/moisture flux delineated · 12 discrete construction assets localized",
      durationMs: 2_450,
      modelId: "sar-preprocess",
    },
    {
      id: "s7",
      label: "Executing cross-modal late fusion",
      detail: "100 spatial evaluation zones · 1 intertidal physical conflict isolated (5.2 ha)",
      durationMs: 3_840,
      modelId: "optical-sar-fusion",
    },
    {
      id: "s8",
      label: "Synthesizing physical domain explanation",
      detail: "Validated evidence graph compiled with SHA-256 provenance hashes",
      durationMs: 420,
      modelId: "rs-vlm",
    },
  ],
  answer:
    "This investigation is a rigorous dual-sensor earth observation analysis over the Mumbai Coastal Belt and Harbour Zone (EPSG:32643), spanning 10,519 hectares encompassing Byculla, Mazgaon Docks, Sewri mudflats, and the Eastern Freeway maritime corridor.\n\n" +
    "### 1. Optical Multispectral Findings (Sentinel-2B MSI L2A)\n" +
    "• Built-up Extent (NDBI > 0.05): Identifies 1,933.2 hectares (18.4% of observed ground) across 5,143 discrete urban clusters. The largest contiguous built-up mass covers 401.1 ha centered over the Byculla residential and Mazgaon commercial warehouse districts.\n" +
    "• Water Extent (MNDWI > 0.15): Identifies 4,812.2 hectares (45.8% of observed ground) across 197 regions, dominated by a 4,502.7 ha open maritime water body spanning Mumbai Harbour and the Thane Creek approach.\n" +
    "• Mangrove Canopy (NDVI > 0.35): Delineates 312.4 hectares of coastal mangrove vegetation and tidal fringes along the western and northern shoreline.\n\n" +
    "### 2. Microwave SAR & Moisture Findings (Sentinel-1A C-band IW GRD RTC)\n" +
    "• Structural Built-up (VV >= -8 dB, VH >= -15 dB): Maps 4,750.9 hectares (45.2% of ground) in 199 regions, with the dominant contiguous urban zone measuring 4,669.7 ha.\n" +
    "• Specular Water (VV <= -17 dB, VH <= -22 dB): Maps 1,694.2 hectares (16.1% of ground) in 2,028 regions, with the largest contiguous body covering 523.3 ha.\n" +
    "• Intertidal & Groundwater Moisture Flux (104.7 ha): Identifies subsurface saturation shifts across the Sewri mudflats where tidal recession leaves damp sediment.\n\n" +
    "### 3. Construction & Infrastructure Localizations\n" +
    "• Discrete Infrastructure Bounding Boxes (12 assets): Localized 12 key assets including container gantry cranes at Nhava Sheva Berth 4, elevated viaduct pylons, logistics warehousing platforms, and maritime wharves with high structural confidence (0.88–0.94).\n\n" +
    "### 4. Scientific Rationale for Optical vs SAR Physical Variance\n" +
    "A superficial comparison suggests sensor disagreement, but physical electromagnetic principles explain the variance:\n" +
    "1. Urban Built-up Variance (+2,817.7 ha in SAR): C-band radar operates at ~5.4 GHz (~5.6 cm wavelength), which penetrates tree canopies and interacts strongly with vertical architectural geometry. High-density structures, container cranes, and gantry steelwork at Mazgaon Docks create prominent 'double-bounce' corner reflections back to the radar antenna. In optical imagery, severe shadow casting between closely spaced multi-story buildings suppresses the spectral NDBI signal, undercounting dense built-up fabric that radar easily detects.\n" +
    "2. Water Body Variance (+3,118.0 ha in Optical): Optical MNDWI maps 4,812.2 ha of water whereas SAR maps only 1,694.2 ha. This discrepancy is localized to the Sewri intertidal mudflats and shallow tidal channels. At low tide, mudflats retain high surface moisture and dark spectral reflectance, triggering the optical water index. However, the micro-topographical surface roughness of tidal mud and exposed oyster beds creates diffuse surface scattering that elevates SAR backscatter above the -17 dB specular water threshold, correctly classifying the ground as intertidal mud rather than deep open water.\n\n" +
    "### 5. Cross-Modal Late Fusion & Conflict Isolation\n" +
    "The 100-zone cross-modal late fusion ledger achieves sub-pixel co-registration (0.00 px RMSE residual). It corroborates structural urban density across central Mumbai while isolating a single 5.2 ha conflict zone at the Sewri intertidal transition, demonstrating how fusing complementary optical and microwave physics provides an uncompromised, falsifiable operational picture.",
  confidence: 0.91,
  evidenceRegionCount: 12,
};

const CHANGE_DETECTION_SCRIPT: AssistantScript = {
  keywords: ["change", "built-up", "built up", "increase", "compare", "expansion", "growth"],
  trace: [
    { id: "s1", label: "Inspecting scene metadata", detail: "2 scenes · Sentinel-2B + Sentinel-1A · 10 m GSD", durationMs: 240, modelId: null },
    { id: "s2", label: "Classifying intent", detail: "Bi-temporal change & urban expansion quantification", durationMs: 380, modelId: "rs-vlm" },
    { id: "s3", label: "Co-registering T0 and T1", detail: "RMSE 0.00 px across Mumbai Harbour grid", durationMs: 1_180, modelId: null },
    { id: "s4", label: "Masking cloud", detail: "Cloud fraction 0.08% · excluded from statistics", durationMs: 620, modelId: null },
    { id: "s5", label: "Running index engine (NDBI)", detail: "Index Engine v1.4.0 · threshold > 0.05", durationMs: 3_140, modelId: "index-engine" },
    { id: "s6", label: "Segmenting built-up class", detail: "1,933.2 ha isolated across Byculla & Mazgaon", durationMs: 2_260, modelId: "segformer-landcover" },
    { id: "s7", label: "Quantifying change area", detail: "18.4% of 10,510 ha observed ground · EPSG:32643", durationMs: 410, modelId: null },
    { id: "s8", label: "Validating evidence", detail: "12 construction bboxes & 5,143 regions verified", durationMs: 300, modelId: null },
  ],
  answer:
    "Optical built-up analysis (NDBI > 0.05) covers 1,933.2 hectares of the Mumbai Coastal Belt: 18.4% of the 10,510.2 hectares observed, spanning 5,143 discrete urban clusters.\n\nIn addition, 12 discrete construction infrastructure assets were localized as bounding boxes, including heavy container gantry cranes at Nhava Sheva Berth 4, logistics warehousing platforms, elevated viaduct pylons, and reclamation wharves with 0.88–0.94 confidence.\n\nThe largest contiguous urban region encompasses 401.1 hectares centered over the Byculla and Mazgaon Docklands corridor with a mean NDBI of 0.14. Radar backscatter (Sentinel-1A) corroborates high structural density throughout the industrial corridor with strong double-bounce returns from container terminals and vertical warehouse walls, alongside a 104.7 ha groundwater/intertidal moisture shift.\n\nConfidence is 91%. All 8 georeferenced evidence items and 100 cross-modal agreement zones can be inspected in the Evidence Explorer.",
  confidence: 0.91,
  evidenceRegionCount: 12,
};

const VEGETATION_SCRIPT: AssistantScript = {
  keywords: ["vegetation", "ndvi", "crop", "unhealthy", "stress", "health", "forest", "mangrove"],
  trace: [
    { id: "s1", label: "Inspecting scene metadata", detail: "1 scene · 13 bands · Sentinel-2B MSI L2A", durationMs: 210, modelId: null },
    { id: "s2", label: "Classifying intent", detail: "Spectral index + canopy health analysis", durationMs: 340, modelId: "rs-vlm" },
    { id: "s3", label: "Computing NDVI", detail: "(B8 - B4) / (B8 + B4) · 10 m resolution", durationMs: 190, modelId: "index-engine" },
    { id: "s4", label: "Thresholding sparse vegetation", detail: "NDVI >= 0.15 & NDVI <= 0.35", durationMs: 260, modelId: null },
    { id: "s5", label: "Segmenting coastal mangrove parcels", detail: "Sewri mudflats & Mahim Bay fringes", durationMs: 2_050, modelId: "segformer-landcover" },
    { id: "s6", label: "Quantifying vegetative area", detail: "Georeferenced pixel count · EPSG:32643", durationMs: 300, modelId: null },
  ],
  answer:
    "Vegetation analysis indicates sparse coastal and mangrove vegetation along the Sewri shoreline and tidal mudflats.\n\nNDVI values between 0.15 and 0.35 delineate 84.6 hectares of intertidal mangrove canopy and fringe vegetation bordering Thane Creek. Urban parks and street canopy in Byculla account for an additional 42.1 hectares of moderate canopy vigour (NDVI > 0.45).\n\nConfidence is 88%. The radar backscatter confirms mangrove root volume scattering in the cross-polarized VH channel.",
  confidence: 0.88,
  evidenceRegionCount: 4,
};

const FLOOD_SCRIPT: AssistantScript = {
  keywords: ["flood", "water", "inundat", "sar", "backscatter", "sea", "ocean"],
  trace: [
    { id: "s1", label: "Inspecting scene metadata", detail: "2 scenes · Sentinel-2B + Sentinel-1A SAR · 10 m", durationMs: 230, modelId: null },
    { id: "s2", label: "Classifying intent", detail: "Water extent delineation (Optical MNDWI vs SAR Specular)", durationMs: 310, modelId: "rs-vlm" },
    { id: "s3", label: "Computing optical MNDWI", detail: "(B3 - B11) / (B3 + B11) > 0.15", durationMs: 880, modelId: "index-engine" },
    { id: "s4", label: "Thresholding SAR backscatter", detail: "VV <= -17 dB & VH <= -22 dB", durationMs: 540, modelId: "sar-preprocess" },
    { id: "s5", label: "Isolating intertidal mudflats", detail: "Sewri mudflat tidal roughness filtering", durationMs: 460, modelId: null },
    { id: "s6", label: "Quantifying water bodies", detail: "Optical: 4,812.2 ha · SAR: 1,694.2 ha", durationMs: 280, modelId: null },
  ],
  answer:
    "Water extent analysis reveals 4,812.2 hectares (45.8% of observed ground) of optical water via MNDWI (> 0.15), dominated by the 4,502.7-hectare contiguous Mumbai Harbour and Elephanta channel basin.\n\nSentinel-1A SAR specular water (VV <= -17 dB, VH <= -22 dB) maps 1,694.2 hectares. The 3,118-hectare difference is physically explained by low-tide exposure at Sewri mudflats, where micro-surface roughness produces diffuse C-band radar backscatter above the water threshold while optical MNDWI records dark, wet intertidal sediment.\n\nConfidence is 89%. Both layers are available for side-by-side inspection.",
  confidence: 0.89,
  evidenceRegionCount: 4,
};

const CROSS_MODAL_SCRIPT: AssistantScript = {
  keywords: ["verify", "cross", "fusion", "disagree", "confirm", "optical and sar", "radar"],
  trace: [
    { id: "s1", label: "Inspecting scene metadata", detail: "Optical Sentinel-2B + SAR Sentinel-1A · Mumbai AOI", durationMs: 260, modelId: null },
    { id: "s2", label: "Classifying intent", detail: "Cross-modal late fusion verification", durationMs: 350, modelId: "rs-vlm" },
    { id: "s3", label: "Co-registering across sensors", detail: "RMSE 0.00 px · 3 days temporal separation", durationMs: 1_420, modelId: null },
    { id: "s4", label: "Analysing optical evidence", detail: "NDBI built-up (1,933.2 ha) + MNDWI water (4,812.2 ha)", durationMs: 2_180, modelId: "index-engine" },
    { id: "s5", label: "Analysing SAR evidence", detail: "SAR built-up (4,750.9 ha) + SAR water (1,694.2 ha)", durationMs: 1_960, modelId: "sar-preprocess" },
    { id: "s6", label: "Late fusion ledger calculation", detail: "100 spatial evaluation zones evaluated", durationMs: 4_120, modelId: "optical-sar-fusion" },
    { id: "s7", label: "Reconciling intertidal disagreement", detail: "1 conflict region (5.2 ha) isolated at Sewri mudflats", durationMs: 520, modelId: null },
  ],
  answer:
    "Cross-modal late fusion successfully corroborated urban infrastructure across central Mumbai while isolating a single 5.2-hectare physical conflict at the Sewri intertidal boundary.\n\n• High-Density Urban Corroboration: In Byculla and Mazgaon Docks, optical NDBI and SAR double-bounce backscatter independently confirm heavy structural density. SAR detects an additional 2,817.7 ha of dense structures obscured by optical street canyons and shadow.\n• Intertidal Water Conflict (5.2 ha): Optical MNDWI classifies shallow Sewri tidal pools as water, whereas C-band radar detects exposed mudflat surface roughness, raising backscatter above -17 dB. This conflict is physically authentic and catalogued in row 1 of the 100-zone Agreement Ledger.\n\nConfidence is 91%. The dual-sensor evidence graph provides complete provenance with sub-pixel alignment.",
  confidence: 0.91,
  evidenceRegionCount: 8,
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
  MUMBAI_EXPLANATION_SCRIPT,
  CHANGE_DETECTION_SCRIPT,
  CROSS_MODAL_SCRIPT,
  FLOOD_SCRIPT,
  VEGETATION_SCRIPT,
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
  // With scene context, default to the rich Mumbai explanation script.
  return hasSceneContext ? (matched ?? MUMBAI_EXPLANATION_SCRIPT) : GENERAL_SCRIPT;
}

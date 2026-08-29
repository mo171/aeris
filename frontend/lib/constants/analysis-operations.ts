// lib/constants/analysis-operations.ts — the analyses this system can actually run.
//
// what  : The catalogue of named remote-sensing operations — change detection, object detection,
//         segmentation, the spectral indices, SAR analysis and area statistics — with what each one needs
//         before it can run and the canonical question it asks.
// where : Rendered by the Toolbox panel, dispatched through investigation.runOperation, and sent on the
//         wire as `operationId` on an analysis run request.
// how   : Until now the only way to run anything was to type a question. That is the right PRIMARY
//         interface for this product and it is not a sufficient one: an analyst who knows they want NDVI
//         should not have to phrase it, and a newcomer cannot ask for a capability they have no way of
//         knowing exists. A named operation is also a far better thing to put on the wire than a sentence
//         — the backend dispatches it directly instead of classifying intent and possibly guessing wrong.
//
//         REQUIREMENTS ARE DECLARED, NOT ENFORCED IN THE UI. Each operation states what it needs, and the
//         panel explains what is missing rather than hiding the row. An operation the operator cannot see
//         is a capability they will never learn the system has, and "needs a radar scene" teaches them
//         something about the analysis; a greyed row with no reason teaches them nothing.
//
//         Every operation maps to a pipeline stage from the design document, so the trace an operation
//         produces is the same trace a typed question produces. Two ways in, one pipeline.

import type { PipelineStageCode } from "./pipeline-stages";

/**
 * What has to be true before an operation can run.
 *
 * `pair` means two usable observations — the whole class of change analysis is meaningless without a
 * before and an after. `evidence` means a run has already produced something to measure.
 */
export type AnalysisRequirement = "pair" | "optical" | "sar" | "evidence";

export interface AnalysisOperation {
  id: string;
  label: string;
  /** Written for the operator and reused as the agent-facing tool description. */
  description: string;
  requires: readonly AnalysisRequirement[];
  stageCode: PipelineStageCode;
  /**
   * The question this operation is equivalent to.
   *
   * Kept so the operation and the free-text route converge on one pipeline rather than forking into two
   * that can drift. Phase 2 sends `operationId` and the backend need not read this at all.
   */
  prompt: string;
}

export const ANALYSIS_OPERATIONS: readonly AnalysisOperation[] = [
  {
    id: "change-detection",
    label: "Change detection",
    description:
      "Compare the two selected observations and map where the ground changed, with each region sized and scored.",
    requires: ["pair"],
    stageCode: "S13",
    prompt: "What changed between these two observations?",
  },
  {
    id: "object-detection",
    label: "Object detection",
    description:
      "Find and count discrete objects — buildings, vehicles, vessels, infrastructure — in the comparison observation.",
    requires: ["optical"],
    stageCode: "S13",
    prompt: "What objects are present, and how many of each?",
  },
  {
    id: "segmentation",
    label: "Land-cover segmentation",
    description:
      "Classify every pixel into land-cover classes and report the share of the area each one covers.",
    requires: ["optical"],
    stageCode: "S13",
    prompt: "Classify land cover across this area and give the proportions.",
  },
  {
    id: "index-ndvi",
    label: "NDVI · vegetation",
    description:
      "Normalised difference vegetation index. Healthy vegetation reflects near-infrared strongly and absorbs red, so the ratio separates live canopy from bare ground.",
    requires: ["optical"],
    stageCode: "S12",
    prompt: "Compute NDVI and show where vegetation is stressed or lost.",
  },
  {
    id: "index-ndwi",
    label: "NDWI · water",
    description:
      "Normalised difference water index. Water absorbs near-infrared, so the ratio maps open water and flooding.",
    requires: ["optical"],
    stageCode: "S12",
    prompt: "Compute NDWI and map open water across this area.",
  },
  {
    id: "index-ndbi",
    label: "NDBI · built-up",
    description:
      "Normalised difference built-up index. Constructed surfaces reflect shortwave infrared more than near-infrared, which separates them from soil.",
    requires: ["optical"],
    stageCode: "S12",
    prompt: "Compute NDBI and map built-up surfaces.",
  },
  {
    id: "sar-analysis",
    label: "SAR backscatter",
    description:
      "Read radar backscatter, which is unaffected by cloud and responds to surface roughness and structure rather than to colour.",
    requires: ["sar"],
    stageCode: "S13",
    prompt: "What does the radar observation show over this area?",
  },
  {
    id: "area-statistics",
    label: "Area statistics",
    description:
      "Measure what the current evidence covers: total area per class, counts, and the distribution of confidence.",
    requires: ["evidence"],
    stageCode: "S15",
    prompt: "Summarise the measured area and counts of the current evidence.",
  },
];

/** Why an operation cannot run, said in terms of what to do about it. */
export const REQUIREMENT_COPY: Record<AnalysisRequirement, string> = {
  pair: "Needs two usable observations — pick a baseline and a comparison on the timeline",
  optical: "Needs an optical observation — the current comparison is radar",
  sar: "Needs a radar scene attached to this investigation",
  evidence: "Needs a completed analysis to measure",
};

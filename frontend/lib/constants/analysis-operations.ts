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
//
//         RUNS AND LENSES ARE DIFFERENT VERBS. A run asks the backend to produce evidence that does not
//         exist yet. A lens changes how evidence already in the workspace is READ — no model executes, no
//         trace step appears, nothing is added to the graph. They share this catalogue because they share
//         a question ("what can I do here?") and a requirements vocabulary, but a lens that dispatched an
//         analysis run would fabricate a trace for work nobody did.

import { CROSS_MODAL_STAGE } from "./cross-modal";
import type { ParameterValue } from "./parameters";
import type { PipelineStageCode } from "./pipeline-stages";
import { z } from "zod";

/**
 * What has to be true before an operation can run.
 *
 * `pair` means two usable observations — the whole class of change analysis is meaningless without a
 * before and an after. `evidence` means a run has already produced something to measure.
 */
export type AnalysisRequirement = "pair" | "optical" | "sar" | "evidence";

/**
 * Whether running this produces evidence or re-reads it.
 *
 * `run` dispatches an analysis and appends to the evidence graph. `lens` toggles a way of reading what is
 * already there and touches no model at all — see the note at the top of this file.
 */
export type AnalysisOperationKind = "run" | "lens";

/** Intent-level grouping for the Toolbox and the palette. */
export type OperationGroup = "ANALYSIS" | "TEMPORAL" | "MULTIMODAL" | "AI" | "MEASURE";

export interface AnalysisOperation {
  id: string;
  kind: AnalysisOperationKind;
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
  /**
   * Which overlay this operation puts on the scene, as a catalogue key.
   *
   * The link that makes the Toolbox and the layer stack two views of one thing: run an operation here,
   * and the overlay it produces is already described — encoding, units, thresholds, caveats — before a
   * single pixel arrives. Null for operations that measure existing evidence rather than draw anything.
   */
  producesOverlayId: string | null;
  /** Tunable inputs. A Zod object: one schema renders the form, validates a re-run, and is emitted as
   *  JSON Schema to the agent. z.object({}) for operations with no knobs. */
  parameters: z.ZodObject<z.ZodRawShape>;
  defaultParameters: Record<string, ParameterValue>;
  /** Search vocabulary — what an operator might type when they want this. */
  keywords: readonly string[];
  /** Intent-level grouping for the Toolbox and the palette. */
  group: OperationGroup;
}

export const ANALYSIS_OPERATIONS: readonly AnalysisOperation[] = [
  {
    id: "vegetation-analysis",
    kind: "run",
    label: "Vegetation analysis",
    description: "Measure vegetation health and density, or assess burn severity across an area.",
    requires: ["optical"],
    stageCode: "S12",
    prompt: "Analyse the vegetation and plant health in this area.",
    producesOverlayId: "ndvi", // Fallback, the real one depends on the parameter
    parameters: z.object({
      index: z.enum(["ndvi", "nbr"]).describe("Specific vegetation index to compute"),
    }),
    defaultParameters: { index: "ndvi" },
    keywords: ["vegetation", "plant", "health", "biomass", "burn", "severity", "ndvi", "nbr"],
    group: "ANALYSIS",
  },
  {
    id: "water-detection",
    kind: "run",
    label: "Water detection",
    description: "Map surface water bodies and moisture levels.",
    requires: ["optical"],
    stageCode: "S12",
    prompt: "Map the surface water in this area.",
    producesOverlayId: "ndwi",
    parameters: z.object({
      index: z.enum(["ndwi", "mndwi"]).describe("Specific water index to compute"),
    }),
    defaultParameters: { index: "ndwi" },
    keywords: ["water", "moisture", "flood", "lake", "river", "ndwi", "mndwi"],
    group: "ANALYSIS",
  },
  {
    id: "built-up-detection",
    kind: "run",
    label: "Built-up detection",
    description: "Highlight urban areas, impervious surfaces and human infrastructure.",
    requires: ["optical"],
    stageCode: "S12",
    prompt: "Highlight built-up and urban areas here.",
    producesOverlayId: "ndbi",
    parameters: z.object({}),
    defaultParameters: {},
    keywords: ["urban", "built-up", "infrastructure", "city", "impervious", "ndbi"],
    group: "ANALYSIS",
  },
  {
    id: "sar-analysis",
    kind: "run",
    label: "SAR backscatter",
    description:
      "Read radar backscatter, which is unaffected by cloud and responds to surface roughness and structure rather than to colour.",
    requires: ["sar"],
    stageCode: "S13",
    prompt: "What does the radar observation show over this area?",
    producesOverlayId: "backscatter",
    parameters: z.object({
      polarization: z.enum(["VV", "VH", "HH", "HV"]).describe("Radar polarization to analyze"),
    }),
    defaultParameters: { polarization: "VV" },
    keywords: ["sar", "radar", "backscatter", "roughness", "structure"],
    group: "MULTIMODAL",
  },
  {
    /**
     * The cross-modal reading. A LENS, not a run: both sensor analyses are already complete, and this
     * holds them apart to report where they agree rather than asking anything new of the backend.
     *
     * It lives here rather than in the navigation rail because a rail names PLACES, and cross-modal is a
     * way of reading one investigation — it needs an investigation id to mean anything at all. Listing it
     * as an operation also means an investigation with no radar sees the row with its reason attached
     * instead of discovering the capability does not apply after navigating to it.
     */
    id: "cross-modal",
    kind: "lens",
    label: "Cross-modal agreement",
    description:
      "Hold the optical and radar analyses apart and report where the two sensors corroborate, where they conflict, and where one of them could not see at all.",
    requires: ["optical", "sar"],
    stageCode: CROSS_MODAL_STAGE,
    prompt: "Do the optical and radar observations agree over this area?",
    producesOverlayId: null,
    parameters: z.object({}),
    defaultParameters: {},
    keywords: ["cross-modal", "compare", "agree", "conflict", "radar vs optical", "fusion"],
    group: "MULTIMODAL",
  },
  {
    id: "area-statistics",
    kind: "run",
    label: "Area statistics",
    description:
      "Measure what the current evidence covers: total area per class, counts, and the distribution of confidence.",
    requires: ["evidence"],
    stageCode: "S15",
    prompt: "Summarise the measured area and counts of the current evidence.",
    producesOverlayId: null,
    parameters: z.object({}),
    defaultParameters: {},
    keywords: ["measure", "area", "statistics", "counts", "distribution", "summary"],
    group: "MEASURE",
  },
];

/** Why an operation cannot run, said in terms of what to do about it. */
export const REQUIREMENT_COPY: Record<AnalysisRequirement, string> = {
  pair: "Needs two usable observations — pick a baseline and a comparison on the timeline",
  optical: "Needs an optical observation — the current comparison is radar",
  sar: "Needs a radar scene attached to this investigation",
  evidence: "Needs a completed analysis to measure",
};

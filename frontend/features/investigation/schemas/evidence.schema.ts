// features/investigation/schemas/evidence.schema.ts — the claim/evidence graph behind every answer.
//
// what  : Zod schemas for a claim, its quantitative metrics, the evidence items supporting it, and the
//         flat graph envelope that carries claims, evidence, layers and trace steps together.
// where : Parsed by evidence.service.ts and by the analysis stream. Drives the answer panel, the layer
//         stack and the evidence spotlight.
// how   : The graph arrives FLAT — parallel arrays keyed by id, not nested objects. Claims, evidence,
//         layers and trace steps form a graph rather than a tree, and nesting one inside another would
//         make the spotlight interaction an O(n) scan and re-render the whole answer panel on every
//         hover. Flat arrays normalise into byId maps in one pass.
//
//         `confidence` is `number | null` everywhere, and null is a real answer: it means AERIS declines
//         to assert one. It renders as an explicit refusal card offering alternatives, never as zero.
//         A fluent guess is worse than an honest gap, and the distinction has to survive the wire.
//
//         Every claim points at the evidence that supports it and at the trace step that produced it, so
//         "show me why" is a lookup rather than an inference.

import { z } from "zod";

import { isoTimestampSchema } from "@/lib/schemas/geo.schema";

import { evidenceLayerSchema } from "./layer.schema";

export const claimKindSchema = z.enum([
  "quantitative",
  "spatial",
  "categorical",
  /** An asserted absence — "no new construction was detected" — which is a finding, not an empty result. */
  "negative",
]);

export const metricDirectionSchema = z.enum(["increase", "decrease", "neutral"]);

export const claimMetricSchema = z.object({
  label: z.string().min(1),
  value: z.number(),
  unit: z.string(),
  direction: metricDirectionSchema,
  /** How many decimals the figure is meaningful to. Prevents a model's noise being rendered as precision. */
  precision: z.number().int().min(0).max(4),
});

export const claimSchema = z.object({
  id: z.string().min(1),
  runId: z.string().min(1),
  text: z.string().min(1),
  kind: claimKindSchema,
  confidence: z.number().min(0).max(1).nullable(),
  metrics: z.array(claimMetricSchema),
  /** Evidence that supports this claim. Empty means the claim is unsupported and must say so. */
  evidenceIds: z.array(z.string()),
  modelId: z.string().min(1),
  modelVersion: z.string().min(1),
  traceStepId: z.string().min(1),
  /** The headline claim of a run. Exactly one per run; the rest are supporting detail. */
  isPrimary: z.boolean(),
});

export const evidenceKindSchema = z.enum([
  "change-mask",
  "detection",
  "index-map",
  "scene-crop",
  "statistic",
  "cross-modal",
]);

export const evidenceItemSchema = z.object({
  id: z.string().min(1),
  kind: evidenceKindSchema,
  title: z.string().min(1),
  /** The layer that draws this evidence, and the feature within it the spotlight raises. */
  layerId: z.string().nullable(),
  featureIds: z.array(z.string()),
  areaHectares: z.number().nonnegative().nullable(),
  magnitude: z.number().min(0).max(1),
  confidence: z.number().min(0).max(1).nullable(),
  sourceSceneIds: z.array(z.string()),
});

/**
 * Why the system will not assert an answer.
 *
 * This is a first-class response, not an error. It names the reason and offers concrete next actions,
 * because "the available imagery does not support a reliable conclusion, try SAR" is more useful to an
 * analyst than a confident sentence with nothing behind it.
 */
export const insufficientEvidenceSchema = z.object({
  reason: z.string().min(1),
  remedies: z.array(
    z.object({
      id: z.string().min(1),
      label: z.string().min(1),
      /** The prompt this remedy re-asks with, so acting on it is one click. */
      prompt: z.string().min(1),
    }),
  ),
});

export const evidenceGraphSchema = z.object({
  claims: z.array(claimSchema),
  evidence: z.array(evidenceItemSchema),
  layers: z.array(evidenceLayerSchema),
  generatedAt: isoTimestampSchema,
});

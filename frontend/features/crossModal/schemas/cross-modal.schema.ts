// features/crossModal/schemas/cross-modal.schema.ts — the dual-evidence contract, validated at the boundary.
//
// what  : Zod schemas for a cross-modal verdict: per-sensor runs, the agreement state of each finding,
//         the modality-pair advisory, and a claim that carries two provenances instead of one.
// where : Parsed by services/cross-modal.service.ts; the inferred types drive the whole Lab surface.
// how   : The workspace's claim carries ONE model, ONE version and ONE confidence. That is correct there
//         and structurally unable to express what this page exists for — a claim two sensors disagree
//         about has two of each, and the disagreement is the finding. So this composes the existing
//         evidence schema rather than widening it: the workspace keeps its simple shape and pays nothing
//         for a case it does not have.
//
//         PER-SENSOR RUNS ARE INDEPENDENT BY CONSTRUCTION. Each carries its own findings, its own masks
//         and its own confidence, and neither can see the other's result before producing its own. That
//         independence is the only thing that makes agreement mean anything — two runs that consulted
//         each other agreeing is not corroboration, it is an echo.
//
//         The verdict is nullable, and that is a feature. §9.2 names four conditions under which the
//         system should decline to fuse; a schema that required a verdict would make refusing impossible
//         to express, and the page would be forced to invent one.

import { z } from "zod";

import { AGREEMENT_STATES, FUSION_REFUSAL_IDS } from "@/lib/constants/cross-modal";
import { evidenceLayerSchema } from "@/features/investigation/schemas/layer.schema";
import { claimSchema, evidenceItemSchema } from "@/features/investigation/schemas/evidence.schema";
import { isoTimestampSchema } from "@/lib/schemas/geo.schema";

export const sensorIdSchema = z.enum(["optical", "radar"]);
export const agreementStateSchema = z.enum(AGREEMENT_STATES);
export const fusionRefusalIdSchema = z.enum(FUSION_REFUSAL_IDS);
export const polarisationSchema = z.enum(["VV", "VH", "ratio"]);

/**
 * One sensor's analysis, complete on its own.
 *
 * Shaped so that either half could be rendered alone and still be a valid answer — which is exactly what
 * happens when the other modality is missing, cloud-blocked, or refused by the fusion policy.
 */
export const sensorRunSchema = z.object({
  sensor: sensorIdSchema,
  sceneId: z.string().min(1),
  capturedAt: isoTimestampSchema,
  platform: z.string().min(1),
  /** Radar only. Null for optical, where the analogue is band selection rather than polarisation. */
  polarisation: polarisationSchema.nullable(),
  /**
   * Radar look azimuth in degrees clockwise from north, and incidence from vertical.
   *
   * Carried because layover and shadow are PREDICTABLE from geometry — terrain tilted toward the sensor
   * folds, terrain behind it goes dark. An operator who can see the look direction can anticipate where
   * radar is blind instead of discovering it inside a wrong answer.
   */
  lookAzimuthDegrees: z.number().min(0).max(360).nullable(),
  incidenceAngleDegrees: z.number().min(0).max(90).nullable(),
  layers: z.array(evidenceLayerSchema),
  evidence: z.array(evidenceItemSchema),
  claims: z.array(claimSchema),
  modelId: z.string().min(1),
  modelVersion: z.string().min(1),
  confidence: z.number().min(0).max(1).nullable(),
  /** Share of the area this sensor could not read at all — cloud for optical, layover/shadow for radar. */
  obscuredFraction: z.number().min(0).max(1),
});

/**
 * One finding, and what the two sensors each said about it.
 *
 * `reason` is the physical explanation, not a restatement of the state. "Optical only" is a fact; "the
 * region sits in radar layover, where radar could not have seen it" is what an operator can act on, and
 * it is the difference between a table and an instrument.
 */
export const agreementRowSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  state: agreementStateSchema,
  reason: z.string().min(1),
  /** Feature ids per sensor, so a row can raise exactly what each one saw. Empty where that sensor is silent. */
  opticalFeatureIds: z.array(z.string()),
  radarFeatureIds: z.array(z.string()),
  opticalConfidence: z.number().min(0).max(1).nullable(),
  radarConfidence: z.number().min(0).max(1).nullable(),
  areaHectares: z.number().nonnegative().nullable(),
});

/** Whether the pair is close enough in time and alignment to be describing the same ground. */
export const modalityAdvisorySchema = z.object({
  verdict: z.enum(["fair", "offset", "unusable"]),
  offsetDays: z.number().nonnegative(),
  coRegistrationPixels: z.number().nonnegative().nullable(),
  /** Said in the operator's terms, and about the data rather than about the system. */
  notes: z.array(z.string()),
});

/**
 * The fused conclusion — or an explicit refusal to produce one.
 *
 * A conflict BLOCKS the headline: when the two sensors assert opposite things, the Lab declines a primary
 * claim and says what would resolve it, rather than picking a side or averaging. Supporting claims are
 * still delivered, tagged with the sensor behind each. Rigour where the reader will quote it, usefulness
 * everywhere else.
 */
export const fusionVerdictSchema = z.object({
  /** Null when fusion was refused, or when a conflict blocks the headline. */
  headline: z.string().nullable(),
  confidence: z.number().min(0).max(1).nullable(),
  refusedBecause: fusionRefusalIdSchema.nullable(),
  /** Set when a conflict is what blocked the headline, naming what would resolve it. */
  blockedByConflict: z.string().nullable(),
  rows: z.array(agreementRowSchema),
});

export const crossModalResultSchema = z.object({
  investigationId: z.string().min(1),
  runId: z.string().min(1),
  optical: sensorRunSchema,
  radar: sensorRunSchema.nullable(),
  advisory: modalityAdvisorySchema,
  verdict: fusionVerdictSchema.nullable(),
  generatedAt: isoTimestampSchema,
});

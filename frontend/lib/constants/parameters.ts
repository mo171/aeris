// lib/constants/parameters.ts — the closed set of tunable analysis inputs.
//
// what  : Zod schemas and types for the parameter kinds an analysis operation can accept.
// where : Used by analysis-operations.ts to define the tunable inputs for each operation.
// how   : A closed set of parameter types ("number-range", "enum", "boolean", etc.) means ONE
//         dynamic form renderer covers every operation. The UI never needs hardcoded fields for specific
//         products because the schema dictates exactly what inputs to render.

import { z } from "zod";

export const parameterKindSchema = z.enum([
  "number-range",
  "enum",
  "boolean",
  "layer-ref",
  "scene-ref",
  "band-list",
  "text",
]);

export type ParameterKind = z.infer<typeof parameterKindSchema>;

// The value that an operation actually runs with. Must be able to represent
// any of the possible values the ParameterKind inputs can produce.
export const parameterValueSchema = z.union([
  z.number(),
  z.string(),
  z.boolean(),
  z.array(z.string()),
  z.record(z.string(), z.any()),
]);

export type ParameterValue = z.infer<typeof parameterValueSchema>;

// lib/env.ts — typed, validated access to every NEXT_PUBLIC_* variable. The only place process.env is read.
//
// what  : Parses and validates environment variables once at module load and exports a frozen `env` object.
// where : Imported by lib/axios, lib/streaming, lib/providers and anywhere a URL/flag is needed.
//         A missing or malformed variable fails loudly at boot instead of surfacing as a mystery 404 later.
// how   : Next.js inlines `process.env.NEXT_PUBLIC_X` at build time only for literal member access, so each
//         variable is spelled out literally below. Values are then run through a Zod schema that applies
//         defaults and coerces the string flags into real booleans/numbers.

import { z } from "zod";

const booleanFromString = z
  .enum(["true", "false"])
  .default("false")
  .transform((value) => value === "true");

const environmentSchema = z.object({
  NEXT_PUBLIC_APP_URL: z.string().min(1).default("http://localhost:3000"),
  NEXT_PUBLIC_API_URL: z.string().min(1).default("http://localhost:8000"),
  NEXT_PUBLIC_API_TIMEOUT_MS: z.coerce.number().int().positive().default(30_000),

  /**
   * Phase 1 switch. While true, /mock installs an in-memory transport under the axios and stream
   * clients. Phase 2 deletes the /mock folder entirely and this flag goes with it.
   */
  NEXT_PUBLIC_USE_MOCK_DATA: booleanFromString,
  /** Artificial round-trip latency for the mock transport, so loading states are real and testable. */
  NEXT_PUBLIC_MOCK_LATENCY_MS: z.coerce.number().int().nonnegative().default(280),
  /** Size of the generated mock imagery catalogue — raise it to stress-test virtualisation. */
  NEXT_PUBLIC_MOCK_SCENE_COUNT: z.coerce.number().int().positive().default(5_000),
  /**
   * Number of mission markers on the globe. 300 is a realistic resting load; raise it well past a
   * thousand to stress-test the point collection. Density at any given altitude is governed by the
   * level-of-detail rules in lib/constants/globe.ts, not by this number.
   */
  NEXT_PUBLIC_MOCK_MARKER_COUNT: z.coerce.number().int().positive().default(300),

  /**
   * Cesium Ion access token. Optional, but this is the switch between a real Earth and a fallback.
   * Set    -> Ion world imagery + real elevation terrain. The intended experience.
   * Unset  -> dark raster basemap on a smooth ellipsoid. Real geography, but flat.
   * Free tokens come from ion.cesium.com.
   */
  NEXT_PUBLIC_CESIUM_ION_TOKEN: z.string().default(""),
});

const parsedEnvironment = environmentSchema.safeParse({
  NEXT_PUBLIC_APP_URL: process.env.NEXT_PUBLIC_APP_URL,
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_API_TIMEOUT_MS: process.env.NEXT_PUBLIC_API_TIMEOUT_MS,
  NEXT_PUBLIC_USE_MOCK_DATA: process.env.NEXT_PUBLIC_USE_MOCK_DATA,
  NEXT_PUBLIC_MOCK_LATENCY_MS: process.env.NEXT_PUBLIC_MOCK_LATENCY_MS,
  NEXT_PUBLIC_MOCK_SCENE_COUNT: process.env.NEXT_PUBLIC_MOCK_SCENE_COUNT,
  NEXT_PUBLIC_MOCK_MARKER_COUNT: process.env.NEXT_PUBLIC_MOCK_MARKER_COUNT,
  NEXT_PUBLIC_CESIUM_ION_TOKEN: process.env.NEXT_PUBLIC_CESIUM_ION_TOKEN,
});

if (!parsedEnvironment.success) {
  throw new Error(
    `Invalid environment configuration:\n${JSON.stringify(
      z.treeifyError(parsedEnvironment.error),
      null,
      2,
    )}`,
  );
}

export const env = Object.freeze(parsedEnvironment.data);

export type Environment = typeof env;

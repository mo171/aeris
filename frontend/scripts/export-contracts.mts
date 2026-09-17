// Exports every Zod schema in this app to JSON Schema, so the backend can validate against the frontend's contract instead of a copy of it.
//
// what  : Discovers every `*.schema.ts` module, converts each exported Zod schema with Zod 4's built-in
//         `z.toJSONSchema`, and writes one deterministic JSON document to
//         `backend/bcontext/contracts/schemas.json`. `--check` verifies the committed file is current
//         instead of rewriting it.
// where : `pnpm run contracts:export`, and `pnpm run contracts:check` in CI. Lives in the frontend because
//         the schemas do: `api-contract.md` §0 makes the frontend's Zod authoritative, and a converter that
//         lived in the backend would be a second place that has to know how the frontend is laid out.
// how   : **`io: "input"`, and that is the whole correctness of this script.** The frontend calls
//         `schema.parse(response.data)`, so a backend payload is the schema's *input*. Any schema carrying a
//         `.transform()`, a `.default()` or a coercion has a different output type, and exporting the output
//         side would produce a contract demanding values the backend cannot send — a `Date` object where the
//         wire has a string. Nothing here currently transforms, which is exactly why the flag has to be set
//         now: the day one does, this keeps being right silently rather than breaking loudly.
//
//         **The output is deterministic and carries no timestamp.** Object keys are sorted and nothing
//         records when it ran, so regenerating an unchanged contract produces a byte-identical file. That is
//         what makes `--check` meaningful and what makes a diff on this file mean "the contract changed"
//         rather than "someone ran the script".
//
//         Discovery is by directory scan rather than an import list. A curated list would be a second thing
//         to maintain, and the failure it invites — a schema the frontend added and the backend never sees —
//         is silent on both sides.

import { readdirSync, readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { z } from "zod";

import { audioLocationSchema, speechEventSchema } from "../lib/schemas/stream-events.schema";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDirectory, "..");
const contractsDirectory = resolve(frontendRoot, "..", "backend", "bcontext", "contracts");
const outputPath = join(contractsDirectory, "schemas.json");

/** Where schema modules live. Both roots are scanned; a new feature is picked up without editing this file. */
const SCHEMA_ROOTS = [join(frontendRoot, "features"), join(frontendRoot, "lib", "schemas")];

type SchemaDocument = Record<string, Record<string, unknown>>;

function verifyAudioLocationRuntimeContract(): void {
  const cases: Array<{ name: string; value: string; normalised: string | null }> = [
    {
      name: "absolute HTTP URL",
      value: "https://aeris.example/api/v1/speech/utt_audio.opus",
      normalised: "https://aeris.example/api/v1/speech/utt_audio.opus",
    },
    {
      name: "root-relative path",
      value: "/api/v1/speech/utt_audio.opus",
      normalised: "/api/v1/speech/utt_audio.opus",
    },
    {
      name: "whitespace-wrapped absolute URL",
      value: "  https://aeris.example/api/v1/speech/utt_audio.opus  ",
      normalised: "https://aeris.example/api/v1/speech/utt_audio.opus",
    },
    {
      name: "whitespace-wrapped root-relative path",
      value: "  /api/v1/speech/utt_audio.opus  ",
      normalised: "/api/v1/speech/utt_audio.opus",
    },
    {
      name: "malformed absolute URL port",
      value: "https://aeris.example:not-a-port/utt_audio.opus",
      normalised: null,
    },
    { name: "unsupported scheme", value: "ftp://aeris.example/utt_audio.opus", normalised: null },
    {
      name: "protocol-relative path",
      value: "//different-origin.example/utt_audio.opus",
      normalised: null,
    },
    { name: "empty path", value: "", normalised: null },
  ];

  for (const contractCase of cases) {
    const result = audioLocationSchema.safeParse(contractCase.value);
    const accepted = result.success;
    if (accepted !== (contractCase.normalised !== null)) {
      throw new Error(
        `Audio location runtime case "${contractCase.name}" expected accepted=${contractCase.normalised !== null}, got ${accepted}.`,
      );
    }
    if (result.success && result.data !== contractCase.normalised) {
      throw new Error(
        `Audio location runtime case "${contractCase.name}" expected audioUrl=${contractCase.normalised}, got ${result.data}.`,
      );
    }
  }
}

function verifySpeechRuntimeContract(): void {
  const common = {
    type: "speech",
    runId: "run_contract",
    utteranceId: "utt_contract",
    text: "Contract fixture.",
    supersedesUtteranceId: null,
  };
  const cases: Array<{
    name: string;
    accepted: boolean;
    payload: Record<string, unknown>;
    normalisedAudioUrl?: string | null;
  }> = [
    {
      name: "grounded absolute URL",
      accepted: true,
      payload: {
        ...common,
        kind: "grounded",
        audioUrl: "  https://aeris.example/api/v1/speech/utt_contract.opus  ",
        claimIds: ["clm_contract"],
        interruptible: true,
        provisional: false,
      },
      normalisedAudioUrl: "https://aeris.example/api/v1/speech/utt_contract.opus",
    },
    {
      name: "provisional local audio",
      accepted: true,
      payload: {
        ...common,
        kind: "provisional",
        audioUrl: null,
        claimIds: [],
        interruptible: true,
        provisional: true,
      },
    },
    {
      name: "progress relative URL",
      accepted: true,
      payload: {
        ...common,
        kind: "progress",
        audioUrl: "  /api/v1/speech/utt_contract.opus  ",
        claimIds: [],
        interruptible: true,
        provisional: false,
      },
      normalisedAudioUrl: "/api/v1/speech/utt_contract.opus",
    },
    {
      name: "non-interruptible refusal",
      accepted: true,
      payload: {
        ...common,
        kind: "refusal",
        audioUrl: null,
        claimIds: [],
        interruptible: false,
        provisional: false,
      },
    },
    {
      name: "unbound grounded result",
      accepted: false,
      payload: {
        ...common,
        kind: "grounded",
        audioUrl: null,
        claimIds: [],
        interruptible: true,
        provisional: false,
      },
    },
    {
      name: "contradictory provisional flag",
      accepted: false,
      payload: {
        ...common,
        kind: "progress",
        audioUrl: null,
        claimIds: [],
        interruptible: true,
        provisional: true,
      },
    },
    {
      name: "provisional speech with claims",
      accepted: false,
      payload: {
        ...common,
        kind: "provisional",
        audioUrl: null,
        claimIds: ["clm_contract"],
        interruptible: true,
        provisional: true,
      },
    },
    {
      name: "provisional kind without label",
      accepted: false,
      payload: {
        ...common,
        kind: "provisional",
        audioUrl: null,
        claimIds: [],
        interruptible: true,
        provisional: false,
      },
    },
    {
      name: "interruptible refusal",
      accepted: false,
      payload: {
        ...common,
        kind: "refusal",
        audioUrl: null,
        claimIds: [],
        interruptible: true,
        provisional: false,
      },
    },
    {
      name: "non-root relative audio path",
      accepted: false,
      payload: {
        ...common,
        kind: "grounded",
        audioUrl: "audio/utt_contract.opus",
        claimIds: ["clm_contract"],
        interruptible: true,
        provisional: false,
      },
    },
    {
      name: "protocol-relative audio path",
      accepted: false,
      payload: {
        ...common,
        kind: "grounded",
        audioUrl: "//different-origin.example/utt_contract.opus",
        claimIds: ["clm_contract"],
        interruptible: true,
        provisional: false,
      },
    },
    {
      name: "non-HTTP absolute audio URL",
      accepted: false,
      payload: {
        ...common,
        kind: "grounded",
        audioUrl: "ftp://aeris.example/utt_contract.opus",
        claimIds: ["clm_contract"],
        interruptible: true,
        provisional: false,
      },
    },
    {
      name: "malformed absolute URL port",
      accepted: false,
      payload: {
        ...common,
        kind: "grounded",
        audioUrl: "https://aeris.example:not-a-port/utt_contract.opus",
        claimIds: ["clm_contract"],
        interruptible: true,
        provisional: false,
      },
    },
    {
      name: "empty audio path",
      accepted: false,
      payload: {
        ...common,
        kind: "grounded",
        audioUrl: "",
        claimIds: ["clm_contract"],
        interruptible: true,
        provisional: false,
      },
    },
  ];

  for (const contractCase of cases) {
    const result = speechEventSchema.safeParse(contractCase.payload);
    const accepted = result.success;
    if (accepted !== contractCase.accepted) {
      throw new Error(
        `Speech runtime contract case "${contractCase.name}" expected accepted=${contractCase.accepted}, got ${accepted}.`,
      );
    }
    if (
      result.success &&
      "normalisedAudioUrl" in contractCase &&
      result.data.audioUrl !== contractCase.normalisedAudioUrl
    ) {
      throw new Error(
        `Speech runtime contract case "${contractCase.name}" expected audioUrl=${contractCase.normalisedAudioUrl}, got ${result.data.audioUrl}.`,
      );
    }
  }
}

function findSchemaModules(): string[] {
  const found: string[] = [];

  const walk = (directory: string): void => {
    if (!existsSync(directory)) return;
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) {
        walk(path);
      } else if (entry.name.endsWith(".schema.ts")) {
        found.push(path);
      }
    }
  };

  for (const root of SCHEMA_ROOTS) walk(root);
  // Sorted so the output file's key order does not depend on the filesystem's.
  return found.sort();
}

/** Recursively sort object keys, so an unchanged contract regenerates byte-identically. */
function withSortedKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(withSortedKeys);
  if (value === null || typeof value !== "object") return value;

  const sorted: Record<string, unknown> = {};
  for (const key of Object.keys(value as Record<string, unknown>).sort()) {
    sorted[key] = withSortedKeys((value as Record<string, unknown>)[key]);
  }
  return sorted;
}

async function buildDocument(): Promise<SchemaDocument> {
  const document: SchemaDocument = {};
  const failures: string[] = [];

  for (const modulePath of findSchemaModules()) {
    // Posix-style, so the keys in the committed file are identical on Windows and on CI.
    const moduleKey = relative(frontendRoot, modulePath).split("\\").join("/");
    const exported = (await import(pathToFileURL(modulePath).href)) as Record<string, unknown>;

    const schemas: Record<string, unknown> = {};
    for (const exportName of Object.keys(exported).sort()) {
      const value = exported[exportName];
      // `createCursorPageSchema` is a factory, not a schema, and type-only exports vanish at runtime.
      // Anything that is not a Zod type is skipped rather than reported: this is a scan, not a lint.
      if (!(value instanceof z.ZodType)) continue;

      try {
        schemas[exportName] = withSortedKeys(
          z.toJSONSchema(value, { io: "input", target: "draft-2020-12" }),
        );
      } catch (error) {
        // Reported rather than swallowed. A schema that cannot be expressed as JSON Schema is a contract the
        // backend cannot be held to, and silently omitting it would look identical to it passing.
        failures.push(`${moduleKey} :: ${exportName} — ${(error as Error).message}`);
      }
    }

    if (Object.keys(schemas).length > 0) document[moduleKey] = schemas;
  }

  if (failures.length > 0) {
    throw new Error(`Could not convert ${failures.length} schema(s):\n  ${failures.join("\n  ")}`);
  }
  return document;
}

async function main(): Promise<void> {
  verifyAudioLocationRuntimeContract();
  verifySpeechRuntimeContract();
  const isCheck = process.argv.includes("--check");
  const document = await buildDocument();
  const serialised = `${JSON.stringify(document, null, 2)}\n`;

  const moduleCount = Object.keys(document).length;
  const schemaCount = Object.values(document).reduce((total, schemas) => total + Object.keys(schemas).length, 0);

  if (isCheck) {
    if (!existsSync(outputPath)) {
      console.error(`Contracts have never been exported. Run: pnpm run contracts:export`);
      process.exit(1);
    }
    if (readFileSync(outputPath, "utf8") !== serialised) {
      console.error(
        "The vendored contracts are stale — a Zod schema changed and backend/bcontext/contracts/schemas.json " +
          "was not regenerated. Run: pnpm run contracts:export",
      );
      process.exit(1);
    }
    console.log(`Contracts are up to date: ${schemaCount} schemas from ${moduleCount} modules.`);
    return;
  }

  mkdirSync(contractsDirectory, { recursive: true });
  writeFileSync(outputPath, serialised, "utf8");
  console.log(`Wrote ${schemaCount} schemas from ${moduleCount} modules to ${outputPath}`);
}

await main();

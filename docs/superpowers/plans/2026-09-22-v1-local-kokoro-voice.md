# V-1 Local Kokoro Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace cloud speech synthesis in the V-1 voice loop with prewarmed local Kokoro q8 inference using the British male George voice (`bm_george`).

**Architecture:** A browser Web Worker owns one cached Kokoro model and returns transferable 24 kHz Float32 audio. A typed client coordinates preparation, synthesis, cancellation, and timing while the existing voice session renders API text/actions immediately and plays local audio through `SpeechStreamPlayer`.

**Tech Stack:** Next.js 16, React 19, TypeScript, Vitest, `kokoro-js`, ONNX Runtime Web, Web Workers, Web Audio API

**Spec:** `docs/superpowers/specs/2026-09-22-v1-local-kokoro-voice-design.md`

## Global Constraints

- Scope is the V-1 frontend voice experience only.
- Use `onnx-community/Kokoro-82M-v1.0-ONNX`, q8 weights, `bm_george`, and 24 kHz output.
- Model preparation may download roughly 90 MB once and must use browser caching afterward.
- Inference must run outside the React/UI thread.
- Existing mute, interruption, and text/action behavior must remain functional.
- Do not modify the Python backend.
- Do not silently switch speech providers.
- Run GitNexus impact analysis before editing each existing symbol and `detect-changes --scope all` before completion.

---

## File Structure

- Create `frontend/lib/audio/kokoro-config.ts`: immutable model, dtype, voice, and sample-rate configuration.
- Create `frontend/lib/audio/kokoro-protocol.ts`: worker message and lifecycle-state contracts shared by the worker and client.
- Create `frontend/lib/audio/kokoro.worker.ts`: model initialization and synthesis execution only.
- Create `frontend/lib/audio/kokoro-client.ts`: worker lifecycle, request correlation, cancellation, timing, and error propagation.
- Modify `frontend/lib/audio/speech-stream-player.ts`: accept transferable Float32 PCM without a base64 or WAV round trip.
- Modify `frontend/features/voice/hooks/use-voice-session.ts`: prewarm Kokoro, synthesize greeting/replies locally, and preserve interruption/mute behavior.
- Modify `frontend/app/api/voice/process/route.ts`: remove cloud TTS from the normal response critical path.
- Create `frontend/tests/audio/kokoro-client.test.ts`: worker protocol and stale-result tests.
- Modify `frontend/tests/audio/speech-stream-player.test.ts`: Float32 playback coverage.
- Modify `frontend/package.json` and `frontend/pnpm-lock.yaml`: add the pinned compatible `kokoro-js` runtime.

---

### Task 1: Kokoro configuration, protocol, and dependency

**Files:**
- Create: `frontend/lib/audio/kokoro-config.ts`
- Create: `frontend/lib/audio/kokoro-protocol.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/pnpm-lock.yaml`
- Test: `frontend/tests/audio/kokoro-client.test.ts`

**Interfaces:**
- Produces: `KOKORO_MODEL_ID`, `KOKORO_DTYPE`, `KOKORO_VOICE`, `KOKORO_SAMPLE_RATE`.
- Produces: `KokoroWorkerRequest`, `KokoroWorkerResponse`, `KokoroLifecycleState`.

- [ ] **Step 1: Run dependency and model compatibility probes**

Run:

```powershell
pnpm view kokoro-js version engines dependencies
pnpm add kokoro-js
```

Confirm the installed package exposes `KokoroTTS.from_pretrained()` and accepts `dtype: "q8"` plus `voice: "bm_george"`. Do not continue if the installed API differs; update the plan's concrete adapter calls first.

- [ ] **Step 2: Write the failing configuration/protocol test**

Create `frontend/tests/audio/kokoro-client.test.ts` with an initial assertion:

```ts
import { describe, expect, it } from "vitest";
import {
  KOKORO_DTYPE,
  KOKORO_MODEL_ID,
  KOKORO_SAMPLE_RATE,
  KOKORO_VOICE,
} from "../../lib/audio/kokoro-config";

describe("Kokoro configuration", () => {
  it("locks V-1 synthesis to the q8 British male George voice", () => {
    expect(KOKORO_MODEL_ID).toBe("onnx-community/Kokoro-82M-v1.0-ONNX");
    expect(KOKORO_DTYPE).toBe("q8");
    expect(KOKORO_VOICE).toBe("bm_george");
    expect(KOKORO_SAMPLE_RATE).toBe(24_000);
  });
});
```

- [ ] **Step 3: Run the focused test and verify the expected missing-module failure**

Run: `pnpm vitest run tests/audio/kokoro-client.test.ts`

Expected: FAIL because `lib/audio/kokoro-config.ts` does not exist.

- [ ] **Step 4: Add immutable configuration and discriminated worker messages**

Implement configuration using `as const`. Define requests for `prepare`, `synthesize`, and `cancel`; define responses for `state`, `prepared`, `audio`, and `error`. Every synthesis message carries a `requestId`; an audio response carries `samples: Float32Array`, `sampleRate`, and timing metadata.

- [ ] **Step 5: Run the focused test**

Run: `pnpm vitest run tests/audio/kokoro-client.test.ts`

Expected: PASS for configuration.

- [ ] **Step 6: Commit the dependency and contracts**

```powershell
git add frontend/package.json frontend/pnpm-lock.yaml frontend/lib/audio/kokoro-config.ts frontend/lib/audio/kokoro-protocol.ts frontend/tests/audio/kokoro-client.test.ts
git commit -m "feat(voice): add Kokoro runtime contracts"
```

---

### Task 2: Worker-backed Kokoro client

**Files:**
- Create: `frontend/lib/audio/kokoro.worker.ts`
- Create: `frontend/lib/audio/kokoro-client.ts`
- Modify: `frontend/tests/audio/kokoro-client.test.ts`

**Interfaces:**
- Consumes: protocol and configuration from Task 1.
- Produces: `KokoroSpeechClient` with `prepare(): Promise<void>`, `synthesize(text: string): Promise<KokoroAudio>`, `cancel(): void`, `dispose(): void`, and `getState(): KokoroLifecycleState`.
- Produces: `KokoroAudio = { samples: Float32Array; sampleRate: number; synthesisMs: number }`.

- [ ] **Step 1: Extend the test with a controllable worker double**

Test these behaviors independently:

```ts
it("deduplicates concurrent prepare calls and resolves when the worker is ready");
it("returns transferred George audio for the matching synthesis request");
it("rejects worker errors with the provider reason");
it("ignores audio from a cancelled or superseded request");
it("terminates the worker and rejects pending work on dispose");
```

Inject a `WorkerLike` factory into `KokoroSpeechClient` so tests exercise real correlation logic without loading ONNX.

- [ ] **Step 2: Run tests and verify missing client failures**

Run: `pnpm vitest run tests/audio/kokoro-client.test.ts`

Expected: FAIL because `KokoroSpeechClient` is not implemented.

- [ ] **Step 3: Implement the typed client**

Use a single worker instance created lazily with:

```ts
new Worker(new URL("./kokoro.worker.ts", import.meta.url), { type: "module" });
```

Maintain one preparation promise and a map of synthesis request resolvers. Generate monotonic request IDs, post cancellation for the active request, reject superseded promises with an `AbortError`, and log `performance.now()` timing without including reply content.

- [ ] **Step 4: Implement the worker model singleton**

Load the runtime only inside the worker:

```ts
const { KokoroTTS } = await import("kokoro-js");
model = await KokoroTTS.from_pretrained(KOKORO_MODEL_ID, {
  dtype: KOKORO_DTYPE,
});
```

Synthesize with:

```ts
const audio = await model.generate(text, { voice: KOKORO_VOICE });
```

Normalize the runtime result to a standalone `Float32Array`, verify a 24 kHz sample rate, and transfer `samples.buffer` back to the client. The worker processes one synthesis at a time and suppresses results whose request ID was cancelled.

- [ ] **Step 5: Run focused tests**

Run: `pnpm vitest run tests/audio/kokoro-client.test.ts`

Expected: PASS for configuration and all client lifecycle cases.

- [ ] **Step 6: Commit the worker boundary**

```powershell
git add frontend/lib/audio/kokoro.worker.ts frontend/lib/audio/kokoro-client.ts frontend/tests/audio/kokoro-client.test.ts
git commit -m "feat(voice): run Kokoro George in a web worker"
```

---

### Task 3: Float32 playback and local voice-session integration

**Files:**
- Modify: `frontend/lib/audio/speech-stream-player.ts`
- Modify: `frontend/tests/audio/speech-stream-player.test.ts`
- Modify: `frontend/features/voice/hooks/use-voice-session.ts`
- Test: `frontend/tests/audio/speech-stream-player.test.ts`
- Test: `frontend/tests/audio/kokoro-client.test.ts`

**Interfaces:**
- Consumes: `KokoroSpeechClient` and `KokoroAudio` from Task 2.
- Produces: `SpeechStreamPlayer.enqueueFloat32(samples: Float32Array, sampleRate?: number): void`.

- [ ] **Step 1: Run GitNexus impact checks for existing symbols**

Run:

```powershell
npx gitnexus@latest impact "SpeechStreamPlayer" --direction upstream --repo .
npx gitnexus@latest impact "AerisSessionManager" --direction upstream --repo .
```

If either result is `UNKNOWN`, confirm callers with `rg` before editing. Warn before continuing if GitNexus reports HIGH or CRITICAL risk.

- [ ] **Step 2: Write the failing Float32 playback test**

Add a test proving that a 24 kHz Float32 buffer is scheduled directly, values are copied unchanged, and sequential timing remains gapless:

```ts
const samples = new Float32Array([0, 0.25, -0.5, 1]);
player.enqueueFloat32(samples, 24_000);
expect(mockCtx.createBuffer).toHaveBeenCalledWith(1, 4, 24_000);
expect(createdBuffer.getChannelData(0)).toEqual(samples);
```

- [ ] **Step 3: Run the player test and verify it fails**

Run: `pnpm vitest run tests/audio/speech-stream-player.test.ts`

Expected: FAIL because `enqueueFloat32` does not exist.

- [ ] **Step 4: Implement direct Float32 scheduling**

Share scheduling logic between Int16 and Float32 entry points. Copy the incoming array into the Web Audio buffer and preserve active-source tracking, gapless scheduling, abort, and close semantics.

- [ ] **Step 5: Integrate one Kokoro client and one speech player into the session manager**

Prepare Kokoro during `connect()` without delaying microphone readiness. Replace activation greeting cloud audio with local synthesis of the existing greeting text. In `handleProcessResponse`, append text and execute actions before awaiting synthesis; then synthesize `data.reply`, set voice state to `speaking`, enqueue the returned samples, and return to idle after playback completion or interruption.

Use a monotonic turn token so late audio from an older reply cannot play. `interrupt()`, mute, and disconnect must call both `kokoro.cancel()` and `speechPlayer.abort()`.

- [ ] **Step 6: Run focused audio tests**

Run:

```powershell
pnpm vitest run tests/audio/kokoro-client.test.ts tests/audio/speech-stream-player.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit local playback integration**

```powershell
git add frontend/lib/audio/speech-stream-player.ts frontend/tests/audio/speech-stream-player.test.ts frontend/features/voice/hooks/use-voice-session.ts
git commit -m "feat(voice): play local Kokoro George responses"
```

---

### Task 4: Remove cloud TTS from the API critical path

**Files:**
- Modify: `frontend/app/api/voice/process/route.ts`
- Create: `frontend/tests/voice/process-response.test.ts`

**Interfaces:**
- Consumes: existing `POST(request: Request)` route contract.
- Produces: successful responses with transcript, reply, actions, and `audioBase64: null`; speech is a frontend responsibility.

- [ ] **Step 1: Run GitNexus impact analysis for the route handler**

Run:

```powershell
npx gitnexus@latest impact "POST" --direction upstream --repo .
```

Confirm `UNKNOWN` results with route and client text searches. Do not edit on an unresolved HIGH or CRITICAL warning.

- [ ] **Step 2: Write a route-contract regression test**

Extract a small pure response composer only if required for testability. Assert that the normal local-TTS response includes `audioBase64: null` and does not invoke ElevenLabs or OpenAI speech synthesis. Preserve transcript, reply, and actions unchanged.

- [ ] **Step 3: Run the focused test and verify it fails**

Run: `pnpm vitest run tests/voice/process-response.test.ts`

Expected: FAIL because the route still synthesizes cloud audio.

- [ ] **Step 4: Remove cloud synthesis from greeting and normal responses**

Return the greeting text immediately with `audioBase64: null`. Return normal reply text/actions immediately with `audioBase64: null`. Remove dead ElevenLabs helper/configuration and OpenAI speech helper code only after confirming it has no remaining callers. Keep OpenAI transcription and response generation untouched.

- [ ] **Step 5: Run focused tests and production build**

Run:

```powershell
pnpm vitest run tests/voice/process-response.test.ts tests/audio/kokoro-client.test.ts tests/audio/speech-stream-player.test.ts
pnpm build
```

Expected: all focused tests PASS and Next.js production build exits 0.

- [ ] **Step 6: Commit the API latency change**

```powershell
git add frontend/app/api/voice/process/route.ts frontend/tests/voice/process-response.test.ts
git commit -m "perf(voice): remove cloud TTS from response path"
```

---

### Task 5: Demo-machine model preparation and latency verification

**Files:**
- Modify if needed: `frontend/features/voice/hooks/use-voice-session.ts`
- Modify if needed: `frontend/lib/audio/kokoro-client.ts`
- Modify: `frontend/.env.example`

**Interfaces:**
- Produces diagnostic timings for `kokoro.prepare`, `voice.api`, `kokoro.synthesize`, and first scheduled playback.

- [ ] **Step 1: Add privacy-safe timing marks**

Log durations and selected model metadata only. Do not log API keys, full request payloads, or synthesized reply text. Include `provider=kokoro`, `voice=bm_george`, cache-warm preparation time, synthesis time, and time to playback scheduling.

- [ ] **Step 2: Document the one-time preparation flow**

Update `.env.example` comments to state that ElevenLabs/OpenAI TTS variables are not used by the V-1 local path. Document that the operator should open AERIS, enable voice once, and wait for the Kokoro ready diagnostic before recording.

- [ ] **Step 3: Run all verification commands**

Run:

```powershell
pnpm vitest run tests/audio/kokoro-client.test.ts tests/audio/speech-stream-player.test.ts tests/voice/process-response.test.ts
pnpm build
npx gitnexus@latest detect-changes --scope all --repo .
git diff --check
git status --short
```

The repository-wide `pnpm test` and `pnpm lint` must also be run. Report pre-existing unrelated failures separately; do not claim they passed when they did not.

- [ ] **Step 4: Perform the local browser acceptance run**

Verify on the Windows demo laptop:

1. First voice connection reaches Kokoro `ready` after the one-time model download.
2. A second page load uses cached assets.
3. Activation greeting and three normal turns audibly use George (`bm_george`).
4. Reply text/actions appear before speech completes.
5. Push-to-talk interruption, mute, and disconnect stop queued speech.
6. Globe/UI interaction remains responsive during synthesis.
7. Record cold preparation and three warm API-to-playback durations.

- [ ] **Step 5: Commit diagnostics and operator documentation**

```powershell
git add frontend/features/voice/hooks/use-voice-session.ts frontend/lib/audio/kokoro-client.ts frontend/.env.example
git commit -m "docs(voice): add Kokoro preparation diagnostics"
```


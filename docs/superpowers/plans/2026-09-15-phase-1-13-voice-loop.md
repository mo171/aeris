# Phase 1.13 Voice Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade, hotkey-activated terminal voice conversation that preserves scientific runs during interruption, speaks claim-grounded results, proposes validated frontend commands, and supplies a tested frontend command bridge.

**Architecture:** A `VoiceSession` service coordinates audio and one active agent task while LangGraph continues to own plans, checkpoints, tools, and scientific execution. Offline adapters use Silero/faster-whisper and Kokoro through async boundaries; a specialized agent node emits typed, data-bound interface proposals, and pure frontend adapters dispatch them through the existing Zod-validating command registry.

**Tech Stack:** Python 3.14, asyncio, LangGraph/LangChain, faster-whisper, Silero VAD, Kokoro, sounddevice, Pydantic, Typer/Rich, TypeScript, Zod, Zustand, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-15-phase-1-13-voice-loop-design.md`

## Global Constraints

- `Ctrl+P` activates one microphone turn; the microphone is not always listening.
- Barge-in cancels one interruptible utterance and never the scientific run.
- Only a language-model-classified explicit abandon action reaches `RunHandle.abandon()`.
- Grounded speech is generated from validated claims/refusals, never chat Markdown.
- Provisional speech has empty `claimIds`, `provisional=true`, and is later superseded.
- With AI enabled, rejected or failed AI prose/UI selection is not replaced with hard-coded prose or a deterministic UI action.
- Interface commands are presentation-only proposals; backend and frontend both validate them.
- Browser microphone, browser playback, and WebSocket transport remain Phase 2.4/2.7.
- Every application function is async except pure `math/` functions and required third-party serialization callbacks already documented by the repository.

---

### Task 1: Correct and model the voice/UI stream contract

**Files:**
- Create: `backend/app/schemas/events/voice.py`
- Create: `backend/app/schemas/events/interface.py`
- Modify: `backend/app/schemas/events/__init__.py`
- Modify: `backend/app/constants/events.py`
- Modify: `frontend/features/investigation/schemas/analysis.schema.ts`
- Modify: `frontend/features/missionCommand/schemas/assistant.schema.ts`
- Modify: `backend/tests/contracts/test_stream_events.py`
- Modify: `backend/bcontext/api-contract.md`

**Interfaces:**
- Produces: `SpeechEvent(run_id, utterance_id, text, audio_url, claim_ids, interruptible, provisional, supersedes_utterance_id)`.
- Produces: `UiCommandEvent(run_id, command_id, params, reason)`.
- Produces: frontend `speechEventSchema` and `uiCommandEventSchema` reused by both stream unions.

- [ ] **Step 1: Write failing backend contract tests**

Add tests that serialize grounded, provisional, and superseding speech plus one UI command, validate them against the exported frontend schemas, and reject an empty unlabelled `claimIds` list.

```python
async def test_provisional_speech_is_explicit_and_can_be_superseded() -> None:
    provisional = SpeechEvent(run_id="run_1", utterance_id="utt_1", text="Provisional: cloud may obscure it.", claim_ids=[], provisional=True)
    grounded = SpeechEvent(run_id="run_1", utterance_id="utt_2", text="The validated result is available.", claim_ids=["clm_1"], supersedes_utterance_id="utt_1")
    assert serialise_event(provisional)["provisional"] is True
    assert serialise_event(grounded)["supersedesUtteranceId"] == "utt_1"
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `uv run pytest tests/contracts/test_stream_events.py -q`

Expected: import/schema failures because `SpeechEvent` and the complete frontend shape do not exist.

- [ ] **Step 3: Implement typed models and shared Zod schemas**

Use Pydantic model validation to enforce the grounded/provisional invariant. Add `UI_COMMAND` and `SPEECH` discriminators to both event vocabularies and unions. Make `audioUrl` nullable, because Phase 1 streams PCM locally.

- [ ] **Step 4: Export contracts and verify GREEN**

Run: `pnpm contracts:export` in `frontend`, then `uv run pytest tests/contracts/test_stream_events.py -q` in `backend`.

Expected: all stream contract tests pass and `schemas.json` contains the complete speech fields.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/events backend/app/constants/events.py backend/tests/contracts/test_stream_events.py backend/bcontext/api-contract.md frontend/features/*/schemas backend/bcontext/contracts/schemas.json
git commit -m "feat: define voice and interface stream events"
```

### Task 2: Add the frontend command-event bridge

**Files:**
- Create: `frontend/lib/streaming/ui-command-bridge.ts`
- Create: `frontend/lib/streaming/ui-command-bridge.test.ts`
- Modify: `frontend/features/investigation/hooks/use-analysis-run.ts`
- Modify: `frontend/features/missionCommand/hooks/use-assistant-session.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/pnpm-lock.yaml`

**Interfaces:**
- Consumes: `{commandId: string, params: Record<string, unknown>, reason: string}`.
- Produces: `dispatchUiCommandEvent(event): Promise<CommandDispatchResult>`.

- [ ] **Step 1: Add Vitest and write failing bridge tests**

Register real commands through `defineCommand`/`registerCommands`; assert completed, not-found, invalid-params, disabled, and failed results. Feed a valid command after each failure to prove the stream remains usable.

```typescript
it("validates before executing an agent command", async () => {
  let opacity = 0;
  const unregister = registerCommands([defineCommand({
    id: "investigation.setLayerOpacity", title: "Opacity", description: "Set opacity", group: "investigation",
    paramsSchema: z.object({ opacity: z.number().min(0).max(1) }), handler: ({ opacity: next }) => { opacity = next; },
  })]);
  expect((await dispatchUiCommandEvent({ commandId: "investigation.setLayerOpacity", params: { opacity: 2 }, reason: "Reveal context" })).status).toBe("invalid-params");
  expect(opacity).toBe(0);
  unregister();
});
```

- [ ] **Step 2: Run Vitest and verify RED**

Run: `pnpm test -- ui-command-bridge.test.ts`

Expected: failure because the script/module does not exist.

- [ ] **Step 3: Implement the pure bridge and hook both streams**

The bridge delegates exclusively to `dispatchCommand`. Stream hooks call it with `void`, report non-completed results through a supplied observer/logger, and continue processing subsequent frames.

- [ ] **Step 4: Verify frontend tests and static gates**

Run: `pnpm test -- ui-command-bridge.test.ts && pnpm lint && pnpm exec tsc --noEmit`.

Expected: all pass with no unhandled promise rejection.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat: dispatch streamed interface commands"
```

### Task 3: Add validated offline voice configuration and dependencies

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Modify: `backend/app/config.py`
- Create: `backend/app/constants/voice.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/unit/test_config.py`

**Interfaces:**
- Produces: settings for device selectors, Whisper model/device/compute type/language, capture/VAD timing, Kokoro voice/speed, narration, and UI command budget.

- [ ] **Step 1: Write failing configuration tests**

Assert invalid sample rates, silence windows, capture limits, speed, and model/device combinations fail at settings validation. Assert secret values never appear in repr.

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/unit/test_config.py -q`.

Expected: missing voice setting attributes.

- [ ] **Step 3: Add dependencies and settings**

Add `faster-whisper`, `silero-vad`, `kokoro`, `sounddevice`, `soundfile`, and `prompt-toolkit`. Put fixed PCM formats and supported lifecycle states in `constants/voice.py`; put every environment-varying value in `config.py` and document it in `.env.example`.

- [ ] **Step 4: Lock and verify GREEN**

Run: `uv lock && uv sync --frozen && uv run pytest tests/unit/test_config.py -q && uv run ruff check app/config.py app/constants/voice.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/config.py backend/app/constants/voice.py backend/.env.example backend/tests/unit/test_config.py
git commit -m "feat: configure offline voice models"
```

### Task 4: Implement capture, VAD, and transcription

**Files:**
- Create: `backend/app/voice/__init__.py`
- Create: `backend/app/voice/audio.py`
- Create: `backend/app/voice/transcription.py`
- Create: `backend/app/voice/types.py`
- Create: `backend/tests/unit/test_voice_input.py`
- Create: `backend/tests/fixtures/audio/README.md`
- Create: `backend/tests/fixtures/audio/operator-short.wav`

**Interfaces:**
- Produces: `CapturedTurn(samples: bytes, sample_rate: int, started_at: datetime, duration_ms: int)`.
- Produces: `MicrophoneCapture.capture(stop_requested: asyncio.Event) -> CapturedTurn | None`.
- Produces: `WhisperTranscriber.transcribe(turn: CapturedTurn) -> Transcript`.

- [ ] **Step 1: Write failing input tests**

Use an injected async block source to test silence, speech followed by silence, noise, maximum duration, and explicit second-hotkey stop without opening hardware.

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/unit/test_voice_input.py -q`.

Expected: module import failure.

- [ ] **Step 3: Implement the async device/model adapters**

Use blocking raw stream reads through `asyncio.to_thread`; use Silero's probability/VAD iterator for endpointing; pass the resulting NumPy waveform to faster-whisper with word timestamps and no second heuristic endpoint detector. Empty/silent input returns `None`.

- [ ] **Step 4: Verify GREEN and measure the retained WAV**

Run: `uv run pytest tests/unit/test_voice_input.py -q`.

Expected: tests pass and the fixture transcript meets its declared normalized phrase/WER assertion when the model-asset marker is enabled.

- [ ] **Step 5: Commit**

```bash
git add backend/app/voice backend/tests/unit/test_voice_input.py backend/tests/fixtures/audio
git commit -m "feat: capture and transcribe voice turns"
```

### Task 5: Implement grounded speech authoring and cancellable playback

**Files:**
- Create: `backend/app/voice/speech.py`
- Create: `backend/app/voice/synthesis.py`
- Create: `backend/app/services/prompts/voice.py`
- Create: `backend/tests/unit/test_voice_speech.py`

**Interfaces:**
- Produces: `author_grounded_speech(request, claims, model) -> AuthoredSpeech`.
- Produces: `author_progress_speech(trace_step, model) -> AuthoredSpeech | None`.
- Produces: `KokoroSynthesizer.chunks(utterance) -> AsyncIterator[AudioChunk]`.
- Produces: `SpeechPlayer.speak(utterance, chunks)`, `interrupt()`, `standby()`, and `resume()`.

- [ ] **Step 1: Write failing truth/lifecycle tests**

Cover claim binding, refusal preservation, unsupported-number rejection, provisional labelling, supersession, chunk order, interruption, standby, non-interruptible statements, synthesis failure, and output failure.

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/unit/test_voice_speech.py -q`.

- [ ] **Step 3: Implement AI-authored speech and Kokoro playback**

Reuse the evidence/numeral guard rather than creating fixed result prose. A rejected draft is regenerated through the configured model policy and otherwise raises a typed speech-generation error. Kokoro's generator and sounddevice writes run through `asyncio.to_thread`; utterance cancellation is independent of run cancellation.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/test_voice_speech.py -q && uv run ruff check app/voice app/services/prompts/voice.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/voice backend/app/services/prompts/voice.py backend/tests/unit/test_voice_speech.py
git commit -m "feat: speak validated claims with interruption"
```

### Task 6: Replace fallback UI actions with a specialized interface-control node

**Files:**
- Modify: `backend/app/agents/state.py`
- Modify: `backend/app/agents/graph.py`
- Modify: `backend/app/agents/tools/interface_tools.py`
- Modify: `backend/app/constants/ui_commands.py`
- Modify: `backend/app/services/prompts/agent.py`
- Modify: `backend/tests/unit/test_agent.py`
- Modify: `backend/tests/integration/test_agent.py`

**Interfaces:**
- Produces: `UiCapability` registry entries with command id, resource kind, resolver, and presentation-only policy.
- Produces: `control_interface(state: AgentState) -> {ui_commands, trace}` LangGraph node.

- [ ] **Step 1: Write failing controller tests**

Assert known resource ids resolve; hallucinated ids/coordinates are dropped; the budget is enforced; reasons cannot introduce measurements; model failure emits no fallback; command ids still mirror the frontend registry.

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/unit/test_agent.py -q`.

- [ ] **Step 3: Implement the capability registry and graph node**

Move command selection out of `synthesise` into `control_interface`. Bind data-bound tools whose arguments are opaque known ids; resolver metadata composes frontend params. Remove production use of `default_ui_commands` when AI is enabled.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/test_agent.py tests/integration/test_agent.py -q`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents backend/app/constants/ui_commands.py backend/app/services/prompts/agent.py backend/tests/unit/test_agent.py backend/tests/integration/test_agent.py
git commit -m "feat: add evidence-bound interface controller"
```

### Task 7: Build the hotkey voice session and terminal command

**Files:**
- Create: `backend/app/voice/session.py`
- Create: `backend/app/voice/turns.py`
- Create: `backend/app/cli/voice.py`
- Modify: `backend/app/agents/run.py`
- Modify: `backend/app/agents/tools/analysis_tools.py`
- Modify: `backend/app/services/pipeline/runner.py`
- Modify: `backend/app/cli/main.py`
- Create: `backend/tests/unit/test_voice_session.py`
- Create: `backend/tests/integration/test_voice_loop.py`

**Interfaces:**
- Adds optional `analysis_event_consumer` dependency to `converse`, captured by graph-node closures rather than checkpoint state.
- Produces: `VoiceTurnDecision(action, enabled_step_ids, response)` from structured model output.
- Produces: `VoiceSession.run()`, `activate()`, and `close()`.

- [ ] **Step 1: Write failing session tests**

Use fake capture/transcriber/synthesizer and the probe graph to assert: hotkey starts one turn; plan approval resumes LangGraph; active-run question is provisional; barge-in stops speech only; standby/resume preserve the run; explicit abandon cancels at a node boundary; completion supersedes provisional speech; UI/speech events retain ids.

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/unit/test_voice_session.py tests/integration/test_voice_loop.py -q`.

- [ ] **Step 3: Implement coordinator and dependency injection**

Use prompt-toolkit's async key binding for `Ctrl+P`. Launch the full agent turn with `asyncio.create_task`; keep the key loop responsive. Pass event observation through graph construction dependencies, never through checkpointed state. Route natural-language control only through structured LLM output.

- [ ] **Step 4: Verify GREEN and CLI help**

Run: `uv run pytest tests/unit/test_voice_session.py tests/integration/test_voice_loop.py -q && uv run aeris voice --help`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/voice backend/app/cli backend/app/agents backend/app/services/pipeline/runner.py backend/tests/unit/test_voice_session.py backend/tests/integration/test_voice_loop.py
git commit -m "feat: add conversational terminal voice loop"
```

### Task 8: Run audio, UI, regression, and real product gates; update truth

**Files:**
- Create: `backend/tests/integration/test_voice_audio_round_trip.py`
- Modify: `backend/bcontext/product-truth.md`
- Modify: `backend/bcontext/roadmap.md`
- Modify: `backend/bcontext/architecture-context.md`
- Modify: `backend/bcontext/folder-archtecture.md`
- Modify: `backend/bcontext/memory.md`

**Interfaces:**
- Produces retained `backend/runs/<session-id>/voice/` audio metrics, events, and gate notes.

- [ ] **Step 1: Write and RED-check the offline round-trip gate**

Synthesize a fixed test phrase, persist WAV, transcribe it, and assert the measured WER/latency record exists. Add declared-SNR noise variants and cancellation during the first utterance.

- [ ] **Step 2: Run focused model-asset gates**

Run: `uv run pytest tests/integration/test_voice_audio_round_trip.py -q -s`.

Expected: Kokoro and Whisper load locally, first-chunk/transcription metrics print, round-trip phrase meets the measured threshold, cancellation truncates output.

- [ ] **Step 3: Run frontend and backend regressions**

Run in `frontend`: `pnpm test && pnpm contracts:check && pnpm lint && pnpm exec tsc --noEmit && pnpm build`.

Run in `backend`: `uv lock --check && uv run pytest -q && uv run ruff check .`.

- [ ] **Step 4: Run the real terminal gate**

With `LLM_PROVIDER=openai` and a non-empty `LLM_API_KEY`, run `uv run aeris voice` with an actual microphone and headphones. Exercise plan approval, progress narration, barge-in, provisional question, standby/resume, grounded supersession, UI commands, and explicit abandonment. Retain the journal and report observed device/model latency.

- [ ] **Step 5: Update authoritative documentation**

Mark 1.13 done only if the real gate passes. State explicitly in product truth and roadmap that the USP is voice conversation plus contextual frontend control; narration without interface action is incomplete. Record model versions, machine profile, measured latencies/WER, scenarios, failures, and retained run paths in memory.

- [ ] **Step 6: Final verification and commit**

Run: `git diff --check && git status --short`.

```bash
git add backend frontend
git commit -m "feat: complete phase 1.13 voice loop"
```

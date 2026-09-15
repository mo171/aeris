# Phase 1.13 Voice Loop Design

## Product outcome

AERIS becomes a voice conversation that can operate the AERIS interface, not a chatbot with transcription and text-to-speech attached. In the Phase 1 terminal, `Ctrl+P` opens one microphone turn. AERIS then transcribes the operator, presents and obtains approval for its plan, keeps the terminal available while scientific work runs, narrates meaningful progress, speaks a claim-grounded result, and emits interface commands that the frontend command bus can validate and dispatch. The original, calm voice identity may have controlled British cadence but must not imitate an identifiable performer.

This is the product USP and an architectural requirement. Written, spoken, and shown output are coordinated projections of the same session evidence. Live browser microphone/audio transport remains Phase 2.4/2.7; Phase 1.13 nevertheless updates and tests the frontend event schemas and command-dispatch bridge so that transport later adds no product logic.

## Scope

Phase 1.13 includes:

- a terminal `aeris voice` session activated per turn with `Ctrl+P`, with no always-listening microphone;
- offline speech recognition using `faster-whisper` and Silero VAD-based endpointing;
- offline, chunked Kokoro synthesis and local playback;
- plan presentation and approval inside the voice session;
- barge-in, standby/resume, explicit run abandonment, narration, provisional answers, and grounded supersession;
- typed `speech` and `ui-command` events on the Phase 1 stream/journal contract;
- a specialized interface-control node that proposes safe, presentation-only commands from validated session resources;
- frontend stream adapters that validate and dispatch mocked `ui-command` events through the existing command registry;
- corrected frontend `speech` schemas capable of identifying, grounding, interrupting, and superseding an utterance;
- unit, contract, integration, audio-fixture, and real terminal verification with retained run logs.

This phase does not add FastAPI, WebSocket transport, browser microphone capture, browser audio playback, authentication, actor voice cloning, or a continuously listening wake-word model.

## Architectural decisions

### One session coordinator, not competing agents

One `VoiceSession` application service owns the terminal interaction lifecycle. It does not replace LangGraph orchestration: each full request still runs through the existing agent graph, and each scientific step still runs through the existing pipeline graph. The coordinator owns only device and turn lifecycle: hotkey activation, capture, playback, pending approval, standby state, and the active agent task.

The existing agent graph gains a dedicated interface-control node after grounded synthesis. This is a specialization within one agent identity, rather than a second autonomous agent with a competing memory. It receives only validated claims, evidence, layers, figures, and safe interface capabilities. It cannot compute measurements or alter scientific state.

While a full agent turn is running, the terminal remains responsive. A `Ctrl+P` turn can interrupt current speech and ask about the active work. A provisional responder uses the language model and the active trace snapshot without entering or mutating the busy agent graph thread. The resulting utterance is explicitly provisional, has no claim ids, and is superseded when the grounded result arrives. New scientific work is not silently started on the same busy graph thread.

### Activation and interruption

The microphone is closed while idle. `Ctrl+P` has three deterministic device effects, all already implied by the approved product rules:

1. stop the currently interruptible utterance;
2. open one capture turn;
3. end capture after model-based VAD observes speech followed by configured silence, or when the operator presses `Ctrl+P` again.

That device behavior is not natural-language routing. The transcript is classified by a structured language-model call into plan approval, question, standby, resume, or explicit abandonment. No synonym list or `if transcript in {...}` vocabulary shortcut is permitted. When classification or response generation fails, AERIS reports the AI error and does not guess an action.

Barge-in cancels only the current utterance's synthesis/playback task. Standby suppresses subsequent speech while runs and event journals continue. Explicit abandonment invokes the existing node-boundary cancellation path and preserves the checkpoint.

### Audio pipeline

`sounddevice.RawInputStream` and `RawOutputStream` are used through blocking reads/writes offloaded with `asyncio.to_thread`, preserving the backend's async boundary without introducing synchronous application callbacks. Input is mono 16 kHz PCM16. Output uses the sample rate produced by Kokoro, currently 24 kHz.

Silero VAD owns speech detection and endpointing; AERIS does not invent an RMS threshold. `faster-whisper` owns transcription and receives the VAD-delimited waveform. Both model name/device/compute type and VAD timing are validated settings in `config.py`. The default profile is chosen from measured latency and word error rate on the target machine, not assumed in code.

Kokoro is selected over the archived Piper line because it provides a current Apache-licensed 82M model and a chunk-yielding Python pipeline suitable for responsive local playback. The configured voice id is an original stock Kokoro voice. Text is synthesized in speakable clauses, queued in order, and cancellable by utterance id. Audio generation or playback failure fails that utterance explicitly while leaving the scientific run untouched.

### Speech truth boundary

`SpeechEvent` carries:

- the owning `runId` or `messageId`;
- `utteranceId`;
- AI-authored `text`;
- `audioUrl`, nullable while Phase 1 audio is streamed locally;
- `claimIds`;
- `interruptible`;
- `provisional`;
- optional `supersedesUtteranceId`.

Grounded speech is generated directly from validated claims and typed refusals through a dedicated voice prompt and the existing numeric/identifier guard. It is never produced by reading chat Markdown. Grounded utterances require non-empty claim ids unless the payload is an explicit typed refusal that identifies its source run. Provisional speech is the only ordinary empty-claim case and must set `provisional=true`. Narration is generated from trace facts, is labelled as progress rather than a result, and may not introduce a measurement.

If AI-authored speech fails validation, it is regenerated from the same dossier within the model call policy. If it still fails, the speech surface reports a generation error or remains silent according to standby state; it never substitutes fixed prose while AI is enabled.

### Interface-control boundary

The frontend command bus remains authoritative. The backend proposes commands; the frontend independently looks up the command, parses parameters with its mounted Zod schema, checks `isEnabled()`, and dispatches.

The interface-control node receives a data-driven capability registry rather than an expanding command `if/elif` tree. Each backend capability records the frontend command id, agent description, parameter resolver, and the validated resource kind it may reference. The model selects a capability and opaque resource ids. Backend resolvers turn only known session resources into frontend parameters; the model cannot invent claim ids, evidence ids, layer ids, coordinates, report ids, or scene ids. Presentation-only commands without resource parameters are explicitly marked in the registry.

The first production capability set covers spotlighting a claim, focusing evidence, showing a layer, focusing a known camera target, opening a completed report, and exposing the trace when it helps explain progress. The set is a documented safety registry in `constants/`, permitted by the existing presentation-only command rule. Generated contract tests ensure every id exists in the frontend registry. Unknown commands, invalid parameters, disabled handlers, rate-limit excess, and failed handlers are logged and not retried or replaced with another command.

The existing deterministic `default_ui_commands` behavior is not used as an AI failure fallback. With AI enabled, UI language and selection are AI-authored from validated resources; if the model fails, no command is emitted. Test and deliberately AI-disabled paths may inject explicit fixtures, but cannot masquerade as production inference.

### Frontend bridge

Both assistant and analysis stream handlers gain one small adapter for `ui-command`: call `dispatchCommand(event.commandId, event.params)`, retain the discriminated result for observability, and never throw into or terminate the parent stream. The command registry remains the only place handlers execute and parameters are parsed.

The frontend does not play `speech` in this phase. It does validate the complete corrected event and exposes it to a future voice transport adapter. This prevents Phase 2.7 from redefining utterance identity, grounding, cancellation, or supersession.

## Data flow

```text
Ctrl+P
  -> capture PCM until VAD endpoint
  -> faster-whisper transcript
  -> voice turn classifier
       -> pending plan: approve/revise through LangGraph interrupt
       -> active run: provisional response / standby / resume / explicit abandon
       -> idle: launch full agent turn as an asyncio task
            -> understand -> plan -> interrupt for approval -> execute scientific graphs
            -> trace observer -> AI progress narration -> Kokoro chunks -> audio output
            -> validated claims -> grounded voice synthesis
            -> interface-control node -> typed ui-command events
  -> terminal renderer + JSONL journal

Mocked frontend stream
  -> Zod event parse
  -> ui-command bridge
  -> command registry lookup -> paramsSchema.safeParse -> isEnabled -> handler
```

The active agent task and audio input loop are separate tasks. The graph is never stored in audio state, and device handles are never checkpointed. Session state stores ids and typed lifecycle facts only.

## Failure behavior

- Silence or VAD timeout produces no agent request and no invented transcript.
- Missing microphone/output device fails startup with the device query and remediation; it does not select an arbitrary device silently.
- STT failure retains the audio fixture/log reference and returns to idle.
- LLM configuration or provider failure prevents natural-language classification, provisional answers, grounded speech, and UI selection from pretending to work.
- TTS model or playback failure emits an utterance failure, leaves text/UI/scientific work intact, and returns the audio surface to idle.
- Barge-in and standby never call run cancellation.
- Only a classified explicit abandonment reaches `RunHandle.abandon()`.
- A malformed frontend command is dropped with its dispatch result and does not terminate the assistant or analysis stream.
- Event journals remain replayable and contain utterance identity, claim references, supersession, and UI reasons.

## Configuration and model assets

All voice settings live in `config.py` and `.env.example`: input/output device selectors, sample rates, Whisper model/device/compute type/language, VAD silence/capture limits, Kokoro model/voice/speed, narration policy, and UI command rate budget. Model weights are cached under the existing model directory. No hosted speech API key is required.

Natural conversational behavior requires a configured language-model provider and `LLM_API_KEY`; `LLM_PROVIDER=none` is not accepted for the production voice gate. Tests may inject deterministic fake models at dependency boundaries, but production code does not contain hard-coded language fallbacks.

## Verification strategy

### Unit and contract tests

- VAD endpointing: silence, speech then silence, background noise below speech probability, maximum capture duration, and rapid reactivation.
- Transcription: a checked-in, consented short WAV fixture yields the expected normalized phrase with measured word error rate.
- Speech queue: ordered chunks, cancellation by utterance id, non-interruptible safety/refusal behavior, standby suppression, synthesis failure, and output-device failure.
- Speech truth: grounded claim ids required, provisional empty ids allowed only when labelled, supersession references an earlier utterance, and unsupported numerals are rejected.
- Turn control: `Ctrl+P` barge-in cancels playback but not the active run; standby/resume do not touch the run; only explicit abandonment does.
- UI control: unknown ids and hallucinated resource ids are dropped; known resources resolve; command budget is enforced; model failure emits no deterministic replacement.
- Backend serialized `speech` and `ui-command` events validate against the frontend-exported JSON schemas.

### Frontend tests

Vitest is added as the minimal test runner for pure TypeScript behavior. Tests register real command definitions with Zod schemas and feed mocked validated stream events through the bridge. They prove successful dispatch, unknown command, invalid parameters, disabled command, failing handler, and that every failure leaves subsequent stream events processable. React rendering and WebSocket audio are outside this phase.

### Audio integration and real gate

The offline round-trip suite synthesizes a fixed, non-scientific test phrase with Kokoro, records the PCM/WAV artifact, transcribes it with faster-whisper, and reports normalized word error rate, synthesis first-chunk latency, transcription latency, and real-time factor. Noise variants are produced from the same retained fixture at declared signal-to-noise ratios; thresholds are accepted only after measurement on the target machine.

The real terminal gate uses an actual microphone and speaker/headphones. The operator presses `Ctrl+P`, asks a real investigation question, hears the plan, approves it with another `Ctrl+P` turn, interrupts narration, asks a follow-up while analysis continues, exercises standby/resume, and receives a grounded result containing a real claim measurement. A second run exercises explicit abandonment. The journal and audio metrics are retained under `backend/runs/<session-id>/voice/`.

UI behavior is verified independently in Phase 1.13 by replaying the same `ui-command` events into the frontend command bus with mocked transport. Live browser microphone, playback, and backend connection are the explicit Phase 2.4/2.7 gate.

## Documentation changes on completion

`product-truth.md`, `roadmap.md`, `api-contract.md`, `architecture-context.md`, `folder-archtecture.md`, `.env.example`, and `memory.md` are updated together. They will state unambiguously that AERIS's USP is a continuous voice conversation whose agent controls the AERIS frontend when evidence, context, or progress warrants it; voice-only narration without interface action does not satisfy the product definition.

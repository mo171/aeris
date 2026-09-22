# V-1 Local Kokoro Voice Design

**Date:** 2026-09-22  
**Status:** Approved for implementation planning  
**Scope:** V-1 frontend voice experience only

## Objective

Reduce the perceived and measured latency of the AERIS speech loop while improving voice consistency. Speech output must use Kokoro's British male George voice (`bm_george`) on the local Windows demo machine. The existing speech-to-text and response-generation path remains unchanged unless measurement identifies a separate bottleneck.

## Constraints

- The demo runs locally on the same Windows laptop.
- A one-time model preparation download of roughly 90 MB is acceptable before recording.
- The model must be cached so normal demo interactions do not depend on downloading it again.
- Model inference must not block React rendering, globe interaction, or microphone controls.
- The frontend must remain usable while the model is preparing.
- Existing voice interruption and mute behavior must continue to work.
- This work must not expand into the Python backend or the broader AERIS processing architecture.

## Selected Architecture

Run quantized Kokoro inference in a dedicated browser Web Worker. Use the `onnx-community/Kokoro-82M-v1.0-ONNX` model with q8 weights and the `bm_george` voice.

The application starts model preparation as soon as the voice experience becomes relevant, before the first spoken response. Model files are loaded through the supported Kokoro JavaScript runtime and retained by the browser cache. The worker owns model initialization and synthesis so ONNX execution cannot stall the main UI thread.

The Next.js voice API continues to perform transcription, response generation, and command mapping. It returns reply text and actions without waiting for cloud TTS. The browser sends the returned reply to the ready Kokoro worker, then plays the generated 24 kHz audio through the existing speech playback boundary.

## Why This Architecture

### Browser worker instead of the Next.js route

- Removes TTS network latency from every warm voice turn.
- Avoids base64 audio expansion in API responses.
- Allows the API reply and UI actions to arrive without waiting for speech synthesis.
- Keeps expensive ONNX work away from the UI thread.
- Makes the demo independent of ElevenLabs plan limits and cloud TTS availability.

### q8 instead of full precision

The q8 model is substantially smaller than fp32 while preserving the confirmed George voice quality. It is the appropriate balance for a local demo where startup preparation is acceptable but warm response speed matters.

## Components

### Kokoro worker

A dedicated worker module will:

- initialize one Kokoro model instance;
- use q8 model weights;
- synthesize exclusively with `bm_george` unless configuration explicitly changes;
- report lifecycle states: `idle`, `loading`, `ready`, `synthesizing`, and `error`;
- return transferable audio data rather than base64 strings;
- serialize synthesis requests to prevent overlapping inference;
- support cancellation by discarding stale results using request identifiers.

### Kokoro client

A small typed client will own worker communication and expose a stable interface:

- `prepare()` for preloading;
- `synthesize(text, requestId)` for speech generation;
- `cancel(requestId)` for interruption;
- readiness and diagnostic events.

This isolates model/runtime details from the voice session manager.

### Voice session integration

The existing voice session manager will:

- begin Kokoro preparation during voice connection or an earlier safe idle point;
- continue showing the existing UI while preparation runs;
- render the text reply and execute validated UI actions as soon as the API responds;
- synthesize the reply locally with George;
- send audio to the existing playback layer;
- cancel queued or playing speech on barge-in, mute, or disconnect.

### API route

The route will no longer perform ElevenLabs or OpenAI synthesis on the normal V-1 path. It will return the validated reply and mapped actions immediately after response generation. Cloud TTS code may remain temporarily behind an explicit fallback boundary until the local path is verified, but provider switching must never be silent.

## Model Preparation and Caching

The preparation workflow will use the runtime's supported browser caching. A dedicated preparation status must distinguish downloading from ready state. The demo operator can prepare the model before recording and verify readiness without speaking a command.

Model URLs and voice identity will be centralized as typed configuration rather than duplicated string literals. The initial configuration is:

- model: `onnx-community/Kokoro-82M-v1.0-ONNX`;
- quantization: `q8`;
- voice: `bm_george`;
- output sample rate: 24 kHz.

No model binary will be committed to Git unless runtime caching proves unreliable on the target laptop. If a frozen local asset becomes necessary, that is a separate reviewed change because it materially increases repository size.

## Data Flow

1. The operator opens AERIS or enables voice mode.
2. The Kokoro client asks the worker to prepare the q8 model.
3. The browser obtains microphone audio and the existing route handles STT and response generation.
4. The route returns transcript, reply text, and actions without synthesizing audio.
5. The UI applies the response and submits the clean reply text to Kokoro.
6. The worker synthesizes `bm_george` audio and transfers it to the main thread.
7. The speech player begins playback and retains existing interruption controls.

## Failure Handling

- Model preparation failure must be logged with a concrete reason and reflected in voice status.
- A configured cloud fallback may synthesize only after an explicit local failure; the selected provider must be included in diagnostics.
- If both local and fallback synthesis fail, the textual response and UI actions still succeed.
- Stale synthesis results are ignored after interruption or a newer voice request.
- Empty or excessively long speech input is rejected or split according to a documented maximum, not sent blindly to the worker.

## Latency Strategy

- Start model preparation before the first response needs speech.
- Keep one model instance alive for the browser session.
- Return API text before TTS completes.
- Transfer binary audio buffers instead of encoding base64.
- Avoid concurrent model initialization and duplicate synthesis work.
- Record timing marks for model preparation, API response, synthesis, and first playback.

The primary metric is warm time from API reply receipt to first audible George speech. Cold preparation time is reported separately and excluded from normal turn latency once the demo is prepared.

## Testing and Acceptance

### Automated tests

- Worker/client protocol handles prepare, synthesize, cancellation, errors, and stale responses.
- Voice session sends returned reply text to Kokoro with `bm_george`.
- API route completes successfully without cloud-generated `audioBase64` on the normal local path.
- Mute and interruption stop or discard speech correctly.
- Existing speech player tests continue to pass.

### Runtime verification on the demo laptop

- Prepare the model once and confirm subsequent loads use the browser cache.
- Confirm the active voice is `bm_george`.
- Measure cold preparation time separately.
- Measure at least three warm turns from API reply to playback.
- Verify the UI remains responsive during synthesis.
- Verify activation greeting, normal response, mute, barge-in, and reconnect behavior.
- Verify a production Next.js build.

## Out of Scope

- Replacing Whisper or browser speech recognition.
- Reworking OpenAI response generation.
- Creating a general-purpose TTS service.
- Supporting multiple selectable voices in V-1.
- Deploying Kokoro for multi-user production traffic.
- Modifying the Python backend.


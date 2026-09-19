# Phase 2.4 WebSocket Voice Architecture Design

## 1. Executive Summary
Phase 2.4 implements bidirectional real-time voice streaming between the AERIS web application (browser) and the FastAPI backend over a low-latency WebSocket connection. It allows operators to converse with AERIS naturally, command the 3D Cesium interface via voice, approve autonomous plans, and interrupt ongoing speech (barge-in), while maintaining the AI-first invariant (ADR-005) with zero synthetic fallbacks or hardcoded shortcuts.

## 2. Product Context & Objectives
- **Product Requirement**: AERIS is an autonomous Earth Observation intelligence assistant. Voice is a primary interface modality.
- **Roadmap Milestone**: `| 2.4 | WebSocket | Bidirectional: audio frames in, events out | Voice from the browser, end to end |`
- **Future-Proofing (Phase 2.5 Inngest)**: The WebSocket connection handles real-time audio transport (<30ms frames for Silero VAD / Whisper) and delegates agent scientific graph execution to `InvestigationRunService`. When Phase 2.5 introduces Inngest for durable graph execution, the audio transport remains unchanged.

## 3. Protocol & Framing Architecture
### Endpoint: `/api/v1/voice/ws`
Multiplexes raw binary audio frames and typed JSON control/event messages over a single bidirectional WebSocket connection.

### Inbound Frames (Client -> Server)
1. **Binary Frames**:
   - Format: Linear PCM16 mono 16 kHz (`<i2`, little-endian).
   - Frame size: 512 samples (32 ms, 1024 bytes) or 1024 samples (64 ms, 2048 bytes).
   - Routed to: `WebSocketAudioCapture` -> Silero VAD state machine.
2. **JSON Control Messages**:
   - `start_turn`: Explicit push-to-talk press or activation.
   - `end_turn`: Explicit push-to-talk release or manual end of speech.
   - `interrupt`: Immediate barge-in; cancels current Kokoro TTS synthesis and flushes audio buffers without stopping ongoing scientific computation.
   - `standby`: Suppresses audio narration while background runs continue.
   - `resume`: Restores audio narration.
   - `approve_plan`: Approves or strikes steps from the agent's proposed plan (`approvedStepIds: string[]`).
   - `abandon`: Explicit operator request to abort the running investigation step.

### Outbound Frames (Server -> Client)
1. **Binary Frames**:
   - Format: Linear PCM16 mono 24 kHz yielded directly by Kokoro/Piper for instant streaming playback.
2. **JSON Event Messages**:
   - `session_state`: `idle` | `listening` | `transcribing` | `thinking` | `speaking` | `standby`.
   - `transcript`: `text`, `language`, `isFinal`.
   - Canonical stream events: `speech`, `ui-command`, `trace-step`, `layer-ready`, `claim`, `figure-ready`, `run-complete`, `run-error`.

## 4. Backend Architecture
### File Layout:
- `backend/app/routes/voice.py`: FastAPI WebSocket router mounting `/api/v1/voice/ws`.
- `backend/app/voice/audio_transport.py`:
  - `WebSocketAudioCapture`: Asynchronous queue-based audio source fulfilling the Silero VAD consumer contract.
  - `WebSocketAudioPlayback`: Real-time streaming sink transmitting `AudioChunk` samples as binary frames over WebSocket.
- `backend/app/voice/session.py`: Coordinates turn lifecycle, delegating scientific execution to `InvestigationRunService`.
- `backend/app/main.py`: Includes `voice.router` under `/api/v1`.

### Lifecycle & Concurrency:
- On connection, a dedicated `VoiceSession` is bound to the WebSocket.
- Concurrent reader task handles inbound messages (binary -> VAD queue, JSON -> control handler).
- Session runner task observes the run event fanout, pushing canonical JSON stream events to the client.
- Disconnections (`WebSocketDisconnect`) trigger graceful cleanup, ensuring no background tasks or audio capture loops leak.

## 5. Frontend Architecture
### File Layout:
- `frontend/public/audio-processors/pcm-capture-processor.js`: AudioWorklet processor converting browser microphone Float32 stream to 16 kHz mono Int16 PCM chunks.
- `frontend/lib/audio/speech-stream-player.ts`: Web Audio API `AudioContext` (24 kHz) scheduler for gapless chunked playback with instant barge-in cutoff (`abort()`).
- `frontend/features/voice/hooks/use-voice-session.ts`: Custom hook managing WebSocket connection, audio worklet pipeline, hotkey bindings, and event dispatching.
- `frontend/features/voice/components/voice-activation-button.tsx`: Aerospace-themed "Activate AERIS Voice" button that triggers browser permission, unlocks `AudioContext`, and establishes the uplink with an audible chime ("AERIS voice link active").
- `frontend/features/voice/components/voice-control-bar.tsx`: Floating HUD status bar and PTT button with live telemetry states (`IDLE`, `LISTENING`, `THINKING`, `SPEAKING`, `STANDBY`) and global `Ctrl+P` push-to-talk hotkey.

## 6. Verification & Test Plan
1. **Backend Integration Tests (`tests/integration/api/test_voice_websocket.py`)**:
   - WebSocket connection handshake and state announcements.
   - Streaming binary PCM audio chunks through `WebSocketAudioCapture` into VAD.
   - Handling control messages (`interrupt`, `standby`, `resume`, `approve_plan`).
   - Clean shutdown upon client disconnect.
2. **Frontend Unit & Contract Tests (`pnpm test`)**:
   - `AudioWorklet` processor downsampling & buffer formatting.
   - `SpeechStreamPlayer` buffer scheduling and interrupt flushing.
   - Event schema validation matching backend payloads.
3. **End-to-End Testing with Playwright (`webapp-testing`)**:
   - Load the web application with backend running.
   - Click "Activate AERIS Voice" and verify WebSocket status transitions to `CONNECTED`.
   - Verify `Ctrl+P` hotkey activates the listening state and pulses the HUD bar.

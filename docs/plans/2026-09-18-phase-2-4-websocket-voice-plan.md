# Phase 2.4 WebSocket Voice Implementation Plan

> **Goal:** Build bidirectional real-time WebSocket voice streaming between the browser frontend and FastAPI backend, enabling natural voice queries, Cesium 3D camera/layer control, plan approval, and instant barge-in without synthetic fallbacks.

**Architecture:** A dedicated FastAPI WebSocket endpoint (`/api/v1/voice/ws`) interfaces with `VoiceSession` via an asynchronous network transport (`WebSocketAudioCapture` and `WebSocketAudioPlayback`), streaming 16 kHz PCM frames to Silero VAD / Whisper and 24 kHz Kokoro chunks back to the browser. The frontend uses a Web Audio `AudioWorklet` for microphone downsampling, a chunked `SpeechStreamPlayer`, and an aerospace-themed HUD widget with `Ctrl+P` push-to-talk. Agent runs are dispatched cleanly to `InvestigationRunService` so Phase 2.5 can introduce Inngest without changing audio transport.

**Tech Stack:** FastAPI WebSockets, Web Audio API (`AudioWorklet`, `AudioContext`), Silero VAD, faster-whisper, Kokoro TTS, Zustand, React 19 / Next.js 15, Tailwind CSS, Playwright.

---

### Task 1: Backend WebSocket Audio Transport & Router

**Files:**
- Create: `backend/app/voice/audio_transport.py`
- Create: `backend/app/routes/voice.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/api/test_voice_websocket.py`

**Step 1: Write the failing test**
Create `backend/tests/integration/api/test_voice_websocket.py`:
- Test connecting to `/api/v1/voice/ws`.
- Verify initial `session_state` frame is received (`{"type": "session_state", "state": "idle"}`).
- Send binary PCM16 audio chunks and control frames (`{"type": "start_turn"}`, `{"type": "end_turn"}`, `{"type": "interrupt"}`).
- Verify server returns appropriate session transitions and handles clean disconnect.

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/integration/api/test_voice_websocket.py -v`
Expected: FAIL (route does not exist).

**Step 3: Implement minimal code**
1. Implement `backend/app/voice/audio_transport.py`:
   - `WebSocketAudioCapture`: Implements async `read_chunk()` and `stream_chunks()` from an `asyncio.Queue[bytes]`.
   - `WebSocketAudioPlayback`: Implements `play_chunk()` sending binary bytes to the WebSocket, and `abort()` to flush output.
2. Implement `backend/app/routes/voice.py`:
   - Declare WebSocket route `/ws`.
   - Wire `WebSocketAudioCapture`, `WebSocketAudioPlayback`, and `VoiceSession`.
   - Create read loop dispatching binary bytes to capture and JSON commands (`start_turn`, `end_turn`, `interrupt`, `standby`, `resume`, `approve_plan`, `abandon`) to session methods.
   - Forward run fanout events as JSON messages.
3. Modify `backend/app/main.py`: Include `voice.router` with prefix `/api/v1/voice`.

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/integration/api/test_voice_websocket.py -v`
Expected: PASS.

---

### Task 2: Frontend Web Audio Capture Worklet & Streaming Player

**Files:**
- Create: `frontend/public/audio-processors/pcm-capture-processor.js`
- Create: `frontend/lib/audio/speech-stream-player.ts`
- Test: `frontend/tests/audio/speech-stream-player.test.ts`

**Step 1: Write the failing test**
Create `frontend/tests/audio/speech-stream-player.test.ts` testing `SpeechStreamPlayer`:
- Enqueuing PCM16 chunks.
- Scheduled timing on mocked Web Audio `AudioContext`.
- Immediate interruption flushing and buffer stop on `abort()`.

**Step 2: Run test to verify it fails**
Run: `pnpm test speech-stream-player`
Expected: FAIL.

**Step 3: Implement minimal code**
1. `pcm-capture-processor.js`:
   - Extends `AudioWorkletProcessor`.
   - In `process(inputs)`: takes Float32 mono input, converts to Int16 Little-Endian PCM, buffers to 512 samples (32 ms), and calls `this.port.postMessage(buffer, [buffer])`.
2. `speech-stream-player.ts`:
   - Manages 24 kHz `AudioContext`.
   - Converts binary Int16 chunks to Float32 AudioBuffers, scheduling them sequentially to achieve gapless playback.
   - `abort()` cancels scheduled sources instantly and resets playback timeline.

**Step 4: Run test to verify it passes**
Run: `pnpm test speech-stream-player`
Expected: PASS.

---

### Task 3: Frontend Reactive Voice Session Store, Hook & UI Widgets

**Files:**
- Create: `frontend/features/voice/store/voice-store.ts`
- Create: `frontend/features/voice/hooks/use-voice-session.ts`
- Create: `frontend/features/voice/components/voice-activation-button.tsx`
- Create: `frontend/features/voice/components/voice-control-bar.tsx`
- Modify: `frontend/app/(workspace)/investigations/[id]/page.tsx` (mount voice activation and control bar)

**Step 1: Implement Voice Store & Hook**
1. `voice-store.ts`:
   - Zustand store tracking connection state (`disconnected`, `connecting`, `connected`), voice state (`idle`, `listening`, `transcribing`, `thinking`, `speaking`, `standby`), and audio meters.
2. `use-voice-session.ts`:
   - Handles `new WebSocket(wsUrl)`.
   - Sets up `navigator.mediaDevices.getUserMedia` and attaches `pcm-capture-processor`.
   - Binds `Ctrl+P` global keyboard listener for push-to-talk.
   - Automatically bridges inbound `ui-command` events to `dispatchCommand()` from `useInvestigationCommands`.

**Step 2: Build UI Components**
1. `voice-activation-button.tsx`:
   - Aerospace-themed button ("Activate AERIS Voice") in the top header.
   - Unlocks `AudioContext` upon user click and plays the confirmation chime: "AERIS voice link active".
2. `voice-control-bar.tsx`:
   - Docked HUD widget at bottom of screen.
   - Shows live state badge (IDLE, LISTENING, THINKING, SPEAKING, STANDBY), dynamic audio pulse ring, PTT button, and standby toggle.

**Step 3: Build & Lint Check**
Run: `pnpm build`
Expected: Clean build with 0 TypeScript/lint errors.

---

### Task 4: Architectural Review & Zero-Hardcoding Audit Subagent

- **Role**: Senior Architect & Fullstack Auditor.
- **Audit Checklist**:
  - Zero canned responses or mock stubs in the WebSocket route or voice adapters.
  - WebSocket error handling: safe task cancellation on disconnect without orphan processes.
  - Type alignment between backend Pydantic models and frontend Zod schemas.
  - Conformance to ADR-005 (AI-first invariant) and project design standards.

---

### Task 5: End-to-End Verification with Webapp Testing (Playwright)

**Files:**
- Create: `frontend/e2e/voice-interaction.spec.ts`

**Steps:**
1. Start backend server: `uv run uvicorn app.main:app --port 8000` (in `backend/`).
2. Start frontend dev server: `pnpm dev --port 3000` (in `frontend/`).
3. Run Playwright E2E test:
   - Navigate to investigation page.
   - Locate and click "Activate AERIS Voice".
   - Verify WebSocket connects successfully.
   - Trigger push-to-talk (`Ctrl+P`) and verify HUD transitions to `LISTENING`.
   - Release push-to-talk and verify transition to `THINKING`.
   - Capture screenshot and verify visual presentation.

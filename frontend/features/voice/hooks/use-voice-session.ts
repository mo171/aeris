// features/voice/hooks/use-voice-session.ts — AERIS Voice AI Session Manager.
//
// what  : Full hands-free voice control via Ctrl+P push-to-talk, MediaRecorder audio capture,
//         Next.js API orchestration with OpenAI Whisper/GPT-5, local Kokoro TTS, and UI command execution.
// persona : Authentic British aerospace AI assistant (polite, witty, articulate).
// where : Mounted by InvestigationScreen, VoiceActivationButton, and VoiceControlBar.

"use client";

import { useCallback, useEffect } from "react";
import { toast } from "sonner";

import { KokoroSpeechClient } from "@/lib/audio/kokoro-client";
import { SpeechStreamPlayer } from "@/lib/audio/speech-stream-player";
import { dispatchUiCommandEvent } from "@/lib/streaming/ui-command-bridge";
import { useMissionCommandStore } from "@/features/missionCommand/store/mission-command-store";
import { useVoiceStore } from "../store/voice-store";

export interface OperatorContext {
  /** Route pathname — tells the brain which screen's commands exist right now. */
  surface: string;
  /** Scenes selected on Mission Command. Empty anywhere else. */
  selectedSceneIds: string[];
}

/**
 * The brain cannot decide what an order means without seeing what the operator
 * sees. Every voice turn carries the live surface and selection so tool choice
 * is grounded in the actual UI state, not in guesses.
 */
function collectOperatorContext(): OperatorContext {
  let selectedSceneIds: string[] = [];
  try {
    selectedSceneIds = useMissionCommandStore.getState().selectedSceneIds ?? [];
  } catch {
    selectedSceneIds = [];
  }
  const surface =
    typeof window !== "undefined" ? window.location.pathname : "unknown";
  return { surface, selectedSceneIds };
}

interface ProcessVoiceResponse {
  success: boolean;
  transcript?: string;
  reply?: string;
  actions?: Array<{
    commandId: string;
    params: Record<string, unknown>;
    description: string;
  }>;
  audioBase64?: string | null;
  error?: string;
}

/**
 * Encodes a Float32Array of raw PCM audio samples into a standard 16-bit PCM RIFF WAV Blob.
 * Universally supported by OpenAI Whisper with zero container ambiguity.
 */
function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  // RIFF chunk descriptor
  view.setUint8(0, 0x52); // 'R'
  view.setUint8(1, 0x49); // 'I'
  view.setUint8(2, 0x46); // 'F'
  view.setUint8(3, 0x46); // 'F'
  view.setUint32(4, 36 + samples.length * 2, true);
  view.setUint8(8, 0x57);  // 'W'
  view.setUint8(9, 0x41);  // 'A'
  view.setUint8(10, 0x56); // 'V'
  view.setUint8(11, 0x45); // 'E'

  // fmt sub-chunk
  view.setUint8(12, 0x66); // 'f'
  view.setUint8(13, 0x6d); // 'm'
  view.setUint8(14, 0x74); // 't'
  view.setUint8(15, 0x20); // ' '
  view.setUint32(16, 16, true); // Subchunk1Size
  view.setUint16(20, 1, true);  // AudioFormat (1 = PCM)
  view.setUint16(22, 1, true);  // NumChannels (1 = mono)
  view.setUint32(24, sampleRate, true); // SampleRate
  view.setUint32(28, sampleRate * 2, true); // ByteRate
  view.setUint16(32, 2, true);  // BlockAlign
  view.setUint16(34, 16, true); // BitsPerSample

  // data sub-chunk
  view.setUint8(36, 0x64); // 'd'
  view.setUint8(37, 0x61); // 'a'
  view.setUint8(38, 0x74); // 't'
  view.setUint8(39, 0x61); // 'a'
  view.setUint32(40, samples.length * 2, true);

  // Convert float32 [-1.0, 1.0] to 16-bit PCM signed integers
  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  return new Blob([buffer], { type: "audio/wav" });
}

/**
 * Resamples Float32 audio data to the target sample rate (default 16kHz for Whisper).
 */
function resampleAudio(audioData: Float32Array, origRate: number, targetRate = 16000): Float32Array {
  if (origRate === targetRate || origRate <= 0) return audioData;
  const ratio = origRate / targetRate;
  const newLength = Math.round(audioData.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    const origIndex = i * ratio;
    const index = Math.floor(origIndex);
    const frac = origIndex - index;
    const s0 = audioData[index] || 0;
    const s1 = audioData[index + 1] || s0;
    result[i] = s0 + frac * (s1 - s0);
  }
  return result;
}

/** Where a turn came from, recorded on each chat message. */
type TurnOrigin = "voice" | "text";

class AerisSessionManager {
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private pcmChunks: Float32Array[] = [];
  private processorNode: ScriptProcessorNode | null = null;
  private silentGainNode: GainNode | null = null;
  private micStream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private animFrameId: number | null = null;
  private currentAudioElement: HTMLAudioElement | null = null;
  private isPttActive: boolean = false;
  private isListenersBound: boolean = false;
  private speechRecognizer: any = null;
  private realTimeTranscript: string = "";
  private readonly kokoro = new KokoroSpeechClient();
  private readonly speechPlayer = new SpeechStreamPlayer();
  private speechTurn = 0;

  /**
   * Records one side of a turn in chat — the only place conversation text
   * lives. Prefers the assistant transcript when its panel is mounted
   * (Mission Command); otherwise the voice thread, which the investigation
   * Chat tab renders. Floating popovers and toasts are never used.
   */
  private appendToChat(role: "operator" | "aeris", text: string, origin: TurnOrigin): void {
    const trimmed = text.trim();
    if (!trimmed) return;
    const controls = useMissionCommandStore.getState().assistantControls;
    if (controls) {
      controls.appendMessage(role, trimmed);
    } else {
      useVoiceStore.getState().appendVoiceMessage(role, trimmed, origin);
    }
  }

  bindGlobalListeners() {
    if (this.isListenersBound || typeof window === "undefined") return;
    this.isListenersBound = true;

    // Permanently suppress and cancel any default browser/Microsoft speech synthesis
    if ("speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
      } catch {}
    }

    window.addEventListener("keydown", this.handleKeyDown);
    window.addEventListener("keyup", this.handleKeyUp);

    // Model preparation is network/CPU work and can start before audio is
    // unlocked. By the time the operator enables voice, George is usually ready.
    void this.kokoro.prepare().catch((error: unknown) => {
      console.error("[AERIS VOICE] Local Kokoro preparation failed:", error);
    });
  }

  private handleKeyDown = (e: KeyboardEvent) => {
    // Hold Ctrl+P (or Meta+P) for Push-to-Talk
    if ((e.ctrlKey || e.metaKey) && (e.key === "p" || e.key === "P")) {
      e.preventDefault();
      const status = useVoiceStore.getState().connectionStatus;
      if (status !== "connected") {
        toast.info("Please click 'VOICE UPLINK' in the header first to activate voice mode.");
        return;
      }
      if (!this.isPttActive) {
        this.isPttActive = true;
        void this.startRecording();
      }
    }
  };

  private handleKeyUp = (e: KeyboardEvent) => {
    if (e.key === "p" || e.key === "P") {
      if (this.isPttActive) {
        this.isPttActive = false;
        void this.stopRecordingAndProcess();
      }
    }
  };

  async connect(): Promise<void> {
    const store = useVoiceStore.getState();
    if (store.connectionStatus === "connected") return;

    // Silence any browser speech engine
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
      } catch {}
    }

    store.setConnectionStatus("connecting");
    try {
      this.bindGlobalListeners();

      // 1. Request microphone permission on user gesture
      this.micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      // 2. Initialize AudioContext on user gesture to unlock browser audio policy
      const AudioCtx =
        window.AudioContext ||
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (window as any).webkitAudioContext;
      if (!this.audioContext || this.audioContext.state === "closed") {
        this.audioContext = new AudioCtx();
      }
      if (this.audioContext.state === "suspended") {
        await this.audioContext.resume();
      }
      await this.speechPlayer.resume();

      // 3. Play futuristic activation chime
      this.playChime();

      store.setConnectionStatus("connected");
      store.setVoiceState("idle");

      // Exactly the user's requested activation feedback
      toast.success("Voice command mode activated");

      // AERIS speaks the activation greeting aloud
      void this.playActivationGreeting();
    } catch (err) {
      console.error("Failed to activate voice uplink:", err);
      store.setConnectionStatus("error", "Microphone access denied");
      toast.error("Microphone access denied. Please allow microphone permissions to use VOICE UPLINK.");
    }
  }

  private async playActivationGreeting(): Promise<void> {
    const store = useVoiceStore.getState();
    // Voice-only: the greeting is spoken, never rendered as text.
    store.setVoiceState("speaking");

    if (store.isMuted) {
      store.setVoiceState("idle");
      return;
    }

    // The pre-rendered file remains an explicit offline fallback only.
    const playUrl = async (url: string): Promise<boolean> => {
      try {
        const audio = new Audio(url);
        audio.volume = 1.0;
        this.currentAudioElement = audio;
        const done = new Promise<boolean>((resolve) => {
          audio.onended = () => resolve(true);
          audio.onerror = () => resolve(false);
        });
        await audio.play();
        return await done;
      } catch {
        return false;
      }
    };

    // The spoken greeting opens the chat thread too, so the conversation
    // starts in exactly one place.
    const recordGreeting = () =>
      this.appendToChat(
        "aeris",
        "Voice command mode activated. AERIS online and at your service, sir.",
        "voice",
      );

    const greeting = "Voice command mode activated. AERIS online and at your service, sir.";
    const turn = ++this.speechTurn;
    try {
      const audio = await this.kokoro.synthesize(greeting);
      if (turn !== this.speechTurn || store.isMuted) {
        if (store.isMuted) store.setVoiceState("idle");
        return;
      }
      console.info(
        `[AERIS VOICE] provider=kokoro voice=bm_george synthesisMs=${audio.synthesisMs.toFixed(0)}`,
      );
      await this.speechPlayer.enqueueFloat32(audio.samples, audio.sampleRate);
      if (turn === this.speechTurn) {
        store.setVoiceState("idle");
        recordGreeting();
      }
      return;
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      console.error("[AERIS VOICE] George greeting failed; using offline greeting:", error);
    }

    if (await playUrl("/audio/greeting.mp3")) {
      this.currentAudioElement = null;
      recordGreeting();
    } else {
      this.currentAudioElement = null;
      console.warn("Could not play greeting audio.");
    }
    store.setVoiceState("idle");
  }

  private playChime(): void {
    try {
      if (!this.audioContext) return;
      const now = this.audioContext.currentTime;
      const osc = this.audioContext.createOscillator();
      const gain = this.audioContext.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(587.33, now); // D5
      osc.frequency.exponentialRampToValueAtTime(880, now + 0.12); // A5
      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
      osc.connect(gain);
      gain.connect(this.audioContext.destination);
      osc.start(now);
      osc.stop(now + 0.25);
    } catch {
      // Ignore audio chime synthesis errors
    }
  }

  async startRecording(): Promise<void> {
    const store = useVoiceStore.getState();

    // Interrupt any ongoing AERIS speech
    this.interrupt();

    store.setVoiceState("listening");
    store.setTranscript("");

    try {
      if (!this.micStream || !this.micStream.active) {
        this.micStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            sampleRate: 16000,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
      }

      // Web Audio RMS Analyser for real-time waveform reactivity
      const AudioCtx =
        window.AudioContext ||
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (window as any).webkitAudioContext;
      if (!this.audioContext || this.audioContext.state === "closed") {
        this.audioContext = new AudioCtx();
      }
      if (this.audioContext.state === "suspended") {
        await this.audioContext.resume();
      }

      const source = this.audioContext.createMediaStreamSource(this.micStream);
      const analyser = this.audioContext.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      this.analyser = analyser;

      this.startAudioLevelMetering();

      // Reset chunks
      this.pcmChunks = [];
      this.audioChunks = [];

      // 1. Primary: Attach ScriptProcessorNode for pristine 16-bit PCM WAV capture
      try {
        const processor = this.audioContext.createScriptProcessor(4096, 1, 1);
        processor.onaudioprocess = (e) => {
          if (useVoiceStore.getState().voiceState !== "listening") return;
          const channelData = e.inputBuffer.getChannelData(0);
          this.pcmChunks.push(new Float32Array(channelData));
        };
        const silentGain = this.audioContext.createGain();
        silentGain.gain.value = 0;
        source.connect(processor);
        processor.connect(silentGain);
        silentGain.connect(this.audioContext.destination);
        this.processorNode = processor;
        this.silentGainNode = silentGain;
      } catch (procErr) {
        console.warn("ScriptProcessor initialization failed, falling back to MediaRecorder:", procErr);
      }

      // 2. Fallback: Start MediaRecorder without timeslice for complete EBML headers
      const mimeType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : MediaRecorder.isTypeSupported("audio/mp4")
          ? "audio/mp4"
          : "";

      const recorder = mimeType ? new MediaRecorder(this.micStream, { mimeType }) : new MediaRecorder(this.micStream);
      this.mediaRecorder = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      recorder.start();

      // 3. Initiate real-time browser speech recognition in parallel for instant 0ms response
      this.realTimeTranscript = "";
      if (typeof window !== "undefined") {
        const SpeechRec =
          (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        if (SpeechRec) {
          try {
            const recognizer = new SpeechRec();
            recognizer.continuous = true;
            recognizer.interimResults = true;
            recognizer.lang = "en-US";
            recognizer.onresult = (event: any) => {
              let text = "";
              for (let i = 0; i < event.results.length; i++) {
                text += event.results[i][0].transcript;
              }
              if (text.trim()) {
                this.realTimeTranscript = text.trim();
                store.setTranscript(this.realTimeTranscript, false);
              }
            };
            recognizer.onerror = () => {};
            recognizer.start();
            this.speechRecognizer = recognizer;
          } catch (recErr) {
            console.debug("Web Speech API not available:", recErr);
          }
        }
      }
    } catch (err) {
      console.error("Microphone capture failed:", err);
      store.setVoiceState("idle");
      store.setConnectionStatus("error", "Microphone access denied");
      toast.error("Microphone permission required for AERIS voice uplink.");
    }
  }

  private startAudioLevelMetering() {
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
    }

    const dataArray = new Uint8Array(this.analyser ? this.analyser.frequencyBinCount : 0);

    const updateLevel = () => {
      if (this.analyser && useVoiceStore.getState().voiceState === "listening") {
        this.analyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i];
        }
        const average = sum / dataArray.length;
        const normalized = Math.min(1, average / 128);
        useVoiceStore.getState().setAudioLevel(normalized);
        this.animFrameId = requestAnimationFrame(updateLevel);
      } else {
        useVoiceStore.getState().setAudioLevel(0);
      }
    };

    this.animFrameId = requestAnimationFrame(updateLevel);
  }

  async stopRecordingAndProcess(): Promise<void> {
    const store = useVoiceStore.getState();

    // 1. Disconnect PCM ScriptProcessorNode
    if (this.processorNode) {
      try {
        this.processorNode.disconnect();
      } catch {}
      this.processorNode = null;
    }
    if (this.silentGainNode) {
      try {
        this.silentGainNode.disconnect();
      } catch {}
      this.silentGainNode = null;
    }

    // 2. Stop MediaRecorder if running
    let mediaBlob: Blob | null = null;
    if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
      const recPromise = new Promise<Blob>((resolve) => {
        if (!this.mediaRecorder) return resolve(new Blob());
        this.mediaRecorder.onstop = () => {
          const type = this.mediaRecorder?.mimeType?.split(";")[0] || "audio/webm";
          resolve(new Blob(this.audioChunks, { type }));
        };
        try {
          this.mediaRecorder.stop();
        } catch {
          resolve(new Blob());
        }
      });
      mediaBlob = await recPromise;
    }

    // Stop real-time browser speech recognition if active
    if (this.speechRecognizer) {
      try {
        this.speechRecognizer.stop();
      } catch {}
      this.speechRecognizer = null;
    }

    // Fast-path: If real-time Web Speech captured the transcript instantly, dispatch text query directly (0ms latency!)
    if (this.realTimeTranscript.trim().length > 0) {
      const fastTranscript = this.realTimeTranscript.trim();
      this.realTimeTranscript = "";
      console.log(`[AERIS VOICE] Fast-path browser speech transcript (0ms): "${fastTranscript}"`);
      await this.sendTextQuery(fastTranscript);
      return;
    }

    store.setVoiceState("transcribing");

    let audioBlob: Blob | null = null;
    let filename = "speech.wav";
    let mimeType = "audio/wav";

      // 3. Prefer PCM WAV encoding (16kHz mono 16-bit PCM)
      if (this.pcmChunks.length > 0 && this.audioContext) {
        const totalLen = this.pcmChunks.reduce((acc, c) => acc + c.length, 0);
        const merged = new Float32Array(totalLen);
        let offset = 0;
        for (const chunk of this.pcmChunks) {
          merged.set(chunk, offset);
          offset += chunk.length;
        }
        this.pcmChunks = [];

        // Resample to Whisper's native 16kHz
        const resampled = resampleAudio(merged, this.audioContext.sampleRate, 16000);
        audioBlob = encodeWav(resampled, 16000);
        filename = "speech.wav";
        mimeType = "audio/wav";
      } else if (mediaBlob && mediaBlob.size >= 500) {
        audioBlob = mediaBlob;
        const isMp4 = mediaBlob.type.includes("mp4");
        filename = isMp4 ? "speech.mp4" : "speech.webm";
        mimeType = isMp4 ? "audio/mp4" : "audio/webm";
      }

      try {
        if (!audioBlob || audioBlob.size < 500) {
          // Audio was too short or silent
          store.setVoiceState("idle");
          return;
        }

        store.setVoiceState("thinking");

        const audioFile = new File([audioBlob], filename, { type: mimeType });

        const operatorContext = collectOperatorContext();
        console.log("[AERIS VOICE] operator context:", operatorContext);
        const formData = new FormData();
        formData.append("audio", audioFile, filename);
        formData.append("context", JSON.stringify(operatorContext));

        // Attempt to capture a frontend snapshot for the AI Vision model
        try {
          const html2canvas = (await import("html2canvas")).default;
          const canvas = await html2canvas(document.body, { scale: 0.5 });
          const imageBase64 = canvas.toDataURL("image/jpeg", 0.5);
          formData.append("screenshot", imageBase64);
          console.log("[AERIS VOICE] Added frontend snapshot to payload");
        } catch (screenshotErr) {
          console.warn("[AERIS VOICE] Failed to capture snapshot:", screenshotErr);
        }

        const response = await fetch("/api/voice/process", {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          const errJson = await response.json().catch(() => ({}));
          throw new Error(errJson.error || `Server responded with status ${response.status}`);
        }

        const data: ProcessVoiceResponse = await response.json();
        await this.handleProcessResponse(data, "voice");
    } catch (err: unknown) {
      console.error("AERIS request failed:", err);
      const message = err instanceof Error ? err.message : "AERIS uplink failure";
      toast.error(message);
      store.setVoiceState("idle");
    }
  }

  async sendTextQuery(query: string): Promise<void> {
    const store = useVoiceStore.getState();
    const trimmed = query.trim();
    if (!trimmed) return;

    this.interrupt();
    store.setTranscript(trimmed, true);
    store.setVoiceState("thinking");

    try {
      const context = collectOperatorContext();
      console.log("[AERIS VOICE] operator context:", context);
      const response = await fetch("/api/voice/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed, context }),
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.error || `Server responded with status ${response.status}`);
      }

      const data: ProcessVoiceResponse = await response.json();
      await this.handleProcessResponse(data, "text");
    } catch (err: unknown) {
      console.error("AERIS text query failed:", err);
      const message = err instanceof Error ? err.message : "AERIS query failure";
      toast.error(message);
      store.setVoiceState("idle");
    }
  }

  private async handleProcessResponse(data: ProcessVoiceResponse, origin: TurnOrigin): Promise<void> {
    const store = useVoiceStore.getState();

    // The whole exchange belongs to chat: operator line, then AERIS line.
    // Spoken turns additionally play the reply as audio; nothing renders
    // as a popover or toast on the canvas.
    if (data.transcript) {
      this.appendToChat("operator", data.transcript, origin);
    }
    if (data.reply) {
      this.appendToChat("aeris", data.reply, origin);
    }

    // Execute UI commands returned by AERIS through the command bus, and
    // report each outcome. A dispatch never throws — failures arrive as data
    // (not-found / invalid-params / disabled / failed) and must be surfaced,
    // otherwise the agent appears to ignore explicit orders.
    console.log(
      `[AERIS VOICE] frontend received ${data.actions?.length ?? 0} action(s) for transcript "${data.transcript ?? ""}"`,
      data.actions,
    );
    if (!data.actions || data.actions.length === 0) {
      console.log("[AERIS VOICE] brain ordered no UI actions — reply was words only.");
    }
    if (data.actions && data.actions.length > 0) {
      const actionSummaries: string[] = [];
      for (const action of data.actions) {
        console.log(`[AERIS VOICE] dispatching: ${action.commandId}`, action.params);
        const result = await dispatchUiCommandEvent({
          commandId: action.commandId,
          params: action.params,
          reason: `AERIS: ${action.description}`,
        });
        console.log(`[AERIS VOICE] dispatch outcome: ${action.commandId} -> ${result.status}`);
        if (result.status === "completed") {
          actionSummaries.push(action.description);
        } else {
          const detail =
            result.status === "invalid-params"
              ? `rejected params (${result.message})`
              : result.status === "not-found"
                ? "not available on this screen"
                : result.status === "disabled"
                  ? "currently disabled"
                  : "execution failed";
          actionSummaries.push(`${action.description} — could not run (${detail})`);
          console.warn(`[voice] command ${action.commandId} ${result.status}:`, result);
        }
      }
      store.setActiveActionSummary(actionSummaries.join(" • "));
    }

    // Synthesize locally after text/actions are already visible and applied.
    if (data.reply && !store.isMuted) {
      const turn = ++this.speechTurn;
      store.setVoiceState("speaking");
      try {
        const playbackStartedAt = performance.now();
        const audio = await this.kokoro.synthesize(data.reply);
        if (turn !== this.speechTurn || store.isMuted) {
          if (store.isMuted) store.setVoiceState("idle");
          return;
        }
        console.info(
          `[AERIS VOICE] provider=kokoro voice=bm_george synthesisMs=${audio.synthesisMs.toFixed(0)} playbackScheduleMs=${(performance.now() - playbackStartedAt).toFixed(0)}`,
        );
        await this.speechPlayer.enqueueFloat32(audio.samples, audio.sampleRate);
        if (turn === this.speechTurn) store.setVoiceState("idle");
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        console.error("[AERIS VOICE] Local George synthesis failed:", error);
        // Cloud audio is an explicit emergency fallback while the route still
        // supplies it. Task 4 removes it from the normal response path.
        if (data.audioBase64) {
          try {
            const fallback = new Audio(data.audioBase64);
            this.currentAudioElement = fallback;
            fallback.onended = () => {
              this.currentAudioElement = null;
              store.setVoiceState("idle");
            };
            await fallback.play();
            return;
          } catch (fallbackError: unknown) {
            console.error("[AERIS VOICE] Emergency cloud audio failed:", fallbackError);
          }
        }
        if (turn === this.speechTurn) store.setVoiceState("idle");
      }
    } else {
      store.setVoiceState("idle");
    }
  }

  interrupt(): void {
    this.speechTurn += 1;
    this.kokoro.cancel();
    this.speechPlayer.abort();
    if (this.currentAudioElement) {
      this.currentAudioElement.pause();
      this.currentAudioElement = null;
    }
    if (this.processorNode) {
      try {
        this.processorNode.disconnect();
      } catch {}
      this.processorNode = null;
    }
    if (this.silentGainNode) {
      try {
        this.silentGainNode.disconnect();
      } catch {}
      this.silentGainNode = null;
    }
    if (this.mediaRecorder && this.mediaRecorder.state === "recording") {
      try {
        this.mediaRecorder.stop();
      } catch {}
    }
    if (this.speechRecognizer) {
      try {
        this.speechRecognizer.stop();
      } catch {}
      this.speechRecognizer = null;
    }
    this.realTimeTranscript = "";
    this.pcmChunks = [];
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
      } catch {}
    }
    useVoiceStore.getState().setAudioLevel(0);
    useVoiceStore.getState().setVoiceState("idle");
  }

  toggleMute(): void {
    const store = useVoiceStore.getState();
    const next = !store.isMuted;
    store.setIsMuted(next);
    if (next) {
      this.kokoro.cancel();
      this.speechPlayer.abort();
      if (this.currentAudioElement) this.currentAudioElement.pause();
      store.setVoiceState("idle");
    }
    toast.info(next ? "AERIS voice narration muted" : "AERIS voice narration unmuted");
  }

  disconnect(): void {
    this.interrupt();
    if (this.micStream) {
      this.micStream.getTracks().forEach((track) => track.stop());
      this.micStream = null;
    }
    if (this.audioContext && this.audioContext.state !== "closed") {
      void this.audioContext.close();
      this.audioContext = null;
    }
    useVoiceStore.getState().setConnectionStatus("disconnected");
    useVoiceStore.getState().setVoiceState("idle");
    toast.info("Voice uplink disconnected");
  }
}

const aerisManager = new AerisSessionManager();

export function useVoiceSession() {
  const connectionStatus = useVoiceStore((state) => state.connectionStatus);
  const voiceState = useVoiceStore((state) => state.voiceState);
  const transcript = useVoiceStore((state) => state.transcript);
  const lastAerisReply = useVoiceStore((state) => state.lastAerisReply);
  const activeActionSummary = useVoiceStore((state) => state.activeActionSummary);
  const isFinalTranscript = useVoiceStore((state) => state.isFinalTranscript);
  const audioLevel = useVoiceStore((state) => state.audioLevel);
  const isMuted = useVoiceStore((state) => state.isMuted);

  useEffect(() => {
    aerisManager.bindGlobalListeners();
  }, []);

  const connect = useCallback(() => aerisManager.connect(), []);
  const disconnect = useCallback(() => aerisManager.disconnect(), []);
  const startTurn = useCallback(() => aerisManager.startRecording(), []);
  const endTurn = useCallback(() => aerisManager.stopRecordingAndProcess(), []);
  const sendTextQuery = useCallback((text: string) => aerisManager.sendTextQuery(text), []);
  const interrupt = useCallback(() => aerisManager.interrupt(), []);
  const toggleMute = useCallback(() => aerisManager.toggleMute(), []);

  return {
    connectionStatus,
    voiceState,
    transcript,
    lastAerisReply,
    activeActionSummary,
    isFinalTranscript,
    audioLevel,
    isMuted,
    connect,
    disconnect,
    startTurn,
    endTurn,
    sendTextQuery,
    interrupt,
    toggleMute,
  };
}

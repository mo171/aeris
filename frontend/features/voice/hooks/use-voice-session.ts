// features/voice/hooks/use-voice-session.ts — bidirectional WebSocket voice session management.
//
// what  : Connects browser to /api/v1/voice/ws, streams 16 kHz Int16 PCM mic audio via AudioWorklet,
//         schedules 24 kHz Kokoro playback, handles push-to-talk (Ctrl+P), and bridges ui-command events.
// where : Invoked by InvestigationScreen, VoiceActivationButton, and VoiceControlBar.
// how   : Manages a persistent voice session handle with low-latency Web Audio capture and Kokoro playback.
//         Incoming UI commands route directly to the command bus via dispatchUiCommandEvent.

"use client";

import { useCallback, useEffect } from "react";
import { toast } from "sonner";

import { SpeechStreamPlayer } from "@/lib/audio/speech-stream-player";
import { env } from "@/lib/env";
import { dispatchUiCommandEvent } from "@/lib/streaming/ui-command-bridge";
import { useVoiceStore, type VoiceState } from "../store/voice-store";

function getVoiceWsUrl(): string {
  const apiUrl = env.NEXT_PUBLIC_API_URL;
  const wsProtocol = apiUrl.startsWith("https") ? "wss:" : "ws:";
  const host = apiUrl.replace(/^https?:\/\//, "");
  return `${wsProtocol}//${host}/api/v1/voice/ws`;
}

class VoiceSessionManager {
  private ws: WebSocket | null = null;
  private player: SpeechStreamPlayer | null = null;
  private micStream: MediaStream | null = null;
  private micContext: AudioContext | null = null;
  private captureNode: AudioWorkletNode | null = null;
  private isPttActive: boolean = false;
  private isListenersBound: boolean = false;

  getPlayer(): SpeechStreamPlayer {
    if (!this.player) {
      this.player = new SpeechStreamPlayer();
    }
    return this.player;
  }

  bindGlobalListeners() {
    if (this.isListenersBound || typeof window === "undefined") return;
    this.isListenersBound = true;

    window.addEventListener("keydown", this.handleKeyDown);
    window.addEventListener("keyup", this.handleKeyUp);
  }

  private handleKeyDown = (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && (e.key === "p" || e.key === "P")) {
      e.preventDefault();
      const status = useVoiceStore.getState().connectionStatus;
      if (!this.isPttActive && status === "connected") {
        this.isPttActive = true;
        this.startTurn();
      }
    }
  };

  private handleKeyUp = (e: KeyboardEvent) => {
    if (e.key === "p" || e.key === "P") {
      if (this.isPttActive) {
        this.isPttActive = false;
        this.endTurn();
      }
    }
  };

  async connect(): Promise<void> {
    const store = useVoiceStore.getState();
    if (store.connectionStatus === "connecting" || store.connectionStatus === "connected") {
      return;
    }

    store.setConnectionStatus("connecting");

    try {
      this.bindGlobalListeners();
      const player = this.getPlayer();
      await player.resume();
      player.playChime();

      // Request low-latency mono mic audio
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      this.micStream = mediaStream;

      const AudioCtx =
        window.AudioContext ||
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (window as any).webkitAudioContext;
      const micContext = new AudioCtx({ sampleRate: 16000 });
      this.micContext = micContext;

      await micContext.audioWorklet.addModule("/audio-processors/pcm-capture-processor.js");

      const sourceNode = micContext.createMediaStreamSource(mediaStream);
      const captureNode = new AudioWorkletNode(micContext, "pcm-capture-processor");
      this.captureNode = captureNode;

      captureNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        const pcmBuffer = event.data;
        if (!pcmBuffer || pcmBuffer.byteLength === 0) return;

        // Compute RMS level for visualizer
        const int16 = new Int16Array(pcmBuffer);
        let sum = 0;
        for (let i = 0; i < int16.length; i++) {
          const s = int16[i] / 32768;
          sum += s * s;
        }
        const rms = Math.sqrt(sum / int16.length);
        useVoiceStore.getState().setAudioLevel(Math.min(1, rms * 4));

        const currentState = useVoiceStore.getState().voiceState;
        if (currentState === "listening" && this.ws?.readyState === WebSocket.OPEN) {
          this.ws.send(pcmBuffer);
        }
      };

      sourceNode.connect(captureNode);
      const muteGain = micContext.createGain();
      muteGain.gain.value = 0;
      captureNode.connect(muteGain);
      muteGain.connect(micContext.destination);

      // Open WebSocket
      const wsUrl = getVoiceWsUrl();
      const ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer";
      this.ws = ws;

      ws.onopen = () => {
        useVoiceStore.getState().setConnectionStatus("connected");
        useVoiceStore.getState().setVoiceState("idle");
        toast.success("AERIS Voice Uplink active");
      };

      ws.onmessage = (event: MessageEvent) => {
        if (event.data instanceof ArrayBuffer) {
          // Inbound binary PCM16 24 kHz speech chunk from Kokoro
          this.player?.enqueueChunk(event.data);
          if (useVoiceStore.getState().voiceState !== "speaking") {
            useVoiceStore.getState().setVoiceState("speaking");
          }
          return;
        }

        if (typeof event.data === "string") {
          try {
            const data = JSON.parse(event.data);
            switch (data.type) {
              case "session_state":
                if (data.state) {
                  const stateMap: Record<string, VoiceState> = {
                    idle: "idle",
                    capturing: "listening",
                    transcribing: "transcribing",
                    running: "thinking",
                    "pending-approval": "thinking",
                    standby: "standby",
                    failed: "idle",
                    closed: "idle",
                  };
                  const mappedState = stateMap[data.state] ?? (data.state as VoiceState);
                  useVoiceStore.getState().setVoiceState(mappedState);
                }
                break;
              case "transcript":
                if (data.text !== undefined) {
                  useVoiceStore.getState().setTranscript(data.text, Boolean(data.isFinal));
                }
                break;
              case "speech": {
                const utteranceId = data.utteranceId || data.utterance_id;
                if (utteranceId) {
                  useVoiceStore.getState().setActiveUtteranceId(utteranceId);
                }
                if (data.text) {
                  useVoiceStore.getState().setTranscript(data.text, true);
                }
                break;
              }
              case "ui-command":
                void dispatchUiCommandEvent({
                  commandId: data.commandId || data.payload?.commandId,
                  params: data.params || data.payload?.params || {},
                  reason: data.reason || data.payload?.reason || "Voice commanded",
                });
                break;
              case "run-complete":
                useVoiceStore.getState().setVoiceState("idle");
                break;
              case "run-error":
                toast.error(`Voice execution error: ${data.error || "Unknown error"}`);
                useVoiceStore.getState().setVoiceState("idle");
                break;
              default:
                break;
            }
          } catch {
            // Ignore non-JSON frames
          }
        }
      };

      ws.onerror = () => {
        useVoiceStore.getState().setConnectionStatus("error", "Voice uplink connection error");
        toast.error("AERIS Voice uplink connection failed");
      };

      ws.onclose = () => {
        useVoiceStore.getState().setConnectionStatus("disconnected");
        useVoiceStore.getState().setVoiceState("idle");
      };
    } catch (error) {
      console.error("Failed to establish voice session:", error);
      this.disconnect();
      useVoiceStore.getState().setConnectionStatus("error", "Microphone access denied or audio error");
      toast.error("Microphone access denied. Please allow microphone access to use AERIS voice.");
    }
  }

  disconnect(): void {
    if (this.captureNode) {
      this.captureNode.disconnect();
      this.captureNode = null;
    }
    if (this.micStream) {
      this.micStream.getTracks().forEach((track) => track.stop());
      this.micStream = null;
    }
    if (this.micContext && this.micContext.state !== "closed") {
      void this.micContext.close();
      this.micContext = null;
    }

    this.player?.abort();

    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.onmessage = null;
      this.ws.close();
      this.ws = null;
    }

    useVoiceStore.getState().reset();
  }

  startTurn(): void {
    this.player?.abort();
    useVoiceStore.getState().setVoiceState("listening");
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "start_turn" }));
    }
  }

  endTurn(): void {
    useVoiceStore.getState().setVoiceState("thinking");
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "end_turn" }));
    }
  }

  interrupt(): void {
    this.player?.abort();
    useVoiceStore.getState().setVoiceState("idle");
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "interrupt" }));
    }
  }

  toggleStandby(): void {
    const currentState = useVoiceStore.getState().voiceState;
    if (currentState === "standby") {
      useVoiceStore.getState().setVoiceState("idle");
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "resume" }));
      }
    } else {
      this.player?.abort();
      useVoiceStore.getState().setVoiceState("standby");
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "standby" }));
      }
    }
  }

  approvePlan(stepIds?: string[]): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(
        JSON.stringify({
          type: "approve_plan",
          approvedStepIds: stepIds ?? [],
        }),
      );
    }
  }

  abandon(): void {
    this.player?.abort();
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "abandon" }));
    }
  }
}

const voiceManager = new VoiceSessionManager();

export function useVoiceSession() {
  const connectionStatus = useVoiceStore((state) => state.connectionStatus);
  const voiceState = useVoiceStore((state) => state.voiceState);
  const transcript = useVoiceStore((state) => state.transcript);
  const isFinalTranscript = useVoiceStore((state) => state.isFinalTranscript);
  const audioLevel = useVoiceStore((state) => state.audioLevel);

  useEffect(() => {
    voiceManager.bindGlobalListeners();
  }, []);

  const connect = useCallback(() => voiceManager.connect(), []);
  const disconnect = useCallback(() => voiceManager.disconnect(), []);
  const startTurn = useCallback(() => voiceManager.startTurn(), []);
  const endTurn = useCallback(() => voiceManager.endTurn(), []);
  const interrupt = useCallback(() => voiceManager.interrupt(), []);
  const toggleStandby = useCallback(() => voiceManager.toggleStandby(), []);
  const approvePlan = useCallback((stepIds?: string[]) => voiceManager.approvePlan(stepIds), []);
  const abandon = useCallback(() => voiceManager.abandon(), []);

  return {
    connectionStatus,
    voiceState,
    transcript,
    isFinalTranscript,
    audioLevel,
    connect,
    disconnect,
    startTurn,
    endTurn,
    interrupt,
    toggleStandby,
    approvePlan,
    abandon,
  };
}

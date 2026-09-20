// features/voice/store/voice-store.ts — reactive client-side state for the AERIS voice interface.
//
// what  : Tracks WebSocket connection status, current voice conversation turn state,
//         active utterance id, real-time speech-to-text transcripts, and live audio levels.
// where : Shared between useVoiceSession hook, VoiceActivationButton, and VoiceControlBar.
// how   : Built with Zustand for reactive updates across the canvas and top navigation.
//         Transient audio levels and live interim transcripts are updated without triggering
//         heavy global re-renders.

import { create } from "zustand";

export type ConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

export type VoiceState =
  | "idle"
  | "listening"
  | "transcribing"
  | "thinking"
  | "speaking"
  | "standby";

export interface VoiceStoreState {
  connectionStatus: ConnectionStatus;
  voiceState: VoiceState;
  activeUtteranceId: string | null;
  transcript: string;
  isFinalTranscript: boolean;
  lastAerisReply: string;
  activeActionSummary: string | null;
  audioLevel: number;
  errorMessage: string | null;
  isMuted: boolean;

  // Actions
  setConnectionStatus: (status: ConnectionStatus, errorMessage?: string | null) => void;
  setVoiceState: (state: VoiceState) => void;
  setActiveUtteranceId: (id: string | null) => void;
  setTranscript: (transcript: string, isFinal?: boolean) => void;
  setLastAerisReply: (reply: string) => void;
  setActiveActionSummary: (summary: string | null) => void;
  setAudioLevel: (level: number) => void;
  setIsMuted: (isMuted: boolean) => void;
  reset: () => void;
}

const initialState = {
  connectionStatus: "disconnected" as ConnectionStatus, // Usually off by default; user clicks VOICE UPLINK to enable
  voiceState: "idle" as VoiceState,
  activeUtteranceId: null,
  transcript: "",
  isFinalTranscript: false,
  lastAerisReply: "",
  activeActionSummary: null,
  audioLevel: 0,
  errorMessage: null,
  isMuted: false,
};

export const useVoiceStore = create<VoiceStoreState>((set) => ({
  ...initialState,

  setConnectionStatus: (status, errorMessage = null) =>
    set({ connectionStatus: status, errorMessage: errorMessage ?? null }),

  setVoiceState: (voiceState) =>
    set((state) => {
      // If entering listening state, clear transient transcript
      if (voiceState === "listening" && state.voiceState !== "listening") {
        return { voiceState, transcript: "", isFinalTranscript: false };
      }
      return { voiceState };
    }),

  setActiveUtteranceId: (activeUtteranceId) => set({ activeUtteranceId }),

  setTranscript: (transcript, isFinal = false) =>
    set({ transcript, isFinalTranscript: isFinal }),

  setLastAerisReply: (lastAerisReply) => set({ lastAerisReply }),

  setActiveActionSummary: (activeActionSummary) => set({ activeActionSummary }),

  setAudioLevel: (audioLevel) => set({ audioLevel }),

  setIsMuted: (isMuted) => set({ isMuted }),

  reset: () => set(initialState),
}));

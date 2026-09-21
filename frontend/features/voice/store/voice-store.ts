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

/**
 * One turn of voice conversation, kept as chat data — never as a floating
 * popover. Rendered by the surface chat UIs (ChatTab, assistant transcript
 * fallback) so the whole exchange lives in exactly one thread.
 */
export interface VoiceChatMessage {
  id: string;
  role: "operator" | "aeris";
  text: string;
  createdAt: string;
  origin: "voice" | "text";
}

/** The thread never grows without bound: a voice log is a session record, not storage. */
const MAX_VOICE_MESSAGES = 100;

export interface VoiceStoreState {
  connectionStatus: ConnectionStatus;
  voiceState: VoiceState;
  activeUtteranceId: string | null;
  transcript: string;
  isFinalTranscript: boolean;
  lastAerisReply: string;
  activeActionSummary: string | null;
  messages: VoiceChatMessage[];
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
  appendVoiceMessage: (role: VoiceChatMessage["role"], text: string, origin: VoiceChatMessage["origin"]) => void;
  clearVoiceMessages: () => void;
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
  messages: [] as VoiceChatMessage[],
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

  appendVoiceMessage: (role, text, origin) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id: `vmsg_${Date.now().toString(36)}_${state.messages.length}`,
          role,
          text,
          createdAt: new Date().toISOString(),
          origin,
        },
      ].slice(-MAX_VOICE_MESSAGES),
    })),

  clearVoiceMessages: () => set({ messages: [] }),

  setAudioLevel: (audioLevel) => set({ audioLevel }),

  setIsMuted: (isMuted) => set({ isMuted }),

  reset: () => set(initialState),
}));

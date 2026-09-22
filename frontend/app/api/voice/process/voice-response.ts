export interface LocalVoiceAction {
  commandId: string;
  params: Record<string, unknown>;
  description: string;
}

interface LocalVoiceResponseInput {
  transcript: string;
  reply: string;
  actions: LocalVoiceAction[];
}

export function createLocalVoiceResponse({
  transcript,
  reply,
  actions,
}: LocalVoiceResponseInput) {
  return {
    success: true as const,
    transcript,
    reply,
    actions,
    audioBase64: null,
    speechProvider: "kokoro-local" as const,
  };
}


// features/missionCommand/types/assistant.types.ts — assistant transcript and stream types.
//
// what  : TypeScript types for messages, execution-trace steps, suggestions and stream events.
// where : Imported by assistant.service.ts, use-assistant-session.ts and the whole assistant panel.
// how   : See imagery.types.ts. AssistantStreamEvent is a discriminated union on `type`, so consumers get
//         exhaustiveness checking when they switch over it — adding a new event type surfaces every
//         handler that needs updating at compile time.

import type { z } from "zod";

import type {
  assistantAskRequestSchema,
  assistantMessageSchema,
  assistantMessageStatusSchema,
  assistantRoleSchema,
  assistantStreamEventSchema,
  assistantSuggestionSchema,
  executionStepStateSchema,
  executionTraceStepSchema,
} from "../schemas/assistant.schema";

export type AssistantRole = z.infer<typeof assistantRoleSchema>;
export type AssistantMessageStatus = z.infer<typeof assistantMessageStatusSchema>;
export type AssistantMessage = z.infer<typeof assistantMessageSchema>;
export type ExecutionStepState = z.infer<typeof executionStepStateSchema>;
export type ExecutionTraceStep = z.infer<typeof executionTraceStepSchema>;
export type AssistantSuggestion = z.infer<typeof assistantSuggestionSchema>;
export type AssistantStreamEvent = z.infer<typeof assistantStreamEventSchema>;
export type AssistantAskRequest = z.infer<typeof assistantAskRequestSchema>;

/**
 * The imperative surface the assistant panel publishes so the command bus — and later the agent and voice
 * layers — can drive the conversation without owning it. Mirrors GlobeViewerHandle: the panel keeps its
 * own state, and everything outside reaches it through these four verbs.
 */
export interface AssistantPanelControls {
  ask: (prompt: string) => void;
  stop: () => void;
  clear: () => void;
  focusComposer: () => void;
}

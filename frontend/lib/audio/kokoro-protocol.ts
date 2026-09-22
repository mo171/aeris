export type KokoroLifecycleState = "idle" | "loading" | "ready" | "synthesizing" | "error";

export type KokoroWorkerRequest =
  | { type: "prepare" }
  | { type: "synthesize"; requestId: number; text: string }
  | { type: "cancel"; requestId: number };

export type KokoroWorkerResponse =
  | { type: "state"; state: KokoroLifecycleState }
  | { type: "prepared"; preparationMs: number }
  | {
      type: "audio";
      requestId: number;
      samples: Float32Array;
      sampleRate: number;
      synthesisMs: number;
    }
  | { type: "error"; requestId?: number; message: string };


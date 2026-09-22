/// <reference lib="webworker" />

import type { KokoroTTS } from "kokoro-js";

import {
  KOKORO_DTYPE,
  KOKORO_MODEL_ID,
  KOKORO_SAMPLE_RATE,
  KOKORO_SPEED,
  KOKORO_VOICE,
} from "./kokoro-config";
import type { KokoroWorkerRequest, KokoroWorkerResponse } from "./kokoro-protocol";

const scope = self as DedicatedWorkerGlobalScope;
let modelPromise: Promise<KokoroTTS> | null = null;
let synthesisQueue = Promise.resolve();
const cancelledRequests = new Set<number>();

function send(message: KokoroWorkerResponse, transfer: Transferable[] = []): void {
  scope.postMessage(message, transfer);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown Kokoro worker error";
}

async function prepareModel(): Promise<KokoroTTS> {
  if (modelPromise) return modelPromise;

  send({ type: "state", state: "loading" });
  const startedAt = performance.now();
  modelPromise = import("kokoro-js")
    .then(({ KokoroTTS }) =>
      KokoroTTS.from_pretrained(KOKORO_MODEL_ID, {
        dtype: KOKORO_DTYPE,
      }),
    )
    .then((model) => {
      send({ type: "prepared", preparationMs: performance.now() - startedAt });
      return model;
    })
    .catch((error: unknown) => {
      modelPromise = null;
      send({ type: "error", message: errorMessage(error) });
      throw error;
    });

  return modelPromise;
}

async function synthesize(requestId: number, text: string): Promise<void> {
  try {
    const model = await prepareModel();
    if (cancelledRequests.delete(requestId)) return;

    send({ type: "state", state: "synthesizing" });
    const startedAt = performance.now();
    const audio = await model.generate(text, {
      voice: KOKORO_VOICE,
      speed: KOKORO_SPEED,
    });
    if (cancelledRequests.delete(requestId)) return;

    const sampleRate = audio.sampling_rate;
    if (sampleRate !== KOKORO_SAMPLE_RATE) {
      throw new Error(`Expected ${KOKORO_SAMPLE_RATE} Hz audio, received ${sampleRate} Hz.`);
    }
    const samples = new Float32Array(audio.audio);
    send(
      {
        type: "audio",
        requestId,
        samples,
        sampleRate,
        synthesisMs: performance.now() - startedAt,
      },
      [samples.buffer],
    );
  } catch (error: unknown) {
    send({ type: "error", requestId, message: errorMessage(error) });
  }
}

scope.addEventListener("message", (event: MessageEvent<KokoroWorkerRequest>) => {
  const message = event.data;
  if (message.type === "prepare") {
    void prepareModel();
    return;
  }
  if (message.type === "cancel") {
    cancelledRequests.add(message.requestId);
    return;
  }

  synthesisQueue = synthesisQueue
    .then(() => synthesize(message.requestId, message.text))
    .catch((error: unknown) => {
      send({ type: "error", requestId: message.requestId, message: errorMessage(error) });
    });
});

export {};

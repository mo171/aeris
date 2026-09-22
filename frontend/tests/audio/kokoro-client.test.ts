import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  KOKORO_DTYPE,
  KOKORO_MODEL_ID,
  KOKORO_SAMPLE_RATE,
  KOKORO_VOICE,
} from "../../lib/audio/kokoro-config";
import { KokoroSpeechClient, type WorkerLike } from "../../lib/audio/kokoro-client";
import type { KokoroWorkerRequest, KokoroWorkerResponse } from "../../lib/audio/kokoro-protocol";

class FakeWorker implements WorkerLike {
  readonly postMessage = vi.fn<(message: KokoroWorkerRequest, transfer?: Transferable[]) => void>();
  readonly terminate = vi.fn();
  private listener: ((event: MessageEvent<KokoroWorkerResponse>) => void) | null = null;

  addEventListener(
    _type: "message",
    listener: (event: MessageEvent<KokoroWorkerResponse>) => void,
  ): void {
    this.listener = listener;
  }

  removeEventListener(
    _type: "message",
    listener: (event: MessageEvent<KokoroWorkerResponse>) => void,
  ): void {
    if (this.listener === listener) this.listener = null;
  }

  emit(data: KokoroWorkerResponse): void {
    this.listener?.({ data } as MessageEvent<KokoroWorkerResponse>);
  }
}

describe("Kokoro configuration", () => {
  it("locks V-1 synthesis to the q8 British male George voice", () => {
    expect(KOKORO_MODEL_ID).toBe("onnx-community/Kokoro-82M-v1.0-ONNX");
    expect(KOKORO_DTYPE).toBe("q8");
    expect(KOKORO_VOICE).toBe("bm_george");
    expect(KOKORO_SAMPLE_RATE).toBe(24_000);
  });
});

describe("KokoroSpeechClient", () => {
  let worker: FakeWorker;
  let client: KokoroSpeechClient;

  beforeEach(() => {
    worker = new FakeWorker();
    client = new KokoroSpeechClient(() => worker);
  });

  it("deduplicates concurrent prepare calls and resolves when the worker is ready", async () => {
    const first = client.prepare();
    const second = client.prepare();

    expect(first).toBe(second);
    expect(worker.postMessage).toHaveBeenCalledOnce();
    expect(worker.postMessage).toHaveBeenCalledWith({ type: "prepare" });

    worker.emit({ type: "prepared", preparationMs: 42 });
    await expect(first).resolves.toBeUndefined();
    expect(client.getState()).toBe("ready");
  });

  it("returns transferred George audio for the matching synthesis request", async () => {
    const prepared = client.prepare();
    worker.emit({ type: "prepared", preparationMs: 10 });
    await prepared;

    const pending = client.synthesize("Ready, sir.");
    await Promise.resolve();
    const request = worker.postMessage.mock.calls.at(-1)?.[0];
    expect(request).toMatchObject({ type: "synthesize", text: "Ready, sir." });
    if (!request || request.type !== "synthesize") throw new Error("missing synthesis request");

    const samples = new Float32Array([0, 0.25, -0.25]);
    worker.emit({
      type: "audio",
      requestId: request.requestId,
      samples,
      sampleRate: 24_000,
      synthesisMs: 18,
    });

    await expect(pending).resolves.toEqual({ samples, sampleRate: 24_000, synthesisMs: 18 });
  });

  it("rejects worker errors with the provider reason", async () => {
    const pending = client.prepare();
    worker.emit({ type: "error", message: "model download failed" });
    await expect(pending).rejects.toThrow("model download failed");
    expect(client.getState()).toBe("error");
  });

  it("ignores audio from a cancelled request", async () => {
    const prepared = client.prepare();
    worker.emit({ type: "prepared", preparationMs: 10 });
    await prepared;

    const pending = client.synthesize("First reply");
    await Promise.resolve();
    const request = worker.postMessage.mock.calls.at(-1)?.[0];
    if (!request || request.type !== "synthesize") throw new Error("missing synthesis request");

    client.cancel();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(worker.postMessage).toHaveBeenCalledWith({
      type: "cancel",
      requestId: request.requestId,
    });

    worker.emit({
      type: "audio",
      requestId: request.requestId,
      samples: new Float32Array([1]),
      sampleRate: 24_000,
      synthesisMs: 1,
    });
    expect(client.getState()).toBe("ready");
  });

  it("terminates the worker and rejects pending work on dispose", async () => {
    const pending = client.prepare();
    client.dispose();

    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(worker.terminate).toHaveBeenCalledOnce();
    expect(client.getState()).toBe("idle");
  });
});

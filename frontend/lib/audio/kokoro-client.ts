import type {
  KokoroLifecycleState,
  KokoroWorkerRequest,
  KokoroWorkerResponse,
} from "./kokoro-protocol";

export interface WorkerLike {
  postMessage(message: KokoroWorkerRequest, transfer?: Transferable[]): void;
  addEventListener(
    type: "message",
    listener: (event: MessageEvent<KokoroWorkerResponse>) => void,
  ): void;
  removeEventListener(
    type: "message",
    listener: (event: MessageEvent<KokoroWorkerResponse>) => void,
  ): void;
  terminate(): void;
}

export interface KokoroAudio {
  samples: Float32Array;
  sampleRate: number;
  synthesisMs: number;
}

type PendingAudio = {
  resolve: (audio: KokoroAudio) => void;
  reject: (error: Error) => void;
};

function abortError(message: string): DOMException {
  return new DOMException(message, "AbortError");
}

export class KokoroSpeechClient {
  private worker: WorkerLike | null = null;
  private state: KokoroLifecycleState = "idle";
  private preparationPromise: Promise<void> | null = null;
  private resolvePreparation: (() => void) | null = null;
  private rejectPreparation: ((error: Error) => void) | null = null;
  private pending = new Map<number, PendingAudio>();
  private nextRequestId = 1;
  private activeRequestId: number | null = null;

  constructor(
    private readonly workerFactory: () => WorkerLike = () =>
      new Worker(new URL("./kokoro.worker.ts", import.meta.url), {
        type: "module",
        name: "aeris-kokoro-george",
      }),
  ) {}

  getState(): KokoroLifecycleState {
    return this.state;
  }

  prepare(): Promise<void> {
    if (this.state === "ready") return Promise.resolve();
    if (this.preparationPromise) return this.preparationPromise;

    this.state = "loading";
    this.ensureWorker();
    this.preparationPromise = new Promise<void>((resolve, reject) => {
      this.resolvePreparation = resolve;
      this.rejectPreparation = reject;
    });
    this.worker?.postMessage({ type: "prepare" });
    return this.preparationPromise;
  }

  async synthesize(text: string): Promise<KokoroAudio> {
    const cleanText = text.trim();
    if (!cleanText) throw new Error("Kokoro cannot synthesize empty text.");

    await this.prepare();
    this.cancel();

    const requestId = this.nextRequestId++;
    this.activeRequestId = requestId;
    this.state = "synthesizing";

    const result = new Promise<KokoroAudio>((resolve, reject) => {
      this.pending.set(requestId, { resolve, reject });
    });
    this.worker?.postMessage({ type: "synthesize", requestId, text: cleanText });
    return result;
  }

  cancel(): void {
    if (this.activeRequestId === null) return;

    const requestId = this.activeRequestId;
    this.activeRequestId = null;
    this.worker?.postMessage({ type: "cancel", requestId });
    const pending = this.pending.get(requestId);
    if (pending) {
      pending.reject(abortError("Kokoro synthesis was interrupted."));
      this.pending.delete(requestId);
    }
    if (this.state !== "error") this.state = "ready";
  }

  dispose(): void {
    const error = abortError("Kokoro client was disposed.");
    this.rejectPreparation?.(error);
    this.resetPreparation();
    for (const { reject } of this.pending.values()) reject(error);
    this.pending.clear();
    this.activeRequestId = null;

    if (this.worker) {
      this.worker.removeEventListener("message", this.handleMessage);
      this.worker.terminate();
      this.worker = null;
    }
    this.state = "idle";
  }

  private ensureWorker(): void {
    if (this.worker) return;
    this.worker = this.workerFactory();
    this.worker.addEventListener("message", this.handleMessage);
  }

  private readonly handleMessage = (event: MessageEvent<KokoroWorkerResponse>): void => {
    const message = event.data;
    if (message.type === "state") {
      this.state = message.state;
      return;
    }
    if (message.type === "prepared") {
      this.state = "ready";
      console.info(
        `[AERIS VOICE] provider=kokoro voice=bm_george prepareMs=${message.preparationMs.toFixed(0)}`,
      );
      this.resolvePreparation?.();
      this.resetPreparation();
      return;
    }
    if (message.type === "audio") {
      const pending = this.pending.get(message.requestId);
      if (!pending) return;
      this.pending.delete(message.requestId);
      if (this.activeRequestId === message.requestId) this.activeRequestId = null;
      this.state = "ready";
      pending.resolve({
        samples: message.samples,
        sampleRate: message.sampleRate,
        synthesisMs: message.synthesisMs,
      });
      return;
    }

    const error = new Error(`Kokoro TTS failed: ${message.message}`);
    this.state = "error";
    if (message.requestId !== undefined) {
      this.pending.get(message.requestId)?.reject(error);
      this.pending.delete(message.requestId);
      if (this.activeRequestId === message.requestId) this.activeRequestId = null;
      return;
    }
    this.rejectPreparation?.(error);
    this.resetPreparation();
    for (const { reject } of this.pending.values()) reject(error);
    this.pending.clear();
    this.activeRequestId = null;
  };

  private resetPreparation(): void {
    this.preparationPromise = null;
    this.resolvePreparation = null;
    this.rejectPreparation = null;
  }
}


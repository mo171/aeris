// frontend/lib/audio/speech-stream-player.ts — real-time Kokoro TTS Web Audio streaming player.
//
// what  : Gapless streaming audio scheduler for 24 kHz mono Int16 PCM chunks received from WebSocket.
//         Provides instant hardware barge-in (abort) and aerospace connection notification chime.
// where : Used by useVoiceSession hook to render spoken agent responses and system telemetry.
// how   : Converts Int16 Little-Endian buffers into Float32 AudioBuffers, scheduling them sequentially
//         against AudioContext.currentTime without gaps or drift. Active AudioBufferSourceNodes are tracked
//         in a Set; calling abort() instantly cancels and disconnects every queued node, resetting the timeline.

export class SpeechStreamPlayer {
  private ctx: AudioContext | null = null;
  private nextPlayTime: number = 0;
  private activeSources: Set<AudioBufferSourceNode> = new Set();
  readonly sampleRate: number = 24000;

  constructor(context?: AudioContext) {
    if (context) {
      this.ctx = context;
    }
  }

  /**
   * Lazily initializes or returns the active 24 kHz AudioContext.
   */
  getAudioContext(): AudioContext {
    if (!this.ctx) {
      const AudioCtx =
        window.AudioContext ||
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (window as any).webkitAudioContext;
      this.ctx = new AudioCtx({ sampleRate: this.sampleRate });
    }
    return this.ctx;
  }

  /**
   * Ensures the browser AudioContext is in running state after user interaction.
   */
  async resume(): Promise<void> {
    const ctx = this.getAudioContext();
    if (ctx.state === "suspended") {
      await ctx.resume();
    }
  }

  /**
   * Enqueues an Int16 PCM ArrayBuffer chunk (mono 24 kHz) for sequential playback.
   */
  enqueueChunk(chunk: ArrayBuffer): void {
    if (chunk.byteLength === 0) {
      return;
    }

    const ctx = this.getAudioContext();
    const int16 = new Int16Array(chunk);
    const sampleCount = int16.length;

    const audioBuffer = ctx.createBuffer(1, sampleCount, this.sampleRate);
    const channelData = audioBuffer.getChannelData(0);

    for (let i = 0; i < sampleCount; i++) {
      const sample = int16[i];
      channelData[i] = sample < 0 ? sample / 0x8000 : sample / 0x7fff;
    }

    const now = ctx.currentTime;
    const startTime = Math.max(now, this.nextPlayTime);
    this.nextPlayTime = startTime + audioBuffer.duration;

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    source.start(startTime);

    this.activeSources.add(source);

    source.onended = () => {
      this.activeSources.delete(source);
    };
  }

  /**
   * Instant hardware barge-in: cancels all queued and currently playing sources,
   * disconnecting them and resetting nextPlayTime to context currentTime.
   */
  abort(): void {
    for (const source of this.activeSources) {
      try {
        source.stop();
        source.disconnect();
      } catch {
        // Node may already have finished or disconnected
      }
    }
    this.activeSources.clear();

    if (this.ctx) {
      this.nextPlayTime = this.ctx.currentTime;
    } else {
      this.nextPlayTime = 0;
    }
  }

  /**
   * Synthesizes a clean, subtle aerospace uplink connection chime (two harmonic tones with soft envelope).
   */
  playChime(): void {
    try {
      const ctx = this.getAudioContext();
      const now = ctx.currentTime;

      // Master gain for the chime
      const masterGain = ctx.createGain();
      masterGain.gain.setValueAtTime(0, now);
      masterGain.connect(ctx.destination);

      // Dual harmonic tones: 880 Hz (A5) -> 1320 Hz (E6)
      const tone1 = ctx.createOscillator();
      tone1.type = "sine";
      tone1.frequency.setValueAtTime(880, now);

      const tone2 = ctx.createOscillator();
      tone2.type = "sine";
      tone2.frequency.setValueAtTime(1320, now + 0.08);

      const gain1 = ctx.createGain();
      gain1.gain.setValueAtTime(0, now);
      gain1.gain.linearRampToValueAtTime(0.08, now + 0.015);
      gain1.gain.exponentialRampToValueAtTime(0.0001, now + 0.16);

      const gain2 = ctx.createGain();
      gain2.gain.setValueAtTime(0, now + 0.08);
      gain2.gain.linearRampToValueAtTime(0.06, now + 0.095);
      gain2.gain.exponentialRampToValueAtTime(0.0001, now + 0.35);

      tone1.connect(gain1);
      gain1.connect(masterGain);

      tone2.connect(gain2);
      gain2.connect(masterGain);

      masterGain.gain.setValueAtTime(1.0, now);

      tone1.start(now);
      tone1.stop(now + 0.18);

      tone2.start(now + 0.08);
      tone2.stop(now + 0.38);
    } catch {
      // Audio playback might be restricted if not yet unlocked
    }
  }

  /**
   * Returns current next scheduled playback timestamp.
   */
  getNextPlayTime(): number {
    return this.nextPlayTime;
  }

  /**
   * Returns count of currently active or queued audio sources.
   */
  getActiveSourceCount(): number {
    return this.activeSources.size;
  }

  /**
   * Shuts down player and releases AudioContext resources.
   */
  async close(): Promise<void> {
    this.abort();
    if (this.ctx && this.ctx.state !== "closed") {
      await this.ctx.close();
      this.ctx = null;
    }
  }
}

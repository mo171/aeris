import { describe, expect, it, vi, beforeEach } from "vitest";
import { SpeechStreamPlayer } from "../../lib/audio/speech-stream-player";

class MockAudioBuffer {
  length: number;
  sampleRate: number;
  numberOfChannels: number;
  duration: number;
  private channelData: Float32Array;

  constructor(numberOfChannels: number, length: number, sampleRate: number) {
    this.numberOfChannels = numberOfChannels;
    this.length = length;
    this.sampleRate = sampleRate;
    this.duration = length / sampleRate;
    this.channelData = new Float32Array(length);
  }

  getChannelData(_channel: number): Float32Array {
    return this.channelData;
  }
}

class MockAudioBufferSourceNode {
  buffer: MockAudioBuffer | null = null;
  onended: (() => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
  connect = vi.fn();
  disconnect = vi.fn();
}

class MockGainNode {
  gain = {
    setValueAtTime: vi.fn(),
    linearRampToValueAtTime: vi.fn(),
    exponentialRampToValueAtTime: vi.fn(),
    value: 1,
  };
  connect = vi.fn();
  disconnect = vi.fn();
}

class MockOscillatorNode {
  frequency = {
    setValueAtTime: vi.fn(),
    value: 440,
  };
  type = "sine";
  start = vi.fn();
  stop = vi.fn();
  connect = vi.fn();
  disconnect = vi.fn();
}

function createMockAudioContext(initialTime = 0) {
  const ctx = {
    currentTime: initialTime,
    state: "running" as AudioContextState,
    sampleRate: 24000,
    destination: {} as AudioDestinationNode,
    createBuffer: vi.fn(
      (channels: number, length: number, sampleRate: number) =>
        new MockAudioBuffer(channels, length, sampleRate),
    ),
    createBufferSource: vi.fn(() => new MockAudioBufferSourceNode()),
    createGain: vi.fn(() => new MockGainNode()),
    createOscillator: vi.fn(() => new MockOscillatorNode()),
    resume: vi.fn().mockResolvedValue(undefined),
    close: vi.fn().mockResolvedValue(undefined),
  };
  return ctx as unknown as AudioContext;
}

describe("SpeechStreamPlayer", () => {
  let mockCtx: ReturnType<typeof createMockAudioContext>;
  let player: SpeechStreamPlayer;

  beforeEach(() => {
    mockCtx = createMockAudioContext(10.0);
    player = new SpeechStreamPlayer(mockCtx);
  });

  it("enqueues Int16 PCM chunks, converts to Float32 and schedules playback sequentially", () => {
    // 2400 samples at 24 kHz = 0.1s duration
    const sampleCount = 2400;
    const pcmData = new Int16Array(sampleCount);
    // Fill half max positive and half max negative
    pcmData[0] = 32767;
    pcmData[1] = -32768;

    player.enqueueChunk(pcmData.buffer);

    expect(mockCtx.createBuffer).toHaveBeenCalledWith(1, sampleCount, 24000);
    expect(mockCtx.createBufferSource).toHaveBeenCalledTimes(1);

    // Initial play time should start at currentTime (10.0)
    expect(player.getNextPlayTime()).toBeCloseTo(10.1, 4);

    // Enqueue second chunk: should schedule right after the first (at 10.1s)
    player.enqueueChunk(pcmData.buffer);
    expect(mockCtx.createBufferSource).toHaveBeenCalledTimes(2);
    expect(player.getNextPlayTime()).toBeCloseTo(10.2, 4);
  });

  it("converts Int16 PCM values accurately into [-1.0, 1.0] range", () => {
    const pcmData = new Int16Array([0, 16384, 32767, -32768, -16384]);
    player.enqueueChunk(pcmData.buffer);

    const createdBuffer = vi.mocked(mockCtx.createBuffer).mock.results[0]?.value as MockAudioBuffer;
    const channelData = createdBuffer.getChannelData(0);

    expect(channelData[0]).toBeCloseTo(0, 4);
    expect(channelData[1]).toBeCloseTo(16384 / 32767, 3);
    expect(channelData[2]).toBeCloseTo(1.0, 3);
    expect(channelData[3]).toBeCloseTo(-1.0, 3);
    expect(channelData[4]).toBeCloseTo(-16384 / 32768, 3);
  });

  it("aborts playback immediately, stops all active sources, and resets nextPlayTime", () => {
    const pcmData = new Int16Array(2400);
    player.enqueueChunk(pcmData.buffer);
    player.enqueueChunk(pcmData.buffer);

    expect(player.getActiveSourceCount()).toBe(2);

    const source1 = vi.mocked(mockCtx.createBufferSource).mock.results[0]?.value as MockAudioBufferSourceNode;
    const source2 = vi.mocked(mockCtx.createBufferSource).mock.results[1]?.value as MockAudioBufferSourceNode;

    // Advance time slightly
    (mockCtx as any).currentTime = 10.05;

    player.abort();

    expect(source1.stop).toHaveBeenCalled();
    expect(source1.disconnect).toHaveBeenCalled();
    expect(source2.stop).toHaveBeenCalled();
    expect(source2.disconnect).toHaveBeenCalled();
    expect(player.getActiveSourceCount()).toBe(0);
    expect(player.getNextPlayTime()).toBe(10.05);
  });

  it("plays aerospace uplink activation chime without errors", () => {
    player.playChime();

    expect(mockCtx.createOscillator).toHaveBeenCalled();
    expect(mockCtx.createGain).toHaveBeenCalled();
  });
});

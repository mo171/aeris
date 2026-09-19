// frontend/public/audio-processors/pcm-capture-processor.js
//
// AudioWorkletProcessor registered as 'pcm-capture-processor'.
// Captures channel 0 Float32 microphone input, resamples/downsamples to 16 kHz mono,
// accumulates into 512-sample (32 ms) Int16 Little-Endian PCM buffers, and transfers
// the underlying ArrayBuffer over the MessagePort.

class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetSampleRate = 16000;
    this.bufferSize = 512; // 512 samples at 16 kHz = 32 ms
    this.outputBuffer = new Int16Array(this.bufferSize);
    this.outputIndex = 0;

    // AudioWorkletGlobalScope defines sampleRate as the context's actual sample rate
    const currentSampleRate = typeof sampleRate !== "undefined" ? sampleRate : 16000;
    this.sourceSampleRate = currentSampleRate;
    this.resampleRatio = this.sourceSampleRate / this.targetSampleRate;
    this.resamplePhase = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) {
      return true;
    }

    const channelData = input[0];
    if (!channelData || channelData.length === 0) {
      return true;
    }

    // Direct 1:1 if sample rates match
    if (Math.abs(this.resampleRatio - 1) < 0.001) {
      for (let i = 0; i < channelData.length; i++) {
        const sample = Math.max(-1, Math.min(1, channelData[i]));
        this.outputBuffer[this.outputIndex++] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;

        if (this.outputIndex >= this.bufferSize) {
          const buffer = this.outputBuffer;
          this.port.postMessage(buffer.buffer, [buffer.buffer]);
          this.outputBuffer = new Int16Array(this.bufferSize);
          this.outputIndex = 0;
        }
      }
    } else {
      // High-fidelity linear interpolation resampling to 16 kHz
      while (this.resamplePhase < channelData.length) {
        const index = Math.floor(this.resamplePhase);
        const nextIndex = Math.min(index + 1, channelData.length - 1);
        const fraction = this.resamplePhase - index;

        const sample = (1 - fraction) * channelData[index] + fraction * channelData[nextIndex];
        const clamped = Math.max(-1, Math.min(1, sample));

        this.outputBuffer[this.outputIndex++] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;

        if (this.outputIndex >= this.bufferSize) {
          const buffer = this.outputBuffer;
          this.port.postMessage(buffer.buffer, [buffer.buffer]);
          this.outputBuffer = new Int16Array(this.bufferSize);
          this.outputIndex = 0;
        }

        this.resamplePhase += this.resampleRatio;
      }

      this.resamplePhase -= channelData.length;
    }

    return true;
  }
}

registerProcessor("pcm-capture-processor", PcmCaptureProcessor);

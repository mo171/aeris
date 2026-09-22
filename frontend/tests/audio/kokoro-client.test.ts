import { describe, expect, it } from "vitest";

import {
  KOKORO_DTYPE,
  KOKORO_MODEL_ID,
  KOKORO_SAMPLE_RATE,
  KOKORO_VOICE,
} from "../../lib/audio/kokoro-config";

describe("Kokoro configuration", () => {
  it("locks V-1 synthesis to the q8 British male George voice", () => {
    expect(KOKORO_MODEL_ID).toBe("onnx-community/Kokoro-82M-v1.0-ONNX");
    expect(KOKORO_DTYPE).toBe("q8");
    expect(KOKORO_VOICE).toBe("bm_george");
    expect(KOKORO_SAMPLE_RATE).toBe(24_000);
  });
});

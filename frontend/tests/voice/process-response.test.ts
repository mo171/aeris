import { describe, expect, it } from "vitest";

import { createLocalVoiceResponse } from "../../app/api/voice/process/voice-response";

describe("local voice process response", () => {
  it("preserves transcript, reply, and actions without cloud audio", () => {
    const actions = [
      {
        commandId: "investigation.zoom",
        params: { level: 4 },
        description: "Zooming the investigation map",
      },
    ];

    expect(
      createLocalVoiceResponse({
        transcript: "Zoom in",
        reply: "Zooming in now, sir.",
        actions,
      }),
    ).toEqual({
      success: true,
      transcript: "Zoom in",
      reply: "Zooming in now, sir.",
      actions,
      audioBase64: null,
      speechProvider: "kokoro-local",
    });
  });
});

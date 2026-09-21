import { describe, expect, it, vi, beforeEach } from "vitest";
import { POST } from "../../app/api/voice/process/route";

describe("POST /api/voice/process (AERIS Voice AI Agent)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    delete process.env.OPENAI_API_KEY;
  });

  it("returns 400 when no query or audio is provided", async () => {
    const request = new Request("http://localhost:3000/api/voice/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: "" }),
    });

    const response = await POST(request);
    expect(response.status).toBe(400);
    const data = await response.json();
    expect(data.success).toBe(false);
    expect(data.error).toContain("No audible speech or query detected, sir.");
  });

  it("returns polite standby message when OPENAI_API_KEY is unset", async () => {
    const request = new Request("http://localhost:3000/api/voice/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: "AERIS, highlight the radar structures" }),
    });

    const response = await POST(request);
    expect(response.status).toBe(200);
    const data = await response.json();
    expect(data.success).toBe(true);
    expect(data.transcript).toBe("AERIS, highlight the radar structures");
    expect(data.reply).toContain("Standing by, sir");
    expect(data.reply).toContain("frontend/.env");
  });

  it("returns activation greeting for action: 'greeting'", async () => {
    const request = new Request("http://localhost:3000/api/voice/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "greeting" }),
    });

    const response = await POST(request);
    expect(response.status).toBe(200);
    const data = await response.json();
    expect(data.success).toBe(true);
    expect(data.reply).toBe("Voice command mode activated. AERIS online and at your service, sir.");
  });

  it("returns 400 when audio file is uploaded but OPENAI_API_KEY is not configured", async () => {
    const formData = new FormData();
    const fakeAudio = new Blob([new Uint8Array(1000)], { type: "audio/wav" });
    formData.append("audio", fakeAudio, "speech.wav");

    const request = new Request("http://localhost:3000/api/voice/process", {
      method: "POST",
      body: formData,
    });

    const response = await POST(request);
    expect(response.status).toBe(400);
    const data = await response.json();
    expect(data.success).toBe(false);
    expect(data.error).toContain("OPENAI_API_KEY is not configured");
    expect(data.error).toContain("AERIS");
  });

  it("returns 400 when audio file is too short/silent (<500 bytes)", async () => {
    process.env.OPENAI_API_KEY = "test-key";
    const formData = new FormData();
    const tinyAudio = new Blob([new Uint8Array(100)], { type: "audio/wav" });
    formData.append("audio", tinyAudio, "speech.wav");

    const request = new Request("http://localhost:3000/api/voice/process", {
      method: "POST",
      body: formData,
    });

    const response = await POST(request);
    expect(response.status).toBe(400);
    const data = await response.json();
    expect(data.success).toBe(false);
    expect(data.error).toContain("Audio recording was too brief or silent");
  });

  it("handles 'see the images that are selected' query gracefully", async () => {
    // With no API key, returns standby
    const request = new Request("http://localhost:3000/api/voice/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: "see the images that are selected",
        context: { surface: "/", selectedSceneIds: [] },
      }),
    });

    const response = await POST(request);
    expect(response.status).toBe(200);
    const data = await response.json();
    expect(data.success).toBe(true);
    expect(data.transcript).toBe("see the images that are selected");
  });
});

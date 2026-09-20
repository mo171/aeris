// app/api/voice/process/route.ts — AERIS Multimodal Voice AI Agent.
//
// what  : High-performance endpoint orchestrating Whisper transcription, GPT-5 Astra reasoning
//         with UI tool calling, and British TTS speech synthesis.
// persona : Authentic British aerospace AI assistant (polite, articulate, addresses user as "Sir").
// tools   : Directly drives AERIS command bus (flyTo, toggleLayer, soloLayer, splitPosition, operations, reports).

import { NextResponse } from "next/server";
import OpenAI, { toFile } from "openai";
import type { ChatCompletionTool } from "openai/resources/chat/completions";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Known geographic coordinate bookmarks around Mumbai EO scene
const LANDMARK_BOUNDS: Record<string, { west: number; south: number; east: number; north: number }> = {
  mazgaon_docks: { west: 72.835, south: 18.955, east: 72.865, north: 18.980 },
  sewri_mudflats: { west: 72.845, south: 18.985, east: 72.880, north: 19.015 },
  nhava_sheva: { west: 72.930, south: 18.930, east: 72.970, north: 18.970 },
  mumbai_harbour: { west: 72.81855, south: 18.91907, east: 72.90132, north: 19.03092 },
  overview: { west: 72.70, south: 18.85, east: 73.05, north: 19.15 },
};

// Known analytical evidence layers in the Mumbai AOI
const LAYER_MAP: Record<string, { id: string; title: string }> = {
  ndvi: { id: "lyr_mumbai_ndvi_vegetation", title: "Coastal Mangrove Canopy (NDVI)" },
  builtup_ndbi: { id: "lyr_01M2FRFSR88QXBFXSDESV0WD87", title: "Optical Built-up (NDBI)" },
  water_mndwi: { id: "lyr_01M2FRFX1YK5V4X4QV2KF3FDRP", title: "Optical Water Extent (MNDWI)" },
  sar_structural: { id: "lyr_mumbai_sar_structural_change", title: "SAR Structural Shifts & Gantry Assets" },
  sar_water: { id: "lyr_01M2FRG1V18KRWB4P71RG03XHV", title: "Radar Specular Water" },
  groundwater_moisture: { id: "lyr_mumbai_groundwater_moisture", title: "Intertidal Mudflat Moisture Flux" },
  cross_modal_fusion: { id: "lyr_mumbai_construction_objects", title: "Port Infrastructure & Detected Assets" },
};

/**
 * Deterministically inspects magic numbers and container headers of an audio buffer
 * to provide OpenAI Whisper with a strictly supported file extension and clean MIME type.
 * Whisper supported formats: flac, m4a, mp3, mp4, mpeg, mpga, oga, ogg, wav, webm.
 */
function detectAudioFormat(
  buffer: Buffer,
  originalName?: string | null,
  originalType?: string | null,
): { filename: string; mimeType: string } {
  // 1. WAV magic: RIFF....WAVE
  if (
    buffer.length >= 12 &&
    buffer.subarray(0, 4).toString("ascii") === "RIFF" &&
    buffer.subarray(8, 12).toString("ascii") === "WAVE"
  ) {
    return { filename: "speech.wav", mimeType: "audio/wav" };
  }

  // 2. WebM/Matroska EBML header: 0x1A 0x45 0xDF 0xA3
  if (
    buffer.length >= 4 &&
    buffer[0] === 0x1a &&
    buffer[1] === 0x45 &&
    buffer[2] === 0xdf &&
    buffer[3] === 0xa3
  ) {
    return { filename: "speech.webm", mimeType: "audio/webm" };
  }

  // 3. MP4 / M4A: bytes 4..8 == "ftyp"
  if (buffer.length >= 8 && buffer.subarray(4, 8).toString("ascii") === "ftyp") {
    return { filename: "speech.mp4", mimeType: "audio/mp4" };
  }

  // 4. Ogg container: "OggS"
  if (buffer.length >= 4 && buffer.subarray(0, 4).toString("ascii") === "OggS") {
    return { filename: "speech.ogg", mimeType: "audio/ogg" };
  }

  // 5. FLAC: "fLaC"
  if (buffer.length >= 4 && buffer.subarray(0, 4).toString("ascii") === "fLaC") {
    return { filename: "speech.flac", mimeType: "audio/flac" };
  }

  // 6. MP3 ID3 header
  if (buffer.length >= 3 && buffer.subarray(0, 3).toString("ascii") === "ID3") {
    return { filename: "speech.mp3", mimeType: "audio/mpeg" };
  }

  // 7. Check by extension or original mime if magic bytes were not matched
  const name = (originalName || "").toLowerCase();
  const mime = (originalType || "").toLowerCase();

  if (name.endsWith(".wav") || mime.includes("wav")) {
    return { filename: "speech.wav", mimeType: "audio/wav" };
  }
  if (name.endsWith(".mp4") || name.endsWith(".m4a") || mime.includes("mp4")) {
    return { filename: "speech.mp4", mimeType: "audio/mp4" };
  }
  if (name.endsWith(".mp3") || mime.includes("mpeg") || mime.includes("mp3")) {
    return { filename: "speech.mp3", mimeType: "audio/mpeg" };
  }
  if (name.endsWith(".ogg") || mime.includes("ogg")) {
    return { filename: "speech.ogg", mimeType: "audio/ogg" };
  }

  // Default to WAV
  return { filename: "speech.wav", mimeType: "audio/wav" };
}

// AERIS Persona System Prompt
const AERIS_SYSTEM_PROMPT = `
You are AERIS (Autonomous Earth Observation System), the sophisticated, articulate, and supremely capable British AI voice assistant and executive flight director for the AERIS platform, possessing the iconic bold British demeanor and razor-sharp intellect of Tony Stark's JARVIS.

PERSONALITY & DEMEANOR:
- Address the operator exclusively as "Sir".
- Tone: Impeccably polite, bold, razor-sharp, calm, and effortlessly confident with a proper, distinguished British cadence.
- Speak in natural spoken English (NO markdown, NO asterisks, NO bullet points, NO brackets in your reply string, as your exact text is synthesized into high-definition voice audio).
- Keep verbal confirmations punchy, concise, and smooth (1 to 2 sentences max), confirming what you are doing on the UI before/as the action executes.
  Example: "Right away, sir. Isolating the SAR structural backscatter across Mazgaon Docks."
  Example: "Adjusting the split comparator to eighty percent to highlight the reclamation boundary, sir."
  Example: "Certainly, sir. Navigating to the Sewri mudflats and spotlighting the moisture flux anomaly."
  Example: "Running autonomous cross-modal late fusion now, sir. Telemetry will update on the canvas."

ACTION CAPABILITIES:
You have direct controls over the AERIS user interface. When the user asks to see, zoom, toggle, analyze, compare, or view anything on the platform, ALWAYS invoke the corresponding tool(s). Do not make the user click with their mouse—you are AERIS, you control the system for them.
`.trim();

// Tools defined for OpenAI function calling
const AERIS_TOOLS: ChatCompletionTool[] = [
  {
    type: "function",
    function: {
      name: "navigate_globe",
      description: "Flies the 3D globe camera to a specific landmark or AOI sector in Mumbai.",
      parameters: {
        type: "object",
        properties: {
          location: {
            type: "string",
            enum: ["mazgaon_docks", "sewri_mudflats", "nhava_sheva", "mumbai_harbour", "overview"],
            description: "The geographic area or landmark to frame on the globe.",
          },
        },
        required: ["location"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "toggle_layer",
      description: "Controls visibility of analytical satellite layers (NDVI, NDBI, SAR structural, moisture flux, etc.).",
      parameters: {
        type: "object",
        properties: {
          layerKey: {
            type: "string",
            enum: [
              "ndvi",
              "builtup_ndbi",
              "water_mndwi",
              "sar_structural",
              "sar_water",
              "groundwater_moisture",
              "cross_modal_fusion",
            ],
            description: "The analytical product layer to toggle.",
          },
          visible: {
            type: "boolean",
            description: "Whether the layer should be visible (true) or hidden (false).",
          },
          solo: {
            type: "boolean",
            description: "If true, isolates this layer exclusively and hides all other analytical layers.",
          },
        },
        required: ["layerKey", "visible"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "adjust_comparator",
      description: "Controls the optical/radar split-slider comparator and sweep mode.",
      parameters: {
        type: "object",
        properties: {
          splitPosition: {
            type: "number",
            minimum: 0,
            maximum: 100,
            description: "Position of the split divider percentage from left (0) to right (100).",
          },
          mode: {
            type: "string",
            enum: ["split", "blend", "diff"],
            description: "The comparison mode: split slider, dual-blend, or spectral difference.",
          },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "run_analysis_operation",
      description: "Dispatches an autonomous or targeted satellite analysis run on the scene.",
      parameters: {
        type: "object",
        properties: {
          operationId: {
            type: "string",
            enum: ["ndvi", "urban-footprint", "water-index", "sar-analysis", "cross-modal", "autonomous"],
            description: "Specific analysis pipeline to trigger.",
          },
          query: {
            type: "string",
            description: "Optional natural language question to guide the analysis.",
          },
        },
        required: ["operationId"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "focus_evidence",
      description: "Highlights and frames a specific detected evidence cluster on the globe and evidence panel.",
      parameters: {
        type: "object",
        properties: {
          target: {
            type: "string",
            enum: ["cranes", "docklands", "mudflats", "strongest_change"],
            description: "The evidence feature to spotlight.",
          },
        },
        required: ["target"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "switch_panel",
      description: "Switches the active UI panel or modal view.",
      parameters: {
        type: "object",
        properties: {
          panel: {
            type: "string",
            enum: ["evidence", "acquisitions", "claims", "trace", "report"],
            description: "The interface view to bring into focus.",
          },
        },
        required: ["panel"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "reset_view",
      description: "Resets the globe view back to the standard orbital overview.",
      parameters: {
        type: "object",
        properties: {},
      },
    },
  },
];

export interface UiAction {
  commandId: string;
  params: Record<string, unknown>;
  description: string;
}

export async function POST(request: Request) {
  const apiKey = process.env.OPENAI_API_KEY?.trim();
  const configuredModel = process.env.OPENAI_MODEL?.trim() || "gpt-5-astra";
  const voice = process.env.OPENAI_VOICE?.trim() || "fable"; // British accent in OpenAI TTS

  let userText = "";

  try {
    const contentType = request.headers.get("content-type") || "";

    // ── 1. Extract Speech or Text ─────────────────────────────────────────────────────────────
    if (contentType.includes("multipart/form-data")) {
      const formData = await request.formData();
      const audioFile = formData.get("audio") as File | null;
      const textQuery = formData.get("query") as string | null;

      if (textQuery && textQuery.trim()) {
        userText = textQuery.trim();
      } else if (audioFile && audioFile.size > 0) {
        if (!apiKey) {
          return NextResponse.json(
            {
              success: false,
              error: "OPENAI_API_KEY is not configured in frontend/.env. Please configure your key to activate AERIS.",
            },
            { status: 400 },
          );
        }

        const buffer = Buffer.from(await audioFile.arrayBuffer());
        if (buffer.length < 500) {
          return NextResponse.json(
            {
              success: false,
              error: "Audio recording was too brief or silent, sir. Please speak clearly into your microphone.",
            },
            { status: 400 },
          );
        }

        // Accurately detect format from magic bytes & container headers
        const detected = detectAudioFormat(buffer, audioFile.name, audioFile.type);

        const openai = new OpenAI({ apiKey });
        const uploadFile = await toFile(buffer, detected.filename, {
          type: detected.mimeType,
        });

        // High-performance transcription via Whisper
        const transcription = await openai.audio.transcriptions.create({
          file: uploadFile,
          model: "whisper-1",
          language: "en",
          prompt: "AERIS satellite earth observation, Sentinel-1 SAR backscatter, Sentinel-2 NDVI, Mazgaon Docks, Sewri mudflats, Mumbai",
        });

        userText = transcription.text.trim();
      }
    } else {
      const body = await request.json();

      if (body.action === "greeting" || body.greeting) {
        const greetingText = "Voice command mode activated. AERIS online and at your service, sir.";
        let audioBase64: string | null = null;
        if (apiKey) {
          try {
            const openai = new OpenAI({ apiKey });
            const speechResponse = await openai.audio.speech.create({
              model: "tts-1-hd",
              voice: voice as "fable" | "onyx" | "alloy" | "echo" | "nova" | "shimmer",
              input: greetingText,
              response_format: "mp3",
            });
            const audioBuffer = Buffer.from(await speechResponse.arrayBuffer());
            audioBase64 = `data:audio/mp3;base64,${audioBuffer.toString("base64")}`;
          } catch (ttsErr) {
            console.error("Greeting TTS generation failed:", ttsErr);
          }
        }

        return NextResponse.json({
          success: true,
          transcript: "Voice command mode activated",
          reply: greetingText,
          actions: [],
          audioBase64,
        });
      }

      userText = (body.query || body.text || "").trim();
    }

    if (!userText) {
      return NextResponse.json(
        { success: false, error: "No audible speech or query detected, sir." },
        { status: 400 },
      );
    }

    // ── Fallback if API key is not yet set by user ───────────────────────────────────────────
    if (!apiKey) {
      return NextResponse.json({
        success: true,
        transcript: userText,
        reply: `Standing by, sir. I have received your instruction: "${userText}", but the OpenAI API key has not yet been set in the environment. Please add your key to frontend/.env so I may fully engage.`,
        actions: [],
        audioBase64: null,
      });
    }

    const openai = new OpenAI({ apiKey });

    // ── 2. Run AERIS Reasoning & Tool Calling ────────────────────────────────────────
    // Cascade policy requested by operator: primary -> gpt-5-mini -> gpt-5-terra (never GPT-4)
    const candidateModels = [
      configuredModel,
      "gpt-5-mini",
      "gpt-5-terra",
    ].filter((m, idx, arr) => Boolean(m) && arr.indexOf(m) === idx);

    let completionResponse;
    const modelAttempts: string[] = [];

    for (const model of candidateModels) {
      try {
        // Note: New generation models like gpt-5-mini strictly enforce default temperature (omit temperature)
        completionResponse = await openai.chat.completions.create({
          model,
          messages: [
            { role: "system", content: AERIS_SYSTEM_PROMPT },
            { role: "user", content: userText },
          ],
          tools: AERIS_TOOLS,
          tool_choice: "auto",
        });
        // Succeeded with this model candidate
        break;
      } catch (modelErr: unknown) {
        const errorMessage = modelErr instanceof Error ? modelErr.message : String(modelErr);
        modelAttempts.push(`${model} failed: ${errorMessage}`);
        console.warn(`Model candidate ${model} attempt failed: ${errorMessage}`);
      }
    }

    if (!completionResponse) {
      throw new Error(
        `All requested GPT-5 models failed (${modelAttempts.join("; ")}). No fallback to GPT-4 is permitted.`,
      );
    }

    const message = completionResponse.choices[0]?.message;
    const toolCalls = message?.tool_calls || [];
    let aerisReply = message?.content?.trim() || "";

    const actions: UiAction[] = [];

    // Map tool calls to AERIS command bus actions
    for (const call of toolCalls) {
      if (call.type !== "function") continue;
      const fnName = call.function.name;
      let args: Record<string, any> = {};
      try {
        args = JSON.parse(call.function.arguments || "{}");
      } catch {
        args = {};
      }

      switch (fnName) {
        case "navigate_globe": {
          const location = args.location || "mumbai_harbour";
          const bounds = LANDMARK_BOUNDS[location] || LANDMARK_BOUNDS.mumbai_harbour;
          actions.push({
            commandId: "globe.flyTo",
            params: { bounds },
            description: `Navigating camera to ${location.replace("_", " ")}`,
          });
          break;
        }

        case "toggle_layer": {
          const layerKey = args.layerKey || "sar_structural";
          const layerInfo = LAYER_MAP[layerKey] || LAYER_MAP.sar_structural;
          const isVisible = args.visible ?? true;

          if (args.solo) {
            actions.push({
              commandId: "investigation.soloLayer",
              params: { layerId: layerInfo.id },
              description: `Soloing ${layerInfo.title}`,
            });
          } else {
            actions.push({
              commandId: "investigation.toggleLayer",
              params: { layerId: layerInfo.id, isVisible },
              description: `${isVisible ? "Enabling" : "Disabling"} ${layerInfo.title}`,
            });
          }
          break;
        }

        case "adjust_comparator": {
          if (args.splitPosition !== undefined) {
            const fraction = Math.max(0, Math.min(1, args.splitPosition / 100));
            actions.push({
              commandId: "investigation.setSplitPosition",
              params: { position: fraction },
              description: `Adjusting split comparator to ${args.splitPosition}%`,
            });
          }
          if (args.mode) {
            actions.push({
              commandId: "investigation.setComparator",
              params: { mode: args.mode },
              description: `Setting comparator mode to ${args.mode}`,
            });
          }
          break;
        }

        case "run_analysis_operation": {
          const operationId = args.operationId || "cross-modal";
          if (operationId === "autonomous") {
            actions.push({
              commandId: "investigation.runAutonomous",
              params: {},
              description: "Launching autonomous investigation pipeline",
            });
          } else {
            actions.push({
              commandId: "investigation.runOperation",
              params: { operationId, query: args.query || userText },
              description: `Executing ${operationId} analysis operation`,
            });
          }
          break;
        }

        case "focus_evidence": {
          const target = args.target || "strongest_change";
          let evidenceId = "ev_mumbai_construction_objects";
          if (target === "mudflats") {
            evidenceId = "ev_01M289GZXV2JJ913N9XCPCT4AE";
          }
          actions.push({
            commandId: "investigation.focusEvidence",
            params: { evidenceId },
            description: `Spotlighting ${target} evidence cluster`,
          });
          break;
        }

        case "switch_panel": {
          const panel = args.panel || "evidence";
          if (panel === "report") {
            actions.push({
              commandId: "investigation.openReport",
              params: {},
              description: "Opening Executive Earth Observation Report",
            });
          } else {
            actions.push({
              commandId: "interface.toggleDataPanel",
              params: { panel },
              description: `Bringing ${panel} panel to front`,
            });
          }
          break;
        }

        case "reset_view": {
          actions.push({
            commandId: "globe.resetView",
            params: {},
            description: "Resetting view to default overview",
          });
          break;
        }
      }
    }

    // Ensure AERIS always has a polite, crisp spoken response
    if (!aerisReply) {
      if (actions.length > 0) {
        aerisReply = `Right away, sir. Executing ${actions.map((a) => a.description).join(" and ")}.`;
      } else {
        aerisReply = "At your command, sir. All telemetry channels are operating at peak efficiency.";
      }
    }

    // Clean any accidental markdown or quotes from spoken text
    const cleanSpokenText = aerisReply.replace(/[*_#`[\]()]/g, "").trim();

    // ── 3. Synthesize Voice with OpenAI TTS-HD (British 'fable' voice) ─────────────────────────
    let audioBase64: string | null = null;
    try {
      const speechResponse = await openai.audio.speech.create({
        model: "tts-1-hd",
        voice: voice as "fable" | "onyx" | "alloy" | "echo" | "nova" | "shimmer",
        input: cleanSpokenText,
        response_format: "mp3",
      });

      const audioBuffer = Buffer.from(await speechResponse.arrayBuffer());
      audioBase64 = `data:audio/mp3;base64,${audioBuffer.toString("base64")}`;
    } catch (ttsError) {
      console.error("OpenAI TTS audio generation failed:", ttsError);
    }

    return NextResponse.json({
      success: true,
      transcript: userText,
      reply: cleanSpokenText,
      actions,
      audioBase64,
    });
  } catch (error: unknown) {
    console.error("AERIS voice processing error:", error);
    const msg = error instanceof Error ? error.message : "Internal voice processing error";
    return NextResponse.json(
      {
        success: false,
        error: `AERIS Uplink Encountered an issue: ${msg}`,
      },
      { status: 500 },
    );
  }
}

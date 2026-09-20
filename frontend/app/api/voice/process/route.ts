// app/api/voice/process/route.ts — AERIS Multimodal Voice AI Agent.
//
// what  : High-performance endpoint orchestrating Whisper transcription, GPT-5 Astra reasoning
//         with UI tool calling, and British TTS speech synthesis.
// persona : Authentic British aerospace AI assistant (polite, articulate, addresses user as "Sir").
// tools   : Directly drives AERIS command bus (flyTo, toggleLayer, soloLayer, splitPosition, operations, reports).

import { NextResponse } from "next/server";
import OpenAI, { toFile } from "openai";
import type { ChatCompletionTool } from "openai/resources/chat/completions";

import { COMMAND_IDS } from "@/lib/constants/commands";

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
You have direct controls over the AERIS user interface. When the user asks to see, zoom, toggle, analyze, compare, view, open, show, hide, or close anything on the platform, ALWAYS invoke the corresponding tool(s) — a spoken acknowledgement ALONE is a failure; the UI must visibly change. Do not make the user click with their mouse—you are AERIS, you control the system for them.
Panel requests always go through switch_panel: "investigation panel" means panel inputs; "layers", "toolbox", "analysis", "evidence", "chat", "trace", "report" map to the same-named panel; "answer panel" means analysis. "Close/hide" means visible false.
`.trim();

// Tools defined for OpenAI function calling. Exported so the contract test
// proves the brain's vocabulary against the real COMMAND_IDS.
export const AERIS_TOOLS: ChatCompletionTool[] = [
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
      description:
        "Controls the before/after comparator. splitPosition moves the divider (0-100). " +
        "binding chooses what the comparator compares: temporal (baseline against comparison) or crossModal (SAR against optical).",
      parameters: {
        type: "object",
        properties: {
          splitPosition: {
            type: "number",
            minimum: 0,
            maximum: 100,
            description: "Position of the split divider percentage from left (0) to right (100).",
          },
          binding: {
            type: "string",
            enum: ["temporal", "crossModal"],
            description: "What the comparator handle compares.",
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
      description:
        "Shows or hides a panel on the investigation screen. " +
        "Panels: inputs (left panel, scenes/acquisitions/regions — also called the 'investigation panel'), " +
        "layers (left panel evidence overlays), toolbox (left panel runnable analyses), " +
        "analysis (right answer panel verdict), evidence (right answer panel supporting geometry), " +
        "chat (right answer panel conversation), trace (execution spine), report (report drawer). " +
        "Always call this when the operator says open/show/hide/close a panel, tab, or view — never answer with words alone.",
      parameters: {
        type: "object",
        properties: {
          panel: {
            type: "string",
            enum: [
              "inputs",
              "layers",
              "toolbox",
              "analysis",
              "evidence",
              "chat",
              "trace",
              "report",
            ],
            description: "The panel or tab to show or hide.",
          },
          visible: {
            type: "boolean",
            description: "True to show, false to hide. Defaults to true.",
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
  {
    type: "function",
    function: {
      name: "investigate_selection",
      description:
        "Creates an investigation from the operator's currently selected imagery and takes them into the investigation workspace. " +
        "Use when they say investigate, take me to investigation, or look deeper into these/the selected images. " +
        "Only call this when the context lists selected scenes; with none selected, ask the operator to select imagery first instead.",
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

// Deep, calm British Jarvis-style delivery applied to every utterance when the
// configured TTS model supports style instructions (gpt-4o-mini-tts does).
const JARVIS_VOICE_INSTRUCTIONS =
  "Speak with a deep, calm, authoritative British accent in the manner of an aerospace AI butler. " +
  "Measured pace, crisp consonants, low steady pitch. Never rushed, never breathy.";

/**
 * Synthesizes speech with the configured Jarvis voice. Tries the modern
 * instruction-aware model first so the British accent is deliberate rather
 * than incidental, and falls back to tts-1-hd (no instructions support) so a
 * model rollout never leaves AERIS mute.
 */
async function synthesizeJarvisSpeech(
  openai: OpenAI,
  text: string,
  voice: string,
  ttsModel: string,
): Promise<string | null> {
  const attempts: Array<Record<string, unknown>> = [];
  if (ttsModel !== "tts-1-hd") {
    attempts.push({ model: ttsModel, voice, input: text, instructions: JARVIS_VOICE_INSTRUCTIONS });
  }
  attempts.push({ model: "tts-1-hd", voice, input: text });

  for (const params of attempts) {
    try {
      const speechResponse = await openai.audio.speech.create({
        ...(params as { model: "tts-1-hd"; voice: "onyx"; input: string }),
        response_format: "mp3",
      });
      const audioBuffer = Buffer.from(await speechResponse.arrayBuffer());
      return `data:audio/mp3;base64,${audioBuffer.toString("base64")}`;
    } catch (ttsError) {
      console.error(`Jarvis TTS attempt (${String(params.model)}) failed:`, ttsError);
    }
  }
  return null;
}

/**
 * Maps one brain tool call to command-bus actions. Pure and exported so the
 * contract test can prove every voice utterance resolves to real COMMAND_IDS —
 * the voice vocabulary and the registry can never silently drift apart again.
 */
export interface VoiceOperatorContext {
  surface: string;
  selectedSceneIds: string[];
}

// Same demo project the Mission Command Investigate button files under
// (MissionCommandScreen handleInvestigate). Voice-created investigations land
// in the same place a click would put them.
const DEFAULT_VOICE_PROJECT_ID = "prj_sih2026_demo";

export function mapVoiceToolToActions(
  toolName: string,
  args: Record<string, any>,
  userText: string,
  context?: VoiceOperatorContext,
): UiAction[] {
  const mapped: UiAction[] = [];

  switch (toolName) {
    case "navigate_globe": {
      const location = args.location || "mumbai_harbour";
      const bounds = LANDMARK_BOUNDS[location] || LANDMARK_BOUNDS.mumbai_harbour;
      // globe.flyTo on every surface takes a lat/lon target — the registry
      // rejects anything else, so fly to the bounds centre.
      mapped.push({
        commandId: COMMAND_IDS.globe.flyTo,
        params: {
          latitude: (bounds.south + bounds.north) / 2,
          longitude: (bounds.west + bounds.east) / 2,
        },
        description: `Navigating camera to ${location.replace("_", " ")}`,
      });
      break;
    }

    case "toggle_layer": {
      const layerKey = args.layerKey || "sar_structural";
      const layerInfo = LAYER_MAP[layerKey] || LAYER_MAP.sar_structural;
      const isVisible = args.visible ?? true;

      if (args.solo) {
        mapped.push({
          commandId: COMMAND_IDS.investigation.soloLayer,
          params: { layerId: layerInfo.id },
          description: `Soloing ${layerInfo.title}`,
        });
      } else {
        mapped.push({
          commandId: COMMAND_IDS.investigation.toggleLayer,
          params: { layerId: layerInfo.id, isVisible },
          description: `${isVisible ? "Enabling" : "Disabling"} ${layerInfo.title}`,
        });
      }
      break;
    }

    case "adjust_comparator": {
      if (args.splitPosition !== undefined) {
        const fraction = Math.max(0, Math.min(1, args.splitPosition / 100));
        mapped.push({
          commandId: COMMAND_IDS.investigation.setSplitPosition,
          params: { position: fraction },
          description: `Adjusting split comparator to ${args.splitPosition}%`,
        });
      }
      // investigation.setComparator takes { binding: "temporal" | "crossModal" }.
      if (args.binding === "temporal" || args.binding === "crossModal") {
        mapped.push({
          commandId: COMMAND_IDS.investigation.setComparator,
          params: { binding: args.binding },
          description: `Setting comparator to ${args.binding === "temporal" ? "baseline against comparison" : "SAR against optical"}`,
        });
      }
      break;
    }

    case "run_analysis_operation": {
      const requested = args.operationId || "cross-modal";
      if (requested === "autonomous") {
        mapped.push({
          commandId: COMMAND_IDS.investigation.runAutonomous,
          params: {},
          description: "Launching autonomous investigation pipeline",
        });
        break;
      }
      // The voice vocabulary is friendly shorthand; the registry only
      // accepts real ANALYSIS_OPERATIONS ids, so translate here.
      const OPERATION_ALIASES: Record<string, string> = {
        ndvi: "vegetation-analysis",
        "urban-footprint": "built-up-detection",
        "water-index": "water-detection",
        "sar-analysis": "sar-analysis",
        "cross-modal": "cross-modal",
      };
      const operationId = OPERATION_ALIASES[requested] ?? requested;
      mapped.push({
        commandId: COMMAND_IDS.investigation.runOperation,
        params: { operationId },
        description: `Executing ${requested} analysis operation`,
      });
      break;
    }

    case "focus_evidence": {
      const target = args.target || "strongest_change";
      // No params means "frame the highest-magnitude evidence" — the only
      // form that cannot name an id that does not exist. Named targets are
      // best-effort: unknown ids no-op in the handler and report back.
      if (target === "strongest_change") {
        mapped.push({
          commandId: COMMAND_IDS.investigation.focusEvidence,
          params: {},
          description: "Spotlighting the biggest change",
        });
      } else {
        const KNOWN_EVIDENCE_IDS: Record<string, string> = {
          mudflats: "ev_01M289GZXV2JJ913N9XCPCT4AE",
          docklands: "ev_mumbai_construction_objects",
          cranes: "ev_mumbai_construction_objects",
        };
        mapped.push({
          commandId: COMMAND_IDS.investigation.focusEvidence,
          params: target in KNOWN_EVIDENCE_IDS ? { evidenceId: KNOWN_EVIDENCE_IDS[target] } : {},
          description: `Spotlighting ${target} evidence cluster`,
        });
      }
      break;
    }

    case "switch_panel": {
      // Vocabulary mirrors the real UI: left-panel tabs, right-panel tabs,
      // trace spine, report drawer. Every branch pairs a tab switch with a
      // deterministic panel open so the result is visible even if the
      // panel was closed — opening a tab inside a closed panel shows nothing.
      const panel = args.panel || "inputs";
      const visible = args.visible ?? true;
      const showHide = visible ? "Showing" : "Hiding";
      if (panel === "report") {
        mapped.push({
          commandId: COMMAND_IDS.investigation.openReport,
          params: { open: visible },
          description: `${showHide} the Executive Earth Observation Report`,
        });
      } else if (panel === "trace") {
        mapped.push({
          commandId: COMMAND_IDS.investigation.toggleTrace,
          params: { expanded: visible },
          description: `${showHide} the execution trace`,
        });
      } else if (panel === "inputs" || panel === "layers" || panel === "toolbox") {
        mapped.push({
          commandId: COMMAND_IDS.investigation.setLeftTab,
          params: { tab: panel },
          description: `${showHide} the ${panel} tab`,
        });
        mapped.push({
          commandId: COMMAND_IDS.interface.toggleDataPanel,
          params: { open: visible },
          description: `${showHide} the investigation panel`,
        });
      } else {
        mapped.push({
          commandId: COMMAND_IDS.investigation.setRightTab,
          params: { tab: panel },
          description: `${showHide} the ${panel} tab`,
        });
        mapped.push({
          commandId: COMMAND_IDS.interface.toggleAssistantPanel,
          params: { open: visible },
          description: `${showHide} the answer panel`,
        });
      }
      break;
    }

    case "investigate_selection": {
      // The prompt forbids this call with an empty selection; the guard here
      // is the second layer — the mapper never invents scene ids.
      const sceneIds = context?.selectedSceneIds ?? [];
      if (sceneIds.length === 0) {
        break;
      }
      mapped.push({
        commandId: COMMAND_IDS.investigation.create,
        params: {
          projectId: DEFAULT_VOICE_PROJECT_ID,
          sceneIds,
          seedQuery: userText || null,
          missionId: null,
        },
        description: `Opening investigation over ${sceneIds.length} selected scene${sceneIds.length === 1 ? "" : "s"}`,
      });
      break;
    }

    case "reset_view": {
      // investigation.resetView is registered on the investigation screen
      // where voice operates; globe.resetView only exists on Mission
      // Command, so addressing it here would be not-found.
      mapped.push({
        commandId: COMMAND_IDS.investigation.resetView,
        params: {},
        description: "Resetting view to the area of interest",
      });
      break;
    }
  }

  return mapped;
}

export async function POST(request: Request) {
  const apiKey = process.env.OPENAI_API_KEY?.trim();
  const configuredModel = process.env.OPENAI_MODEL?.trim() || "gpt-5-astra";
  // Deep, authoritative masculine voice — the closest OpenAI stock voice to a
  // Jarvis-like British delivery. ("fable" is the thin default; do not revert.)
  const voice = process.env.OPENAI_VOICE?.trim() || "onyx";
  const ttsModel = process.env.OPENAI_TTS_MODEL?.trim() || "gpt-4o-mini-tts";

  let userText = "";

  // Live operator context sent by the frontend with every turn: which screen
  // is mounted (so the brain only orders commands that exist there) and what
  // is selected (so "these images" resolves to real scene ids).
  let operatorContext: { surface: string; selectedSceneIds: string[] } = {
    surface: "unknown",
    selectedSceneIds: [],
  };
  const adoptContext = (raw: unknown) => {
    if (!raw || typeof raw !== "object") return;
    const candidate = raw as { surface?: unknown; selectedSceneIds?: unknown };
    operatorContext = {
      surface: typeof candidate.surface === "string" ? candidate.surface : "unknown",
      selectedSceneIds: Array.isArray(candidate.selectedSceneIds)
        ? candidate.selectedSceneIds.filter((id): id is string => typeof id === "string" && id.length > 0)
        : [],
    };
  };

  try {
    const contentType = request.headers.get("content-type") || "";

    // ── 1. Extract Speech or Text ─────────────────────────────────────────────────────────────
    if (contentType.includes("multipart/form-data")) {
      const formData = await request.formData();
      const audioFile = formData.get("audio") as File | null;
      const textQuery = formData.get("query") as string | null;
      const contextField = formData.get("context") as string | null;
      if (contextField) {
        try {
          adoptContext(JSON.parse(contextField));
        } catch {
          // Malformed context never blocks the turn; the brain just sees less.
        }
      }

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
          const openai = new OpenAI({ apiKey });
          audioBase64 = await synthesizeJarvisSpeech(openai, greetingText, voice, ttsModel);
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
      adoptContext(body.context);
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

    // Ground the brain in the live UI: which screen is mounted determines
    // which commands exist, and the selection resolves "these images".
    const selectionLine =
      operatorContext.selectedSceneIds.length > 0
        ? `Selected scenes: ${operatorContext.selectedSceneIds.join(", ")} (${operatorContext.selectedSceneIds.length} selected). "Investigate / take me to investigation / these images" means call investigate_selection.`
        : "Selected scenes: none. If the operator asks to investigate, do NOT call investigate_selection — tell them to select imagery first.";
    const systemPrompt =
      `${AERIS_SYSTEM_PROMPT}\n\nOPERATOR CONTEXT (live — trust it over guesses):\n` +
      `- Current surface: ${operatorContext.surface}\n- ${selectionLine}`;

    console.log(`[AERIS VOICE] context: surface=${operatorContext.surface} scenes=${operatorContext.selectedSceneIds.length}`);

    for (const model of candidateModels) {
      try {
        // Note: New generation models like gpt-5-mini strictly enforce default temperature (omit temperature)
        completionResponse = await openai.chat.completions.create({
          model,
          messages: [
            { role: "system", content: systemPrompt },
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

    console.log(`[AERIS VOICE] transcript: "${userText}"`);
    console.log(
      `[AERIS VOICE] brain tool calls (${toolCalls.length}):`,
      toolCalls.map((call) =>
        call.type === "function" ? `${call.function.name} ${call.function.arguments}` : call.type,
      ),
    );

    const actions: UiAction[] = [];

    // Map brain tool calls to command-bus actions through the single tested
    // mapper above — this loop must never grow its own inline cases again.
    for (const call of toolCalls) {
      if (call.type !== "function") continue;
      let args: Record<string, any> = {};
      try {
        args = JSON.parse(call.function.arguments || "{}");
      } catch {
        args = {};
      }
      actions.push(
        ...mapVoiceToolToActions(call.function.name, args, userText, operatorContext),
      );
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

    console.log(
      `[AERIS VOICE] mapped actions (${actions.length}):`,
      actions.map((a) => `${a.commandId} ${JSON.stringify(a.params)} — ${a.description}`),
    );

    // ── 3. Synthesize Voice with the Jarvis voice ─────────────────────────
    const audioBase64 = await synthesizeJarvisSpeech(openai, cleanSpokenText, voice, ttsModel);
    console.log(`[AERIS VOICE] TTS ${audioBase64 ? "succeeded" : "FAILED"} (model=${ttsModel}, voice=${voice})`);

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

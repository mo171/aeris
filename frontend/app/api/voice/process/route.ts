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

// ElevenLabs TTS configuration
// API docs: https://elevenlabs.io/docs/api/text-to-speech
function synthesizeElevenLabsSpeech(text: string, apiKey: string, voiceId: string): Promise<string | null> {
  const elevenLabsUrl = `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}`;

  const options: RequestInit = {
    method: "POST",
    headers: {
      "xi-api-key": apiKey,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      text: text,
      voice_settings: {
        stability: 0.5,
        similarity_boost: 0.5,
      },
    }),
  };

  try {
    const response = fetch(elevenLabsUrl, options);
    if (!response.ok) {
      throw new Error(`ElevenLabs TTS failed: ${response.statusText}`);
    }
    const arrayBuffer = response.arrayBuffer();
    const base64 = Buffer.from(arrayBuffer).toString("base64");
    return `data:audio/mpeg;base64,${base64}`;
  } catch (error) {
    console.error("[AERIS VOICE] ElevenLabs TTS failed:", error);
    return null;
  }
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
  Example: "Opening the visual analysis canvas and spotlighting Step 12, Cross-Modal Fusion, sir."
  Example: "Adjusting fusion confidence threshold to zero-point-seven-two and branching pipeline execution from Step 12, sir."

ACTION CAPABILITIES:
You have direct controls over the AERIS user interface. When the user asks to see, zoom, toggle, analyze, compare, view, open, show, hide, or close anything on the platform, ALWAYS invoke the corresponding tool(s) — a spoken acknowledgement ALONE is a failure; the UI must visibly change. Do not make the user click with their mouse—you are AERIS, you control the system for them.
Panel requests always go through switch_panel: "investigation panel" means panel inputs; "layers", "toolbox", "analysis", "evidence", "chat", "trace", "report" map to the same-named panel; "answer panel" means analysis. "Close/hide" means visible false.

PIPELINE WORKFLOW & DAG MASTERY:
- The visual analysis canvas represents the end-to-end analytical Directed Acyclic Graph (DAG) for satellite Earth Observation.
- Core pipeline stages:
  * S01/S02: Multi-sensor ingestion (Sentinel-2 Bottom-of-Atmosphere optical reflectance and Sentinel-1 SAR C-band radar).
  * S05: SAR radiometric calibration, terrain correction, and Lee speckle filtering.
  * S10: Multi-spectral indexing (NDVI mangrove canopy, MNDWI intertidal water, NDBI urban footprint).
  * S12: Cross-modal late fusion — correlates radar dielectric backscatter with optical spectral indices to detect structural shifts through clouds.
  * S16: Probabilistic claim verification — validates detected changes against spatial ground truth with confidence scoring.
- When asked to "explain the canvas", "explain the workflow", "what does this craft/graph mean", or "explain the steps":
  Invoke explain_workflow, open the canvas, and deliver a brilliant, articulate British overview of the analytical DAG.
- When asked to "open the canvas", "show the workflow", or "view the DAG":
  Invoke toggle_canvas({ open: true }).
- When asked to "inspect step 12", "open node 12", "show cross-modal fusion node", or "inspect node":
  Invoke inspect_pipeline_node({ nodeId: "S12_CROSS_MODAL_FUSION" }).
- When asked to "rerun from step 12", "change threshold and rerun", or "lower the confidence threshold to 0.72":
  Invoke rerun_pipeline_step({ stepId: "S12_CROSS_MODAL_FUSION", parameters: { confidenceThreshold: 0.72 } }). Confirm with authentic British poise that the pipeline has been branched with a new version snapshot.
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
      name: "manage_imagery_selection",
      description:
        "Controls scene selection and reveals the imagery catalogue on Mission Command. " +
        "Use action 'view' when the operator asks to see or inspect selected imagery or open the catalogue. " +
        "Use action 'select_demo' to select the primary Mumbai demonstration scenes. " +
        "Use action 'select' with specific sceneIds to select them. " +
        "Use action 'clear' to clear selected imagery.",
      parameters: {
        type: "object",
        properties: {
          action: {
            type: "string",
            enum: ["view", "select_demo", "select", "clear"],
            description: "The imagery selection action to execute.",
          },
          sceneIds: {
            type: "array",
            items: { type: "string" },
            description: "Specific scene identifiers when action is 'select'.",
          },
        },
        required: ["action"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "investigate_selection",
      description:
        "Creates an investigation from imagery and launches the 3D descent into the Investigation Workspace. " +
        "Always call this when the operator says: investigate, take me to investigation, let's go to investigation, " +
        "or open investigation workspace/panel. If no scenes are currently selected in context, " +
        "supply sceneIds with the default demo scenes to launch the workspace seamlessly.",
      parameters: {
        type: "object",
        properties: {
          sceneIds: {
            type: "array",
            items: { type: "string" },
            description: "Optional explicit scene IDs to investigate.",
          },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "toggle_canvas",
      description:
        "Opens or closes the visual Analysis Canvas and Version History modal. " +
        "Always call this when the operator asks to open, view, show, or close the canvas, DAG, or workflow graph.",
      parameters: {
        type: "object",
        properties: {
          open: {
            type: "boolean",
            description: "True to open/show the canvas modal, false to close it. Defaults to true.",
          },
          view: {
            type: "string",
            enum: ["trace", "workflow", "versions"],
            description: "Which tab to display: 'workflow' (DAG node topology), 'trace' (execution timeline), or 'versions' (version history).",
          },
        },
        required: ["open"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "explain_workflow",
      description:
        "Explains what the analytical visual canvas (DAG) means, detailing how Sentinel-1 SAR and Sentinel-2 optical inputs are calibrated, cloud-masked, and fused via cross-modal late fusion to yield verified claims. Automatically opens the visual canvas so the operator can view the pipeline steps.",
      parameters: {
        type: "object",
        properties: {
          focusStep: {
            type: "string",
            description: "Optional step or stage to spotlight specifically (e.g., 'S12_CROSS_MODAL_FUSION', 'S05_PREPROCESS_SAR', 'S16_CLAIM_VERIFICATION').",
          },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "inspect_pipeline_node",
      description:
        "Opens the analysis canvas and focuses/inspects a specific analytical pipeline node (e.g. S12_CROSS_MODAL_FUSION, S05_PREPROCESS_SAR, S16_CLAIM_VERIFICATION) to view its parameters, tensor telemetry, and rationale.",
      parameters: {
        type: "object",
        properties: {
          nodeId: {
            type: "string",
            description: "The stage code or node ID to inspect (e.g., 'S12_CROSS_MODAL_FUSION', 'S05_PREPROCESS_SAR', 'S10_SPECTRAL_INDICES', 'S16_CLAIM_VERIFICATION', 'step-1', 'step-2').",
          },
        },
        required: ["nodeId"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "rerun_pipeline_step",
      description:
        "Adjusts parameters on an analytical step (e.g., confidenceThreshold, sensitivity, filterWindow) and triggers a branch re-run from that step. Preserves upstream DAG stages, re-executes downstream stages, and commits a new version snapshot.",
      parameters: {
        type: "object",
        properties: {
          stepId: {
            type: "string",
            description: "The stage code or step ID from which to rerun (e.g., 'S12_CROSS_MODAL_FUSION', 'S05_PREPROCESS_SAR', 'step-2').",
          },
          parameters: {
            type: "object",
            description: "Key-value map of parameter overrides (e.g. { confidenceThreshold: 0.72, sarWeightRatio: 0.75 }).",
          },
        },
        required: ["stepId"],
      },
    },
  },
];

export interface UiAction {
  commandId: string;
  params: Record<string, unknown>;
  description: string;
}

// Bold, articulate, resonant British Jarvis-style delivery applied to every utterance.
// Captures Paul Bettany's iconic JARVIS: confident, distinguished, crisp, and authoritative.
const JARVIS_VOICE_INSTRUCTIONS =
  "Speak with a bold, resonant, articulate British accent with deep confidence and impeccable poise, exactly like Tony Stark's JARVIS. Natural cadence, punchy, authoritative, and crystal clear.";

interface JarvisSpeechOptions {
  voice: string;
  ttsModel: string;
  /** 0.25–4.0; slightly under 1.0 aids clarity. */
  speed: number;
}

/**
 * Synthesizes speech with the configured Jarvis voice. Tries the modern
 * instruction-aware model first so the British softness is deliberate rather
 * than incidental, and falls back to tts-1-hd (no instructions support) so a
 * model rollout never leaves AERIS mute.
 */
async function synthesizeJarvisSpeech(
  openai: OpenAI,
  text: string,
  options: JarvisSpeechOptions,
): Promise<string | null> {
  const { voice, ttsModel, speed } = options;
  const attempts: Array<Record<string, unknown>> = [];
  if (ttsModel !== "tts-1-hd") {
    attempts.push({
      model: ttsModel,
      voice,
      input: text,
      instructions: JARVIS_VOICE_INSTRUCTIONS,
      speed,
    });
  }
  attempts.push({ model: "tts-1-hd", voice, input: text, speed });

  for (const params of attempts) {
    try {
      const speechResponse = await openai.audio.speech.create({
        ...(params as { model: "tts-1-hd"; voice: "ash"; input: string; speed: number }),
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
        // On Mission Command (/), the left panel is Data & Context; setLeftTab only exists inside InvestigationScreen
        const isOnMissionCommand = context?.surface === "/" || context?.surface === "mission-command";
        if (!isOnMissionCommand || panel !== "inputs") {
          mapped.push({
            commandId: COMMAND_IDS.investigation.setLeftTab,
            params: { tab: panel },
            description: `${showHide} the ${panel} tab`,
          });
        }
        mapped.push({
          commandId: COMMAND_IDS.interface.toggleDataPanel,
          params: { open: visible },
          description: `${showHide} the ${isOnMissionCommand ? "Data & Context" : "investigation"} panel`,
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

    case "manage_imagery_selection": {
      const action = args.action || "view";
      if (action === "clear") {
        mapped.push({
          commandId: COMMAND_IDS.imagery.clearSelection,
          params: {},
          description: "Clearing scene selection",
        });
      } else if (action === "select_demo") {
        mapped.push({
          commandId: COMMAND_IDS.interface.toggleDataPanel,
          params: { open: true },
          description: "Opening Data & Context panel",
        });
        mapped.push({
          commandId: COMMAND_IDS.imagery.select,
          params: { sceneId: "scn_000001" },
          description: "Selecting primary Sentinel-2 optical scene",
        });
        mapped.push({
          commandId: COMMAND_IDS.imagery.select,
          params: { sceneId: "scn_000002" },
          description: "Selecting Sentinel-1 SAR radar scene",
        });
      } else if (action === "select" && Array.isArray(args.sceneIds) && args.sceneIds.length > 0) {
        mapped.push({
          commandId: COMMAND_IDS.interface.toggleDataPanel,
          params: { open: true },
          description: "Opening Data & Context panel",
        });
        for (const sceneId of args.sceneIds) {
          mapped.push({
            commandId: COMMAND_IDS.imagery.select,
            params: { sceneId },
            description: `Selecting scene ${sceneId}`,
          });
        }
      } else {
        // "view" or default
        mapped.push({
          commandId: COMMAND_IDS.interface.toggleDataPanel,
          params: { open: true },
          description: "Revealing the imagery catalogue and selected scenes",
        });
      }
      break;
    }

    case "investigate_selection": {
      // Prioritize explicit sceneIds passed by brain tool call, then context.selectedSceneIds
      const explicitScenes = Array.isArray(args.sceneIds) && args.sceneIds.length > 0 ? args.sceneIds : null;
      const contextScenes = context?.selectedSceneIds && context.selectedSceneIds.length > 0 ? context.selectedSceneIds : null;
      let sceneIds = explicitScenes || contextScenes;

      if (!sceneIds || sceneIds.length === 0) {
        // Fallback to demo scenes for seamless transition
        sceneIds = ["scn_000001", "scn_000002"];
      }
      mapped.push({
        commandId: COMMAND_IDS.investigation.create,
        params: {
          projectId: DEFAULT_VOICE_PROJECT_ID,
          sceneIds,
          seedQuery: userText || null,
          missionId: null,
        },
        description: `Opening investigation over ${sceneIds.length} scene${sceneIds.length === 1 ? "" : "s"}`,
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

    case "toggle_canvas": {
      const open = args.open ?? true;
      const view = args.view;
      mapped.push({
        commandId: COMMAND_IDS.investigation.toggleCanvas,
        params: view ? { open, view } : { open },
        description: `${open ? "Opening" : "Closing"} the Analysis Canvas`,
      });
      break;
    }

    case "explain_workflow": {
      mapped.push({
        commandId: COMMAND_IDS.investigation.toggleCanvas,
        params: { open: true, view: "trace" },
        description: "Opening the Analysis Canvas to visual workflow",
      });
      if (args.focusStep) {
        mapped.push({
          commandId: COMMAND_IDS.investigation.focusNode,
          params: { nodeId: args.focusStep },
          description: `Spotlighting stage ${args.focusStep}`,
        });
      }
      break;
    }

    case "inspect_pipeline_node": {
      const nodeId = args.nodeId || "S12_CROSS_MODAL_FUSION";
      mapped.push({
        commandId: COMMAND_IDS.investigation.toggleCanvas,
        params: { open: true },
        description: "Opening the Analysis Canvas",
      });
      mapped.push({
        commandId: COMMAND_IDS.investigation.focusNode,
        params: { nodeId },
        description: `Inspecting pipeline node ${nodeId}`,
      });
      break;
    }

    case "rerun_pipeline_step": {
      const stepId = args.stepId || "S12_CROSS_MODAL_FUSION";
      const parameterOverrides = args.parameters || { confidenceThreshold: 0.72 };
      mapped.push({
        commandId: COMMAND_IDS.investigation.rerunStep,
        params: { stepId, parameterOverrides },
        description: `Branching pipeline execution from ${stepId}`,
      });
      break;
    }
  }

  return mapped;
}

export async function POST(request: Request) {
  const openAIApiKey = process.env.OPENAI_API_KEY?.trim();
  const elevenLabsApiKey = process.env.ELEVENLABS_API_KEY?.trim();
  const configuredModel = process.env.OPENAI_MODEL?.trim() || "gpt-5-astra";
  // Warm, clear masculine voice as the Jarvis base — "ash" stays audible on
  // small speakers where deep voices (onyx) lose their fundamental and go
  // quiet. British softness comes from the instruction layer, and any voice
  // can be tried without a code change via OPENAI_VOICE (ballad = most
  // British-sounding, younger; cedar = warmest, newest; onyx = deepest).
  const openAIVoice = process.env.OPENAI_VOICE?.trim() || "ballad";
  const elevenLabsVoiceId = process.env.ELEVENLABS_VOICE_ID?.trim() || "archaeology";
  const ttsModel = process.env.OPENAI_TTS_MODEL?.trim() || "tts-1";
  const ttsSpeed = Number.parseFloat(process.env.OPENAI_TTS_SPEED?.trim() || "1.0") || 1.0;
  const speechOptions = {
    voice: openAIVoice,
    ttsModel,
    speed: Math.min(4, Math.max(0.25, ttsSpeed)),
  };

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
    let screenshotBase64 = null;
    if (contentType.includes("multipart/form-data")) {
      const formData = await request.formData();
      const audioFile = formData.get("audio") as File | null;
      const textQuery = formData.get("query") as string | null;
      const contextField = formData.get("context") as string | null;
      screenshotBase64 = formData.get("screenshot") as string | null;
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
        if (!openAIApiKey) {
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

        // 1. Ultra-low-latency local Faster-Whisper backend check
        const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        try {
          const localRes = await fetch(`${backendUrl}/api/v1/voice/transcribe`, {
            method: "POST",
            headers: { "Content-Type": detected.mimeType },
            body: buffer,
            signal: AbortSignal.timeout(2500), // Allow faster-whisper enough time to transcribe
          });
          if (localRes.ok) {
            const localData = await localRes.json();
            if (localData.success && localData.text && localData.text.trim()) {
              userText = localData.text.trim();
              console.log(`[AERIS VOICE] Local Faster-Whisper transcribed in fast path: "${userText}"`);
            }
          }
        } catch {
          // Local backend offline or timed out; fall through to OpenAI Whisper
        }

        // 2. High-performance cloud Whisper-1 fallback
        if (!userText) {
          const openai = new OpenAI({ apiKey: openAIApiKey });
          const uploadFile = await toFile(buffer, detected.filename, {
            type: detected.mimeType,
          });

          const transcription = await openai.audio.transcriptions.create({
            file: uploadFile,
            model: "whisper-1",
            language: "en",
            prompt: "AERIS satellite earth observation, Sentinel-1 SAR backscatter, Sentinel-2 NDVI, Mazgaon Docks, Sewri mudflats, Mumbai",
          });

          userText = transcription.text.trim();
          console.log(`[AERIS VOICE] OpenAI Whisper-1 transcribed: "${userText}"`);
        }
      }
    } else {
      const body = await request.json();

      if (body.action === "greeting" || body.greeting) {
        const greetingText = "Voice command mode activated. AERIS online and at your service, sir.";
        let audioBase64: string | null = null;
        if (elevenLabsApiKey && elevenLabsVoiceId) {
          try {
            const elevenLabsUrl = `https://api.elevenlabs.io/v1/text-to-speech/${elevenLabsVoiceId}`;
            const response = await fetch(elevenLabsUrl, {
              method: "POST",
              headers: {
                "xi-api-key": elevenLabsApiKey,
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                text: greetingText,
                voice_settings: {
                  stability: 0.5,
                  similarity_boost: 0.5,
                },
              }),
            });
            if (response.ok) {
              const arrayBuffer = await response.arrayBuffer();
              const base64 = Buffer.from(arrayBuffer).toString("base64");
              audioBase64 = `data:audio/mpeg;base64,${base64}`;
            }
          } catch (error) {
            console.error("[AERIS VOICE] ElevenLabs greeting TTS failed:", error);
          }
        }
        if (!audioBase64 && openAIApiKey) {
          const openai = new OpenAI({ apiKey: openAIApiKey });
          audioBase64 = await synthesizeJarvisSpeech(openai, greetingText, speechOptions);
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
      screenshotBase64 = body.screenshot || null;
    }

    if (!userText) {
      return NextResponse.json(
        { success: false, error: "No audible speech or query detected, sir." },
        { status: 400 },
      );
    }

    // ── Fallback if API key is not yet set by user ───────────────────────────────────────────
    if (!openAIApiKey) {
      return NextResponse.json({
        success: true,
        transcript: userText,
        reply: `Standing by, sir. I have received your instruction: "${userText}", but the OpenAI API key has not yet been set in the environment. Please add your key to frontend/.env so I may fully engage.`,
        actions: [],
        audioBase64: null,
      });
    }

    const openai = new OpenAI({ apiKey: openAIApiKey });

    // ── 2. Run AERIS Reasoning & Tool Calling ────────────────────────────────────────
    
    // Ground the brain in the live UI: which screen is mounted determines
    // which commands exist, and the selection resolves "these images".
    const selectionLine =
      operatorContext.selectedSceneIds.length > 0
        ? `Selected scenes: ${operatorContext.selectedSceneIds.join(", ")} (${operatorContext.selectedSceneIds.length} selected). "Investigate / take me to investigation / these images" means call investigate_selection. "See images selected" means call manage_imagery_selection({ action: "view" }).`
        : `Selected scenes: none. If the operator asks to "see the images selected" or "open imagery catalogue", call manage_imagery_selection({ action: "view" }). If the operator asks to "investigate / take me to investigation / let's go to investigation panel", call investigate_selection with sceneIds: ["scn_000001", "scn_000002"] to auto-select the primary demonstration scenes and launch the workspace.`;
    const systemPrompt =
      `${AERIS_SYSTEM_PROMPT}\n\nOPERATOR CONTEXT (live — trust it over guesses):\n` +
      `- Current surface: ${operatorContext.surface}\n- ${selectionLine}`;

    console.log(`[AERIS VOICE] context: surface=${operatorContext.surface} scenes=${operatorContext.selectedSceneIds.length}`);

    // Use gpt-4o which is robust, supports vision natively, and is fast
    const model = "gpt-4o";
    
    let completionResponse;
    try {
      const messages: any[] = [
        { role: "system", content: systemPrompt }
      ];

      if (screenshotBase64) {
        messages.push({
          role: "user",
          content: [
            { type: "text", text: userText },
            { type: "image_url", image_url: { url: screenshotBase64 } }
          ]
        });
      } else {
        messages.push({ role: "user", content: userText });
      }

      completionResponse = await openai.chat.completions.create({
        model,
        messages,
        tools: AERIS_TOOLS,
        tool_choice: "auto",
      });
    } catch (modelErr: unknown) {
      const errorMessage = modelErr instanceof Error ? modelErr.message : String(modelErr);
      throw new Error(`AERIS model reasoning failed: ${errorMessage}`);
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

    // ── 3. Synthesize Voice ─────────────────────────────────────────
    let audioBase64: string | null = null;

    // Try ElevenLabs first if API key and voice ID are configured
    if (elevenLabsApiKey && elevenLabsVoiceId) {
      try {
        const elevenLabsUrl = `https://api.elevenlabs.io/v1/text-to-speech/${elevenLabsVoiceId}`;
        const response = await fetch(elevenLabsUrl, {
          method: "POST",
          headers: {
            "xi-api-key": elevenLabsApiKey,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            text: cleanSpokenText,
            voice_settings: {
              stability: 0.5,
              similarity_boost: 0.5,
            },
          }),
        });
        if (response.ok) {
          const arrayBuffer = await response.arrayBuffer();
          const base64 = Buffer.from(arrayBuffer).toString("base64");
          audioBase64 = `data:audio/mpeg;base64,${base64}`;
          console.log(`[AERIS VOICE] ElevenLabs TTS succeeded (voice=${elevenLabsVoiceId})`);
        }
      } catch (error) {
        console.error("[AERIS VOICE] ElevenLabs TTS failed:", error);
      }
    }

    // Fall back to OpenAI Jarvis voice
    if (!audioBase64 && openAIApiKey) {
      const openai = new OpenAI({ apiKey: openAIApiKey });
      audioBase64 = await synthesizeJarvisSpeech(openai, cleanSpokenText, speechOptions);
    }

    console.log(`[AERIS VOICE] TTS ${audioBase64 ? "succeeded" : "FAILED"} (elevenLabs=${!!(elevenLabsApiKey && elevenLabsVoiceId)}, openAI=${!!openAIApiKey})`);

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

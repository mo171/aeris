// tests/audio/voice-command-contract.test.ts — the permanent guard against voice/bus drift.
//
// what  : Proves every tool call the brain can make resolves to commandIds that
//         exist in COMMAND_IDS, with params shaped like the registry expects.
//         Reads the tool JSON Schemas' own enums, so a newly added enum value is
//         covered automatically — no test update needed when vocabulary grows.
// why   : Voice failures used to be silent contract mismatches (bounds vs lat/lon,
//         mode vs binding, void vs { panel }). If this test is green, an order the
//         brain gives is an order the bus understands.

import { describe, expect, it } from "vitest";
import type { ChatCompletionTool } from "openai/resources/chat/completions";

import { COMMAND_IDS } from "../../lib/constants/commands";
import { AERIS_TOOLS, mapVoiceToolToActions } from "../../app/api/voice/process/route";

function collectCommandIds(node: unknown, into: Set<string>): void {
  if (typeof node === "string") {
    into.add(node);
    return;
  }
  if (node && typeof node === "object") {
    for (const value of Object.values(node)) collectCommandIds(value, into);
  }
}

const KNOWN_IDS = new Set<string>();
collectCommandIds(COMMAND_IDS, KNOWN_IDS);

type FunctionTool = Extract<ChatCompletionTool, { function: unknown }>;

function findTool(name: string): FunctionTool {
  const tool = AERIS_TOOLS.find(
    (candidate): candidate is FunctionTool =>
      "function" in candidate && candidate.function?.name === name,
  );
  if (!tool) throw new Error(`voice tool "${name}" is missing from AERIS_TOOLS`);
  return tool;
}

function enumOf(tool: FunctionTool, property: string): string[] {
  const schema = tool.function.parameters as {
    properties?: Record<string, { enum?: string[] }>;
  };
  const values = schema.properties?.[property]?.enum;
  if (!values) throw new Error(`tool "${tool.function.name}" has no enum for "${property}"`);
  return values;
}

function expectKnownCommands(actions: ReturnType<typeof mapVoiceToolToActions>): void {
  expect(actions.length).toBeGreaterThan(0);
  for (const action of actions) {
    expect(KNOWN_IDS.has(action.commandId), `unknown commandId "${action.commandId}"`).toBe(true);
    expect(action.description.length).toBeGreaterThan(0);
  }
}

describe("voice → command-bus contract", () => {
  it("unknown tool names map to no actions (never a crash, never a hallucinated command)", () => {
    expect(mapVoiceToolToActions("do_anything", {}, "test")).toEqual([]);
  });

  it("every switch_panel value resolves to known commands, shown and hidden", () => {
    for (const panel of enumOf(findTool("switch_panel"), "panel")) {
      for (const visible of [true, false]) {
        expectKnownCommands(mapVoiceToolToActions("switch_panel", { panel, visible }, "test"));
      }
    }
  });

  it("'open the investigation panel' opens the inputs tab in an open left panel", () => {
    const actions = mapVoiceToolToActions("switch_panel", { panel: "inputs" }, "open the investigation panel");
    expect(actions.map((a) => a.commandId)).toEqual([
      COMMAND_IDS.investigation.setLeftTab,
      COMMAND_IDS.interface.toggleDataPanel,
    ]);
    expect(actions[0]?.params).toEqual({ tab: "inputs" });
    expect(actions[1]?.params).toEqual({ open: true });
  });

  it("every navigate_globe location flies to a lat/lon the registry accepts", () => {
    for (const location of enumOf(findTool("navigate_globe"), "location")) {
      const actions = mapVoiceToolToActions("navigate_globe", { location }, "test");
      expectKnownCommands(actions);
      const params = actions[0]?.params as { latitude: number; longitude: number };
      expect(params.latitude).toBeGreaterThanOrEqual(-90);
      expect(params.latitude).toBeLessThanOrEqual(90);
      expect(params.longitude).toBeGreaterThanOrEqual(-180);
      expect(params.longitude).toBeLessThanOrEqual(180);
      expect("bounds" in (actions[0]?.params ?? {})).toBe(false);
    }
  });

  it("every toggle_layer key resolves to known layer commands", () => {
    for (const layerKey of enumOf(findTool("toggle_layer"), "layerKey")) {
      expectKnownCommands(mapVoiceToolToActions("toggle_layer", { layerKey, visible: true }, "test"));
      expectKnownCommands(mapVoiceToolToActions("toggle_layer", { layerKey, visible: true, solo: true }, "test"));
    }
  });

  it("adjust_comparator only emits registry-shaped comparator params", () => {
    const moved = mapVoiceToolToActions("adjust_comparator", { splitPosition: 80 }, "test");
    expectKnownCommands(moved);
    const position = (moved[0]?.params as { position: number }).position;
    expect(position).toBeGreaterThanOrEqual(0);
    expect(position).toBeLessThanOrEqual(1);

    for (const binding of ["temporal", "crossModal"]) {
      const bound = mapVoiceToolToActions("adjust_comparator", { binding }, "test");
      expectKnownCommands(bound);
      expect(bound[0]?.params).toEqual({ binding });
    }
    // The old split/blend/diff vocabulary must never produce a command again.
    expect(mapVoiceToolToActions("adjust_comparator", { mode: "split" }, "test")).toEqual([]);
  });

  it("every run_analysis_operation id resolves to a known run command", () => {
    for (const operationId of enumOf(findTool("run_analysis_operation"), "operationId")) {
      expectKnownCommands(mapVoiceToolToActions("run_analysis_operation", { operationId }, "test"));
    }
  });

  it("every focus_evidence target spotlights without inventing evidence ids", () => {
    for (const target of enumOf(findTool("focus_evidence"), "target")) {
      expectKnownCommands(mapVoiceToolToActions("focus_evidence", { target }, "test"));
    }
  });

  it("reset_view addresses the investigation screen's command", () => {
    const actions = mapVoiceToolToActions("reset_view", {}, "test");
    expectKnownCommands(actions);
    expect(actions[0]?.commandId).toBe(COMMAND_IDS.investigation.resetView);
    // The registry schema accepts the empty object — a void schema would
    // reject every one of these dispatches as invalid-params.
    expect(actions[0]?.params).toEqual({});
  });

  it("investigate_selection opens a workspace over the live selection", () => {
    const context = { surface: "/mission-command", selectedSceneIds: ["sc_1", "sc_2"] };
    const actions = mapVoiceToolToActions(
      "investigate_selection",
      {},
      "take me to investigation over these images",
      context,
    );
    expectKnownCommands(actions);
    expect(actions[0]?.commandId).toBe(COMMAND_IDS.investigation.create);
    expect(actions[0]?.params).toEqual({
      projectId: expect.any(String),
      sceneIds: ["sc_1", "sc_2"],
      seedQuery: "take me to investigation over these images",
      missionId: null,
    });
  });

  it("investigate_selection with nothing selected falls back to demo scenes", () => {
    // If the brain and context fail to provide scenes, the fallback ensures a seamless demo
    const actions = mapVoiceToolToActions(
      "investigate_selection",
      { sceneIds: [] },
      "test",
      { surface: "investigation", selectedSceneIds: [] },
    );
    expect(actions).toHaveLength(1);
    expect(actions[0].params.sceneIds).toEqual(["scn_000001", "scn_000002"]);
  });

  it("every manage_imagery_selection action resolves to known commands", () => {
    for (const action of enumOf(findTool("manage_imagery_selection"), "action")) {
      const args = action === "select" ? { action, sceneIds: ["scn_000001"] } : { action };
      expectKnownCommands(mapVoiceToolToActions("manage_imagery_selection", args, "test"));
    }
  });

  it("toggle_canvas opens and closes the analysis canvas", () => {
    const openActions = mapVoiceToolToActions("toggle_canvas", { open: true }, "open canvas");
    expectKnownCommands(openActions);
    expect(openActions[0]?.commandId).toBe(COMMAND_IDS.investigation.toggleCanvas);
    expect(openActions[0]?.params).toEqual({ open: true });

    const closeActions = mapVoiceToolToActions("toggle_canvas", { open: false }, "close canvas");
    expectKnownCommands(closeActions);
    expect(closeActions[0]?.commandId).toBe(COMMAND_IDS.investigation.toggleCanvas);
    expect(closeActions[0]?.params).toEqual({ open: false });
  });

  it("explain_workflow opens the canvas and optionally spotlights a step", () => {
    const actions = mapVoiceToolToActions("explain_workflow", { focusStep: "S12_CROSS_MODAL_FUSION" }, "explain workflow");
    expectKnownCommands(actions);
    expect(actions[0]?.commandId).toBe(COMMAND_IDS.investigation.toggleCanvas);
    expect(actions[1]?.commandId).toBe(COMMAND_IDS.investigation.focusNode);
    expect(actions[1]?.params).toEqual({ nodeId: "S12_CROSS_MODAL_FUSION" });
  });

  it("inspect_pipeline_node opens the canvas and spotlights the targeted node", () => {
    const actions = mapVoiceToolToActions("inspect_pipeline_node", { nodeId: "S05_PREPROCESS_SAR" }, "inspect node 5");
    expectKnownCommands(actions);
    expect(actions[0]?.commandId).toBe(COMMAND_IDS.investigation.toggleCanvas);
    expect(actions[1]?.commandId).toBe(COMMAND_IDS.investigation.focusNode);
    expect(actions[1]?.params).toEqual({ nodeId: "S05_PREPROCESS_SAR" });
  });

  it("rerun_pipeline_step issues rerunStep command with parameters", () => {
    const actions = mapVoiceToolToActions("rerun_pipeline_step", {
      stepId: "S12_CROSS_MODAL_FUSION",
      parameters: { confidenceThreshold: 0.72 },
    }, "rerun from step 12");
    expectKnownCommands(actions);
    expect(actions[0]?.commandId).toBe(COMMAND_IDS.investigation.rerunStep);
    expect(actions[0]?.params).toEqual({
      stepId: "S12_CROSS_MODAL_FUSION",
      parameterOverrides: { confidenceThreshold: 0.72 },
    });
  });
});

import { afterEach, describe, expect, it } from "vitest";
import { z } from "zod";

import {
  defineCommand,
  registerCommands,
  type CommandDefinition,
} from "../command-bus";

import { dispatchUiCommandEvent } from "./ui-command-bridge";

const unregisterCallbacks: Array<() => void> = [];

afterEach(() => {
  while (unregisterCallbacks.length > 0) {
    unregisterCallbacks.pop()?.();
  }
});

function register<TParams>(command: CommandDefinition<TParams>) {
  unregisterCallbacks.push(registerCommands([defineCommand(command)]));
}

describe("dispatchUiCommandEvent", () => {
  it("dispatches a validated agent command", async () => {
    let opacity = 0;
    register({
      id: "investigation.setLayerOpacity",
      title: "Opacity",
      description: "Set opacity",
      group: "investigation",
      paramsSchema: z.object({ opacity: z.number().min(0).max(1) }),
      handler: ({ opacity: next }) => {
        opacity = next;
      },
    });

    await expect(
      dispatchUiCommandEvent({
        commandId: "investigation.setLayerOpacity",
        params: { opacity: 0.4 },
        reason: "Reveal validated context",
      }),
    ).resolves.toEqual({ status: "completed", commandId: "investigation.setLayerOpacity" });
    expect(opacity).toBe(0.4);
  });

  it("exposes a failed dispatch result to the stream observer", async () => {
    const observedStatuses: string[] = [];

    await dispatchUiCommandEvent(
      {
        commandId: "investigation.unknown",
        params: {},
        reason: "Unknown capability",
      },
      (result) => observedStatuses.push(result.status),
    );

    expect(observedStatuses).toEqual(["not-found"]);
  });

  it("continues after a command is not found", async () => {
    let executed = false;
    registerSuccessfulCommand(() => {
      executed = true;
    });

    await expect(
      dispatchUiCommandEvent({
        commandId: "investigation.unknown",
        params: {},
        reason: "Unknown capability",
      }),
    ).resolves.toMatchObject({ status: "not-found", commandId: "investigation.unknown" });

    await expect(dispatchSuccessfulCommand()).resolves.toMatchObject({ status: "completed" });
    expect(executed).toBe(true);
  });

  it("continues after parameters fail command validation", async () => {
    let opacity = 0;
    register({
      id: "investigation.setLayerOpacity",
      title: "Opacity",
      description: "Set opacity",
      group: "investigation",
      paramsSchema: z.object({ opacity: z.number().min(0).max(1) }),
      handler: ({ opacity: next }) => {
        opacity = next;
      },
    });
    let executed = false;
    registerSuccessfulCommand(() => {
      executed = true;
    });

    await expect(
      dispatchUiCommandEvent({
        commandId: "investigation.setLayerOpacity",
        params: { opacity: 2 },
        reason: "Reveal context",
      }),
    ).resolves.toMatchObject({ status: "invalid-params" });
    expect(opacity).toBe(0);

    await expect(dispatchSuccessfulCommand()).resolves.toMatchObject({ status: "completed" });
    expect(executed).toBe(true);
  });

  it("continues after a disabled command", async () => {
    let executed = false;
    register({
      id: "investigation.disabled",
      title: "Disabled",
      description: "Unavailable command",
      group: "investigation",
      paramsSchema: z.object({}),
      isEnabled: () => false,
      handler: () => {
        throw new Error("disabled commands must not execute");
      },
    });
    registerSuccessfulCommand(() => {
      executed = true;
    });

    await expect(
      dispatchUiCommandEvent({
        commandId: "investigation.disabled",
        params: {},
        reason: "Unavailable capability",
      }),
    ).resolves.toMatchObject({ status: "disabled" });

    await expect(dispatchSuccessfulCommand()).resolves.toMatchObject({ status: "completed" });
    expect(executed).toBe(true);
  });

  it("contains a command availability exception and continues the stream", async () => {
    const expectedError = new Error("availability lookup failed");
    let executed = false;
    register({
      id: "investigation.throwingAvailability",
      title: "Throwing availability",
      description: "Exercises command-boundary containment",
      group: "investigation",
      paramsSchema: z.object({}),
      isEnabled: () => {
        throw expectedError;
      },
      handler: () => {
        throw new Error("unreachable when availability fails");
      },
    });
    registerSuccessfulCommand(() => {
      executed = true;
    });

    await expect(
      dispatchUiCommandEvent({
        commandId: "investigation.throwingAvailability",
        params: {},
        reason: "Capability lookup",
      }),
    ).resolves.toEqual({
      status: "failed",
      commandId: "investigation.throwingAvailability",
      error: expectedError,
    });

    await expect(dispatchSuccessfulCommand()).resolves.toMatchObject({ status: "completed" });
    expect(executed).toBe(true);
  });

  it("continues after a command handler fails", async () => {
    let executed = false;
    register({
      id: "investigation.failing",
      title: "Failing",
      description: "Handler failure",
      group: "investigation",
      paramsSchema: z.object({}),
      handler: () => {
        throw new Error("handler failed");
      },
    });
    registerSuccessfulCommand(() => {
      executed = true;
    });

    await expect(
      dispatchUiCommandEvent({
        commandId: "investigation.failing",
        params: {},
        reason: "Exercise failure isolation",
      }),
    ).resolves.toMatchObject({ status: "failed" });

    await expect(dispatchSuccessfulCommand()).resolves.toMatchObject({ status: "completed" });
    expect(executed).toBe(true);
  });
});

function registerSuccessfulCommand(handler: () => void) {
  register({
    id: "investigation.afterFailure",
    title: "Subsequent command",
    description: "Confirms stream processing continues",
    group: "investigation",
    paramsSchema: z.object({}),
    handler,
  });
}

function dispatchSuccessfulCommand() {
  return dispatchUiCommandEvent({
    commandId: "investigation.afterFailure",
    params: {},
    reason: "Continue the stream",
  });
}

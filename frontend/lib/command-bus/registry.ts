// lib/command-bus/registry.ts — the single registry of everything the AERIS interface can be told to do.
//
// what  : Stores command definitions, validates parameters on dispatch, and exposes the registry both to
//         React (palette, shortcuts) and to plain callers (the future agent/voice bridge).
// where : Written to by feature command hooks via useRegisterCommands; read by CommandPalette,
//         useCommandShortcuts and — later — the agent tool bridge through listCommandDescriptors().
// how   : A Zustand store backs the map so React consumers re-render on registration changes, while
//         dispatchCommand() reads the store imperatively and therefore works outside React entirely.
//         Every dispatch is Zod-validated: an agent cannot drive the UI into an invalid state, and a
//         malformed voice intent fails as data rather than as a runtime crash.

import { create } from "zustand";
import { z } from "zod";

import type {
  CommandDefinition,
  CommandDescriptor,
  CommandDispatchResult,
  RegisteredCommand,
} from "./types";

interface CommandRegistryState {
  commands: Record<string, RegisteredCommand>;
  setCommands: (next: Record<string, RegisteredCommand>) => void;
}

const useCommandRegistryStore = create<CommandRegistryState>((set) => ({
  commands: {},
  setCommands: (next) => set({ commands: next }),
}));

/**
 * Widens a typed command definition into a storable one. The two casts here are the only place in the
 * codebase where command parameter typing is erased, and they are safe because the stored handler is only
 * ever reached through paramsSchema.parse().
 */
export function defineCommand<TParams>(definition: CommandDefinition<TParams>): RegisteredCommand {
  return {
    ...definition,
    paramsSchema: definition.paramsSchema as unknown as CommandDefinition<unknown>["paramsSchema"],
    handler: (params: unknown) => definition.handler(params as TParams),
  };
}

/**
 * Registers a batch of commands and returns the matching unregister function.
 * Batching matters: a feature mounting registers all of its commands in one store write.
 */
export function registerCommands(commands: readonly RegisteredCommand[]): () => void {
  const { commands: existing, setCommands } = useCommandRegistryStore.getState();
  const next = { ...existing };
  for (const command of commands) {
    next[command.id] = command;
  }
  setCommands(next);

  return () => {
    const { commands: current, setCommands: set } = useCommandRegistryStore.getState();
    const remaining = { ...current };
    for (const command of commands) {
      if (remaining[command.id] === command) {
        delete remaining[command.id];
      }
    }
    set(remaining);
  };
}

/** Imperative snapshot of the registry. Safe to call outside React. */
export function getRegisteredCommands(): RegisteredCommand[] {
  return Object.values(useCommandRegistryStore.getState().commands);
}

/** Reactive registry access for React consumers. */
export function useRegisteredCommands(): RegisteredCommand[] {
  const commands = useCommandRegistryStore((state) => state.commands);
  return Object.values(commands);
}

/**
 * Executes a command by id after validating its parameters.
 * Never throws — callers get a discriminated result so UI and agent can both react without try/catch.
 */
export async function dispatchCommand(
  commandId: string,
  rawParameters?: unknown,
): Promise<CommandDispatchResult> {
  const command = useCommandRegistryStore.getState().commands[commandId];

  if (!command) {
    return { status: "not-found", commandId };
  }

  if (command.isEnabled && !command.isEnabled()) {
    return { status: "disabled", commandId };
  }

  const parsed = command.paramsSchema.safeParse(rawParameters);
  if (!parsed.success) {
    return {
      status: "invalid-params",
      commandId,
      message: parsed.error.issues.map((issue) => issue.message).join("; "),
    };
  }

  try {
    await command.handler(parsed.data);
    return { status: "completed", commandId };
  } catch (error) {
    return { status: "failed", commandId, error };
  }
}

/**
 * Serialises the registry into tool-style descriptors.
 * This is the seam the agentic layer plugs into: no UI rewiring will be needed, because every
 * interactive affordance in the app already routes through a command that appears in this list.
 */
export function listCommandDescriptors(): CommandDescriptor[] {
  return getRegisteredCommands().map((command) => ({
    id: command.id,
    title: command.title,
    description: command.description,
    group: command.group,
    parameters: toJsonSchemaSafely(command.paramsSchema),
  }));
}

function toJsonSchemaSafely(schema: RegisteredCommand["paramsSchema"]): unknown {
  try {
    return z.toJSONSchema(schema, { io: "input" });
  } catch {
    // A schema that cannot be represented as JSON Schema still dispatches fine; it just is not
    // advertised to the agent with a parameter shape.
    return null;
  }
}

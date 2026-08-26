// lib/command-bus/types.ts — the contract every UI-invocable action satisfies.
//
// what  : Types describing a command: its identity, human copy, agent-readable description, parameter
//         schema and handler, plus the discriminated result of dispatching one.
// where : Implemented by feature command hooks, consumed by the registry, the command palette, the
//         keyboard-shortcut layer and (in a later phase) the agent/voice bridge.
// how   : Commands are generic over their parameter type at definition time, then widened to `unknown`
//         for storage so heterogeneous commands can share one registry without `any`. defineCommand()
//         in registry.ts performs that widening in exactly one place.

import type { LucideIcon } from "lucide-react";
import type { ZodType } from "zod";

import type { CommandGroup } from "@/lib/constants/commands";

export interface CommandDefinition<TParams> {
  /** Stable namespaced identifier from lib/constants/commands.ts. */
  id: string;
  /** Short label shown in the command palette. */
  title: string;
  /**
   * Plain-language description of what running this command does. This is written for the agent as much
   * as for the operator — it becomes the tool description when the agent layer introspects the registry.
   */
  description: string;
  group: CommandGroup;
  /** Extra terms the palette should match on. */
  keywords?: readonly string[];
  icon?: LucideIcon;
  /** Key combination, lower-case, e.g. ["ctrl", "k"] or ["shift", "?"]. */
  shortcut?: readonly string[];
  /** Zod schema for the parameters. Use z.void() for commands that take none. */
  paramsSchema: ZodType<TParams>;
  handler: (params: TParams) => void | Promise<void>;
  /** Commands hidden from the palette are still dispatchable by the agent. Defaults to visible. */
  isPaletteVisible?: boolean;
  /** Evaluated at render time by the palette to dim unavailable commands. Defaults to enabled. */
  isEnabled?: () => boolean;
}

/** A command as stored in the registry: parameters erased to `unknown`, validated at dispatch time. */
export type RegisteredCommand = CommandDefinition<unknown>;

export type CommandDispatchResult =
  | { status: "completed"; commandId: string }
  | { status: "not-found"; commandId: string }
  | { status: "disabled"; commandId: string }
  | { status: "invalid-params"; commandId: string; message: string }
  | { status: "failed"; commandId: string; error: unknown };

/**
 * Agent-facing description of a command. Shaped deliberately like a tool definition so the future
 * agent layer can hand the registry straight to a model without a translation step.
 */
export interface CommandDescriptor {
  id: string;
  title: string;
  description: string;
  group: CommandGroup;
  parameters: unknown;
}

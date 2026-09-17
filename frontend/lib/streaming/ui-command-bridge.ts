import { dispatchCommand } from "../command-bus";
import type { CommandDispatchResult } from "../command-bus";

export interface UiCommandEvent {
  commandId: string;
  params: Record<string, unknown>;
  reason: string;
}

export type UiCommandDispatchObserver = (result: CommandDispatchResult) => void;

/**
 * Preserves the command bus as the only execution and parameter-validation boundary for agent proposals.
 */
export async function dispatchUiCommandEvent(
  event: UiCommandEvent,
  observeResult?: UiCommandDispatchObserver,
): Promise<CommandDispatchResult> {
  let result: CommandDispatchResult;
  try {
    result = await dispatchCommand(event.commandId, event.params);
  } catch (error) {
    result = { status: "failed", commandId: event.commandId, error };
  }
  observeResult?.(result);
  return result;
}

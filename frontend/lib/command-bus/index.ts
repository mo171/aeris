// lib/command-bus/index.ts — public surface of the command bus. Import from here, never from internals.
//
// what  : Re-exports the registry API, the React binding and the command types.
// where : Imported by feature command hooks, the command palette, the shortcut layer, and eventually the
//         agent/voice bridge.
// how   : A single entry point keeps the internal file layout free to change without a codebase sweep.

export {
  defineCommand,
  dispatchCommand,
  getRegisteredCommands,
  listCommandDescriptors,
  registerCommands,
  useRegisteredCommands,
} from "./registry";
export { useRegisterCommands } from "./use-register-commands";
export type {
  CommandDefinition,
  CommandDescriptor,
  CommandDispatchResult,
  RegisteredCommand,
} from "./types";

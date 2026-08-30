// features/investigation/components/inputsPanel/ToolboxPanel.tsx — everything this workspace can actually do.
//
// what  : A catalogue of the operations available on the open investigation, grouped, searchable, and
//         runnable in one click for the ones that need no arguments.
// where : The second tab of the left panel in InvestigationScreen, beside Inputs.
// how   : The workspace could do around thirty things and advertised none of them. An operator saw a
//         scene, a question box and an answer; the rest was reachable only by opening the command palette
//         and guessing a search term. Capability that cannot be found is capability that does not exist.
//
//         Every row here is READ FROM THE COMMAND REGISTRY. Nothing is listed by hand, so this panel
//         cannot drift from what the application actually supports: registering a command makes it appear,
//         removing one makes it vanish, and the description shown to the operator is the same string the
//         agent layer receives as a tool description. A hand-maintained menu would have been wrong within
//         a week.
//
//         The ANALYSIS section at the top is the other half, and the more important one: named operations
//         — change detection, object detection, segmentation, the spectral indices, SAR — that the
//         operator can run without phrasing a question. Free text stays the primary interface, but an
//         analyst who already knows they want NDVI should not have to compose a sentence, and a newcomer
//         cannot ask for a capability they have no way of knowing exists.
//
//         Operations that cannot run are shown with the REASON, never hidden. "Needs a radar scene"
//         teaches the operator something about the analysis; a missing row teaches them nothing and a
//         greyed one with no explanation reads as a broken button.
//
//         The OVERLAY BROWSER at the bottom completes the same argument for products. Operations say what
//         the workspace can DO; overlays say what it can SHOW, which is a different question an operator
//         cannot otherwise answer — the layer stack only ever lists what a run happened to produce.
//
//         A LENS ROW IS A TOGGLE, NOT A BUTTON. Cross-modal agreement re-reads evidence that already
//         exists rather than dispatching a model, so it presses in and stays pressed while it is open.
//         Rendering it as a one-shot Play control would promise a run that never happens and give the
//         operator no way to see, from here, that the reading is currently on.
//
//         Operations that need arguments are shown but not run from here. A list cannot collect a layer id
//         or a date, and a button that silently guesses one is worse than a button that explains it needs
//         the scene. Those rows say where the argument comes from instead — which is also the honest
//         answer to "can the agent do this", since the agent supplies exactly what the row is missing.

"use client";

import { Eye, Play, Sparkles, Terminal } from "lucide-react";
import { useMemo, useState } from "react";

import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { Input } from "@/components/ui/input";
import { KeyboardHint } from "@/components/sharedUI/dumbComponent/KeyboardHint";
import { dispatchCommand, useRegisteredCommands } from "@/lib/command-bus";
import {
  ANALYSIS_OPERATIONS,
  REQUIREMENT_COPY,
  type AnalysisRequirement,
} from "@/lib/constants/analysis-operations";
import { COMMAND_GROUP_LABEL, type CommandGroup } from "@/lib/constants/commands";
import { getPipelineStage } from "@/lib/constants/pipeline-stages";
import { cn } from "@/lib/utils";

import { OverlayBrowser } from "./OverlayBrowser";

/** What the open investigation can currently satisfy, so each operation can say what it is waiting for. */
export interface AnalysisReadiness {
  pair: boolean;
  optical: boolean;
  sar: boolean;
  evidence: boolean;
  /** What the next run will be scoped to, named for the operator. */
  scopeLabel: string;
}

/**
 * Which groups belong on this surface, in the order an investigation actually uses them.
 *
 * Navigation and interface commands are deliberately absent: they are how you get around the application,
 * not things you do to an investigation, and listing them would bury the six operations that matter.
 */
const TOOLBOX_GROUPS: readonly CommandGroup[] = ["investigation", "assistant", "imagery"];

interface ToolboxPanelProps {
  readiness: AnalysisReadiness;
  onRunOperation: (operationId: string) => void;
  /** Catalogue keys of the overlays currently drawn, so the browser can mark them. */
  activeOverlayIds: readonly string[];
  /** Ids of the lens operations currently open, so their rows read as pressed rather than as buttons. */
  activeLensIds: readonly string[];
}

export function ToolboxPanel({
  readiness,
  onRunOperation,
  activeOverlayIds,
  activeLensIds,
}: ToolboxPanelProps) {
  const commands = useRegisteredCommands();
  const [query, setQuery] = useState("");

  const operations = useMemo(() => {
    const search = query.trim().toLowerCase();
    return ANALYSIS_OPERATIONS.filter((operation) => {
      if (!search) {
        return true;
      }
      return `${operation.label} ${operation.description}`.toLowerCase().includes(search);
    }).map((operation) => {
      const unmet = operation.requires.filter(
        (requirement) => !readiness[requirement as AnalysisRequirement],
      );
      return { operation, unmet };
    });
  }, [query, readiness]);

  const grouped = useMemo(() => {
    const search = query.trim().toLowerCase();

    const matches = commands
      .filter((command) => TOOLBOX_GROUPS.includes(command.group))
      .filter((command) => {
        if (!search) {
          return true;
        }
        const haystack = [command.title, command.description, ...(command.keywords ?? [])]
          .join(" ")
          .toLowerCase();
        return haystack.includes(search);
      });

    return TOOLBOX_GROUPS.map((group) => ({
      group,
      commands: matches.filter((command) => command.group === group),
    })).filter((section) => section.commands.length > 0);
  }, [commands, query]);

  const total = commands.filter((command) => TOOLBOX_GROUPS.includes(command.group)).length;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <SectionHeader
        title="Toolbox"
        trailing={
          <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
            {ANALYSIS_OPERATIONS.length} + {total}
          </span>
        }
      />

      <Input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Filter operations"
        aria-label="Filter operations"
        className="h-7 shrink-0 text-xs"
      />

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-0.5">
        {operations.length > 0 ? (
          <section className="flex flex-col gap-1">
            <h3 className="aeris-technical px-1">
              Analysis · scoped to {readiness.scopeLabel}
            </h3>

            {operations.map(({ operation, unmet }) => {
              const isRunnable = unmet.length === 0;
              const stage = getPipelineStage(operation.stageCode);
              const isLens = operation.kind === "lens";
              const isLensOpen = isLens && activeLensIds.includes(operation.id);
              const ActionIcon = isLens ? Eye : Play;

              return (
                <button
                  key={operation.id}
                  type="button"
                  disabled={!isRunnable}
                  // Only a lens has an on/off state to announce. A run happens and is over.
                  aria-pressed={isLens ? isLensOpen : undefined}
                  onClick={() => onRunOperation(operation.id)}
                  title={operation.description}
                  className={cn(
                    "group flex w-full items-start gap-2 rounded-md border px-2 py-1.5 text-left transition-colors duration-fast",
                    isLensOpen
                      ? "border-aeris-teal/60 bg-aeris-teal/15"
                      : isRunnable
                        ? "border-aeris-teal/25 bg-aeris-teal/5 hover:border-aeris-teal/55 hover:bg-aeris-teal/10"
                        : "cursor-default border-border-soft/60 bg-transparent",
                  )}
                >
                  <ActionIcon
                    className={cn(
                      "mt-0.5 size-3.5 shrink-0",
                      isRunnable
                        ? "text-aeris-teal"
                        : "text-muted-foreground/35",
                    )}
                    aria-hidden="true"
                  />

                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline gap-1.5">
                      <span
                        className={cn(
                          "truncate text-xs",
                          isRunnable ? "text-foreground" : "text-muted-foreground",
                        )}
                      >
                        {operation.label}
                      </span>
                      <span className="shrink-0 font-mono text-[9px] text-muted-foreground/50">
                        {isLensOpen ? "open · " : null}
                        {operation.stageCode} · {stage.label}
                      </span>
                    </span>
                    <span className="mt-0.5 block text-[10px] leading-relaxed text-muted-foreground/70">
                      {operation.description}
                    </span>
                    {unmet.map((requirement) => (
                      <span
                        key={requirement}
                        className="mt-0.5 block font-mono text-[9px] leading-relaxed tracking-wide text-aeris-amber/80 uppercase"
                      >
                        {REQUIREMENT_COPY[requirement as AnalysisRequirement]}
                      </span>
                    ))}
                  </span>
                </button>
              );
            })}
          </section>
        ) : null}

        {grouped.length === 0 && operations.length === 0 ? (
          <p className="px-1 py-4 text-center text-xs text-muted-foreground">
            No operation matches “{query}”.
          </p>
        ) : null}

        {grouped.map((section) => (
          <section key={section.group} className="flex flex-col gap-1">
            <h3 className="aeris-technical px-1">{COMMAND_GROUP_LABEL[section.group]}</h3>

            {section.commands.map((command) => {
              // z.void() is how a command declares it takes nothing, and that is exactly the set that can
              // be run straight from a list.
              const isDirectlyRunnable = command.paramsSchema.safeParse(undefined).success;
              const Icon = command.icon ?? Terminal;

              return (
                <button
                  key={command.id}
                  type="button"
                  disabled={!isDirectlyRunnable}
                  onClick={() => void dispatchCommand(command.id)}
                  title={command.description}
                  className={cn(
                    "group flex w-full items-start gap-2 rounded-md border px-2 py-1.5 text-left transition-colors duration-fast",
                    isDirectlyRunnable
                      ? "border-border-soft bg-surface-2/40 hover:border-aeris-teal/40 hover:bg-aeris-teal/5"
                      : "cursor-default border-transparent bg-transparent",
                  )}
                >
                  <Icon
                    className={cn(
                      "mt-0.5 size-3.5 shrink-0",
                      isDirectlyRunnable
                        ? "text-muted-foreground group-hover:text-aeris-teal"
                        : "text-muted-foreground/40",
                    )}
                    aria-hidden="true"
                  />

                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <span
                        className={cn(
                          "truncate text-xs",
                          isDirectlyRunnable ? "text-foreground" : "text-muted-foreground",
                        )}
                      >
                        {command.title}
                      </span>
                      {command.shortcut ? (
                        <KeyboardHint keys={command.shortcut} className="shrink-0" />
                      ) : null}
                    </span>
                    <span className="mt-0.5 block text-[10px] leading-relaxed text-muted-foreground/70">
                      {command.description}
                    </span>
                    {!isDirectlyRunnable ? (
                      <span className="mt-0.5 flex items-center gap-1 font-mono text-[9px] tracking-wide text-muted-foreground/50 uppercase">
                        <Sparkles className="size-2.5" aria-hidden="true" />
                        Needs a target — run it from the scene, or ask AERIS
                      </span>
                    ) : null}
                  </span>
                </button>
              );
            })}
          </section>
        ))}
        <OverlayBrowser activeOverlayIds={activeOverlayIds} query={query} />
      </div>
    </div>
  );
}

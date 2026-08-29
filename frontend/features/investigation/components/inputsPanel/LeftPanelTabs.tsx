// features/investigation/components/inputsPanel/LeftPanelTabs.tsx — what went in, and what can be done to it.
//
// what  : Two tabs over the left zone: the investigation's inputs and evidence, and the toolbox of
//         operations available on it.
// where : Rendered inside the left PanelContainer of InvestigationScreen.
// how   : A tab rather than a fifth section in the inputs list, because the two answer different questions
//         and are consulted at different moments. Inputs are what you check while reading an answer;
//         the toolbox is what you reach for when deciding what to do next. Stacking them in one scroll
//         would mean the capability list — the thing an operator most needs when they do not yet know what
//         the system can do — sits below four sections they have to scroll past.
//
//         Two tabs, not more. The panel is narrow and every extra tab costs a word of the label; a third
//         would push all three to abbreviations.

"use client";

import { Layers, Wrench } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";

import { InputsPanel } from "./InputsPanel";
import { ToolboxPanel, type AnalysisReadiness } from "./ToolboxPanel";

type LeftPanelTab = "inputs" | "toolbox";

const TABS: readonly { id: LeftPanelTab; label: string; icon: typeof Layers }[] = [
  { id: "inputs", label: "Inputs", icon: Layers },
  { id: "toolbox", label: "Toolbox", icon: Wrench },
];

interface LeftPanelTabsProps extends React.ComponentProps<typeof InputsPanel> {
  readiness: AnalysisReadiness;
  onRunOperation: (operationId: string) => void;
  activeOverlayIds: readonly string[];
}

export function LeftPanelTabs({
  readiness,
  onRunOperation,
  activeOverlayIds,
  ...inputsProps
}: LeftPanelTabsProps) {
  const [tab, setTab] = useState<LeftPanelTab>("inputs");

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div
        role="tablist"
        aria-label="Left panel"
        className="flex shrink-0 items-center gap-1 rounded-md border border-border-soft bg-surface-2/40 p-0.5"
      >
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-sm px-2 py-1 font-mono text-[10px] tracking-wide uppercase transition-colors duration-fast focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              tab === id
                ? "bg-aeris-teal/10 text-aeris-teal"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="size-3" aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>

      {/*
        Both trees stay mounted and the inactive one is hidden, not unmounted. The inputs panel holds
        section collapse state and scroll position that an operator would otherwise lose every time they
        glanced at the toolbox.
      */}
      <div className={cn("min-h-0 flex-1", tab === "inputs" ? "flex" : "hidden")} role="tabpanel">
        <InputsPanel {...inputsProps} />
      </div>
      <div className={cn("min-h-0 flex-1", tab === "toolbox" ? "flex" : "hidden")} role="tabpanel">
        <ToolboxPanel
          readiness={readiness}
          onRunOperation={onRunOperation}
          activeOverlayIds={activeOverlayIds}
        />
      </div>
    </div>
  );
}

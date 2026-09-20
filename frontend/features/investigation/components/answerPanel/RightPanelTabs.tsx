"use client";

import { useState } from "react";
import { ListFilter, MessageSquare, Microscope } from "lucide-react";
import { cn } from "@/lib/utils";

import { AnswerPanel } from "./AnswerPanel";
import { EvidenceTab } from "./EvidenceTab";
import { ChatTab } from "./ChatTab";
import type { AnalysisPlan, AnalysisRun } from "../../types/analysis.types";
import type { Claim, EvidenceItem } from "../../types/evidence.types";
import type { InvestigationEvent } from "../../types/history.types";

type RightPanelTab = "analysis" | "evidence" | "chat";

interface RightPanelTabsProps {
  verdictSection?: React.ReactNode;
  runs: AnalysisRun[];
  isRunning: boolean;
  claimsById: Record<string, Claim>;
  evidenceById: Record<string, EvidenceItem>;
  activePlan: AnalysisPlan | null;
  onAsk: (query: string) => void;
  onStop: () => void;
  onInvestigate: (claimId: string) => void;
  onFocusEvidence: (claim: Claim) => void;
  onTogglePlanStep: (stepId: string) => void;
  onExecutePlan: () => void;
  onDismissPlan: () => void;
  history?: InvestigationEvent[];
  onInspectStep?: (stepId: string) => void;
  onFocusLayer?: (layerId: string) => void;
}

export function RightPanelTabs({
  verdictSection,
  runs,
  isRunning,
  claimsById,
  evidenceById,
  activePlan,
  onAsk,
  onStop,
  onInvestigate,
  onFocusEvidence,
  onTogglePlanStep,
  onExecutePlan,
  onDismissPlan,
  history,
  onInspectStep,
  onFocusLayer,
}: RightPanelTabsProps) {
  const [activeTab, setActiveTab] = useState<RightPanelTab>("analysis");
  const currentRun = runs.at(-1) ?? null;

  return (
    <div className="flex h-full flex-col bg-surface-1/50 backdrop-blur-md">
      {/* Tab Bar */}
      <div className="flex shrink-0 items-center gap-1 border-b border-border-soft p-1">
        <button
          type="button"
          onClick={() => setActiveTab("analysis")}
          className={cn(
            "flex min-w-0 flex-1 items-center justify-center gap-1.5 rounded-sm py-1.5 transition-colors",
            activeTab === "analysis"
              ? "bg-surface-2/60 text-foreground shadow-sm"
              : "text-muted-foreground hover:bg-surface-2/30 hover:text-foreground",
          )}
        >
          <Microscope className="size-3.5 shrink-0" />
          <span className="truncate text-[10px] font-medium tracking-wide uppercase">Analysis</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("evidence")}
          className={cn(
            "flex min-w-0 flex-1 items-center justify-center gap-1.5 rounded-sm py-1.5 transition-colors",
            activeTab === "evidence"
              ? "bg-surface-2/60 text-foreground shadow-sm"
              : "text-muted-foreground hover:bg-surface-2/30 hover:text-foreground",
          )}
        >
          <ListFilter className="size-3.5 shrink-0" />
          <span className="truncate text-[10px] font-medium tracking-wide uppercase">Evidence</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("chat")}
          className={cn(
            "flex min-w-0 flex-1 items-center justify-center gap-1.5 rounded-sm py-1.5 transition-colors",
            activeTab === "chat"
              ? "bg-surface-2/60 text-foreground shadow-sm"
              : "text-muted-foreground hover:bg-surface-2/30 hover:text-foreground",
          )}
        >
          <MessageSquare className="size-3.5 shrink-0" />
          <span className="truncate text-[10px] font-medium tracking-wide uppercase">Chat</span>
        </button>
      </div>

      {/* Tab Content */}
      <div className="min-h-0 flex-1 overflow-hidden">
        {activeTab === "analysis" ? (
          <AnswerPanel
            verdictSection={verdictSection}
            runs={runs}
            isRunning={isRunning}
            claimsById={claimsById}
            evidenceById={evidenceById}
            activePlan={activePlan}
            onAsk={onAsk}
            onStop={onStop}
            onInvestigate={onInvestigate}
            onFocusEvidence={onFocusEvidence}
            onTogglePlanStep={onTogglePlanStep}
            onExecutePlan={onExecutePlan}
            onDismissPlan={onDismissPlan}
          />
        ) : activeTab === "chat" ? (
          <ChatTab
            runs={runs}
            isRunning={isRunning}
            claimsById={claimsById}
            evidenceById={evidenceById}
            onAsk={onAsk}
            onStop={onStop}
            onFocusEvidence={onFocusEvidence}
            history={history}
          />
        ) : (
          <div className="h-full overflow-y-auto p-3">
            <EvidenceTab
              currentRun={currentRun}
              claimsById={claimsById}
              evidenceById={evidenceById}
              onFocusEvidence={onFocusEvidence}
              onInspectStep={onInspectStep}
              onFocusLayer={onFocusLayer}
            />
          </div>
        )}
      </div>
    </div>
  );
}

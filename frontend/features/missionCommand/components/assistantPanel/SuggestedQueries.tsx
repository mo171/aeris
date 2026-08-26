// features/missionCommand/components/assistantPanel/SuggestedQueries.tsx — starting points for an operator.
//
// what  : Renders the backend-supplied suggested questions as one-click prompts, tagged by analysis pillar.
// where : Shown in the assistant panel when the transcript is empty.
// how   : Suggestions come from the API rather than a hardcoded list, because which questions are worth
//         asking depends on what imagery the operator actually holds — that logic belongs on the server
//         where the catalogue lives. The pillar tag is shown so the operator learns the system's three
//         analysis modes by using it, rather than by reading documentation.

"use client";

import type { AssistantSuggestion } from "../../types/assistant.types";
import { Chip, type ChipTone } from "@/components/sharedUI/dumbComponent/Chip";

const PILLAR_LABEL: Record<AssistantSuggestion["pillar"], string> = {
  "single-image": "Single image",
  temporal: "Temporal",
  "cross-modal": "Cross-modal",
};

const PILLAR_TONE: Record<AssistantSuggestion["pillar"], ChipTone> = {
  "single-image": "teal",
  temporal: "amber",
  "cross-modal": "blue",
};

interface SuggestedQueriesProps {
  suggestions: readonly AssistantSuggestion[];
  onSelect: (prompt: string) => void;
}

export function SuggestedQueries({ suggestions, onSelect }: SuggestedQueriesProps) {
  if (suggestions.length === 0) {
    return null;
  }

  return (
    <div className="px-3 pb-2">
      <p className="aeris-technical mb-1.5">Try asking</p>
      <ul className="flex flex-col gap-1.5">
        {suggestions.map((suggestion) => (
          <li key={suggestion.id}>
            <button
              type="button"
              onClick={() => onSelect(suggestion.prompt)}
              className="w-full rounded-md border border-border-soft bg-surface-2/40 px-2.5 py-1.5 text-left transition-colors duration-fast hover:border-aeris-teal/40 hover:bg-aeris-teal/[0.05] focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              <span className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-[11px] text-foreground">
                  {suggestion.label}
                </span>
                <Chip tone={PILLAR_TONE[suggestion.pillar]}>{PILLAR_LABEL[suggestion.pillar]}</Chip>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// features/crossModal/components/AgreementSection.tsx — the verdict and the ledger, above the answers.
//
// what  : The fusion verdict (or the explicit refusal to state one) with the agreement ledger beneath it,
//         collapsible, as a single block for the workspace's right column.
// where : Passed to AnswerPanel as `verdictSection` by InvestigationScreen while the lens is open.
// how   : Composed here so AnswerPanel stays ignorant of cross-modal, the mirror of what SensorsSection
//         does on the left.
//
//         IT SITS ABOVE THE RUNS, NOT INSTEAD OF THEM. A verdict is a standing fact about the evidence; a
//         run is an answer to a question somebody asked. Both belong on screen, and having them together
//         is the entire reason this reading lives inside the workspace: an operator can read "the sensors
//         disagree here", then ask about it in the same column, and the answer lands directly underneath.
//
//         THE LEDGER COLLAPSES, THE VERDICT DOES NOT. The verdict is one short block and is the thing the
//         operator will quote; the ledger grows with the number of findings and would otherwise push the
//         composer off the bottom of a narrow panel. Conflict rows sort first and the ledger never
//         re-sorts them, so collapsing hides agreement before it hides anything that needs reading.

"use client";

import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import type { AgreementState } from "@/lib/constants/cross-modal";

import type { AgreementRow, CrossModalResult } from "../types/cross-modal.types";
import { AgreementLedger } from "./AgreementLedger";
import { FusionVerdictCard } from "./FusionVerdictCard";

interface AgreementSectionProps {
  result: CrossModalResult | undefined;
  isLoading: boolean;
  counts: Readonly<Record<AgreementState, number>>;
  rows: readonly AgreementRow[];
  selectedRowId: string | null;
  onSelectRow: (rowId: string | null) => void;
  isExpanded: boolean;
  onToggleExpanded: () => void;
  /** Asks the workspace's own assistant about one row. Only possible now the reading lives in-place. */
  onAskAboutRow: (row: AgreementRow) => void;
  /** Frames the geometry both sensors contributed to a row. */
  onFocusRow: (row: AgreementRow) => void;
}

export function AgreementSection({
  result,
  isLoading,
  counts,
  rows,
  selectedRowId,
  onSelectRow,
  isExpanded,
  onToggleExpanded,
  onAskAboutRow,
  onFocusRow,
}: AgreementSectionProps) {
  if (!result) {
    return (
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        {isLoading ? "Reading both sensors…" : "No cross-modal result for this area of interest."}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-aeris-teal/25 bg-aeris-teal/5 p-2">
      <FusionVerdictCard
        verdict={result.verdict}
        advisory={result.advisory}
        counts={counts}
      />

      <div className="flex flex-col">
        <SectionHeader
          title="Agreement"
          isExpanded={isExpanded}
          onToggle={onToggleExpanded}
          className="px-0"
          trailing={
            <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
              {rows.length}
            </span>
          }
        />

        {isExpanded ? (
          <div className="max-h-[38vh] overflow-y-auto">
            <AgreementLedger
              rows={rows}
              selectedRowId={selectedRowId}
              onSelectRow={onSelectRow}
              onAskAboutRow={onAskAboutRow}
              onFocusRow={onFocusRow}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

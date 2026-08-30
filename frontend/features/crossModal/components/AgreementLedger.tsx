// features/crossModal/components/AgreementLedger.tsx — where the two sensors agree, and where they don't.
//
// what  : One row per candidate finding, tagged corroborated / optical-only / radar-only / conflict, each
//         expandable into the physical reason and the two sensors' confidences side by side.
// where : The Lab's right column, beneath the fusion verdict.
// how   : This is the instrument the page exists to provide. "Dual evidence" is the requirement; the
//         ledger is how an analyst actually reads it — by scanning for the rows that need attention
//         rather than by comparing two lists of findings by eye.
//
//         CONFLICT LEADS, ALWAYS. Rows arrive sorted worst-first and the component never re-sorts them
//         into anything friendlier. Every other state can be scanned; a conflict has to be read, and
//         burying it under agreement would be the interface quietly doing what the fusion policy forbids
//         the model to do.
//
//         THE REASON IS THE ROW. A state alone — "optical only" — is a label the operator still has to
//         interpret, and interpreting it requires knowing whether radar was blind there. The classifier
//         already resolved that, so the row carries the physical explanation rather than making the
//         operator go and find the mask themselves.
//
//         Confidences are shown per sensor and never combined. There is no cell on this page containing
//         an averaged number, because averaging is the exact operation late fusion was chosen to avoid.
//
//         EVERY ROW CAN BE ASKED ABOUT. Naming a conflict and then offering nothing to do about it is
//         where this ledger used to stop — it lived on a surface with no assistant and no drawing tools,
//         so "resolve with a third observation" was advice the operator had to leave the page to act on.
//         Inside the workspace the same row can hand its question straight to the composer and frame the
//         ground it is about, which is the whole argument for the reading living here.

"use client";

import { ChevronDown, ChevronRight, Crosshair, MessageSquareText } from "lucide-react";

import { Button } from "@/components/ui/button";
import { AGREEMENT, type AgreementState } from "@/lib/constants/cross-modal";
import { formatPercentage } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import type { AgreementRow } from "../types/cross-modal.types";

const TONE_CLASS: Record<AgreementState, string> = {
  conflict: "border-aeris-amber/45 bg-aeris-amber/10 text-aeris-amber",
  corroborated: "border-aeris-green/35 bg-aeris-green/10 text-aeris-green",
  "optical-only": "border-aeris-teal/35 bg-aeris-teal/10 text-aeris-teal",
  "radar-only": "border-[#C3CAD6]/35 bg-[#C3CAD6]/10 text-[#C3CAD6]",
};

interface AgreementLedgerProps {
  rows: readonly AgreementRow[];
  selectedRowId: string | null;
  onSelectRow: (rowId: string | null) => void;
  /** Hands this row's question to the workspace composer. */
  onAskAboutRow: (row: AgreementRow) => void;
  /** Frames every feature both sensors contributed to this row. */
  onFocusRow: (row: AgreementRow) => void;
}

export function AgreementLedger({
  rows,
  selectedRowId,
  onSelectRow,
  onAskAboutRow,
  onFocusRow,
}: AgreementLedgerProps) {
  if (rows.length === 0) {
    return (
      <p className="px-2 text-[11px] leading-relaxed text-muted-foreground">
        No regions to compare. Both sensors ran and neither reported a finding in this area of interest.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-1">
      {rows.map((row) => (
        <LedgerRow
          key={row.id}
          row={row}
          isExpanded={selectedRowId === row.id}
          onToggle={() => onSelectRow(row.id)}
          onAsk={() => onAskAboutRow(row)}
          onFocus={() => onFocusRow(row)}
        />
      ))}
    </ul>
  );
}

function LedgerRow({
  row,
  isExpanded,
  onToggle,
  onAsk,
  onFocus,
}: {
  row: AgreementRow;
  isExpanded: boolean;
  onToggle: () => void;
  onAsk: () => void;
  onFocus: () => void;
}) {
  const definition = AGREEMENT[row.state];
  const ExpandIcon = isExpanded ? ChevronDown : ChevronRight;

  return (
    <li
      className={cn(
        "rounded-md border transition-colors duration-fast",
        isExpanded ? "border-border bg-surface-2/50" : "border-border-soft/60",
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isExpanded}
        className="flex w-full items-start gap-1.5 px-2 py-1.5 text-left"
      >
        <ExpandIcon className="mt-0.5 size-3 shrink-0 text-muted-foreground" aria-hidden="true" />

        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-1.5 gap-y-1">
            <span className="truncate text-xs text-foreground">{row.label}</span>
            <span
              className={cn(
                "shrink-0 rounded-[2px] border px-1 font-mono text-[9px] tracking-wide uppercase",
                TONE_CLASS[row.state],
              )}
            >
              {definition.label}
            </span>
          </span>

          {/* Two confidences, side by side, never combined into one. */}
          <span className="mt-1 flex items-center gap-3 font-mono text-[9px] text-muted-foreground">
            <SensorConfidence label="OPT" value={row.opticalConfidence} tint="#00E5FF" />
            <SensorConfidence label="SAR" value={row.radarConfidence} tint="#C3CAD6" />
            {row.areaHectares !== null ? (
              <span className="tabular-nums">{row.areaHectares.toFixed(1)} ha</span>
            ) : null}
          </span>
        </span>
      </button>

      {isExpanded ? (
        <div className="border-t border-border-soft/60 px-2 py-1.5">
          <p className="text-[10px] leading-relaxed text-foreground">{row.reason}</p>

          {definition.action ? (
            <p className="mt-1.5 font-mono text-[9px] leading-relaxed tracking-wide text-aeris-amber/80 uppercase">
              {definition.action}
            </p>
          ) : null}

          {/* The other causes this state can have. Naming them is how the operator picks between them. */}
          {definition.causes.length > 1 ? (
            <ul className="mt-1.5 flex flex-col gap-0.5 border-t border-border-soft/40 pt-1.5">
              {definition.causes.map((cause) => (
                <li key={cause} className="text-[10px] leading-relaxed text-muted-foreground/70">
                  {cause}
                </li>
              ))}
            </ul>
          ) : null}

          {/*
            What to do next, in the same panel. The workspace's assistant and camera are right here, so a
            row that names a disagreement can also hand over the question about it.
          */}
          <div className="mt-2 flex items-center gap-1 border-t border-border-soft/40 pt-1.5">
            <Button type="button" size="sm" variant="ghost" onClick={onAsk} className="h-6 px-1.5">
              <MessageSquareText />
              <span className="font-mono text-[9px] tracking-wide uppercase">Ask about this</span>
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={onFocus}
              disabled={row.opticalFeatureIds.length + row.radarFeatureIds.length === 0}
              className="h-6 px-1.5"
            >
              <Crosshair />
              <span className="font-mono text-[9px] tracking-wide uppercase">Focus</span>
            </Button>
          </div>
        </div>
      ) : null}
    </li>
  );
}

/** A sensor's own confidence, or an explicit silence. Null is never rendered as zero. */
function SensorConfidence({
  label,
  value,
  tint,
}: {
  label: string;
  value: number | null;
  tint: string;
}) {
  return (
    <span className="flex items-center gap-1">
      <span style={{ color: tint }}>{label}</span>
      <span className={cn("tabular-nums", value === null && "text-muted-foreground/40")}>
        {value === null ? "silent" : formatPercentage(value)}
      </span>
    </span>
  );
}

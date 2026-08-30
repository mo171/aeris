// features/crossModal/components/FusionVerdictCard.tsx — the fused conclusion, or the refusal to draw one.
//
// what  : The headline the two sensors jointly support, the tally of agreement states, and — where no
//         headline can be stated — the explicit reason and what would resolve it.
// where : The top of the Lab's right column, above the ledger.
// how   : Three mutually exclusive states, and the two that decline to answer are the ones that matter.
//
//         REFUSED — §9.2 names four conditions under which the sensors should not be combined at all.
//         Both runs are still reported; they are simply not fused. "These should not be combined, and
//         here is why" is a better answer than a fused number the policy itself says should not exist.
//
//         BLOCKED BY CONFLICT — when the two sensors assert opposite things, the Lab declines a headline
//         rather than picking a side or averaging them into a figure that describes neither. This is the
//         product decision the page turns on: rigour where the reader will quote it, usefulness
//         everywhere else, so supporting rows are still delivered in the ledger below.
//
//         FUSED — a headline, with confidence taken as the MINIMUM of the two sensors rather than the
//         mean. A fused claim is only as good as its weaker leg; averaging would let a confident optical
//         run carry an unconfident radar one and report the pair as more certain than either sensor
//         ever claimed.

"use client";

import { AlertTriangle, Ban, CheckCircle2 } from "lucide-react";

import { ConfidenceMeter } from "@/components/sharedUI/functionalComponent/dataDisplay/ConfidenceMeter";
import {
  AGREEMENT,
  AGREEMENT_ORDER,
  FUSION_REFUSALS,
  type AgreementState,
} from "@/lib/constants/cross-modal";
import { cn } from "@/lib/utils";

import type { FusionVerdict, ModalityAdvisory } from "../types/cross-modal.types";

const COUNT_TONE: Record<AgreementState, string> = {
  conflict: "text-aeris-amber",
  corroborated: "text-aeris-green",
  "optical-only": "text-aeris-teal",
  "radar-only": "text-[#C3CAD6]",
};

interface FusionVerdictCardProps {
  verdict: FusionVerdict | null;
  advisory: ModalityAdvisory;
  counts: Readonly<Record<AgreementState, number>>;
}

export function FusionVerdictCard({ verdict, advisory, counts }: FusionVerdictCardProps) {
  if (!verdict) {
    return (
      <Shell tone="warning" icon={Ban} title="No radar observation">
        <p>
          Only one sensor is attached, so there is nothing to corroborate against. Every finding below
          stands on a single sensor and should be read that way.
        </p>
      </Shell>
    );
  }

  if (verdict.refusedBecause) {
    const refusal = FUSION_REFUSALS[verdict.refusedBecause];
    return (
      <Shell tone="neutral" icon={Ban} title={refusal.label}>
        <p>{refusal.reason}</p>
        <p className="mt-1.5 text-muted-foreground/70">{refusal.instead}</p>
        <AdvisoryNotes advisory={advisory} />
      </Shell>
    );
  }

  if (verdict.blockedByConflict) {
    return (
      <Shell tone="warning" icon={AlertTriangle} title="No headline — the sensors disagree">
        <p>{verdict.blockedByConflict}</p>
        <Tally counts={counts} />
        <AdvisoryNotes advisory={advisory} />
      </Shell>
    );
  }

  return (
    <Shell tone="positive" icon={CheckCircle2} title="Joint conclusion">
      <p className="text-foreground">{verdict.headline}</p>
      {verdict.confidence !== null ? (
        <div className="mt-2">
          <ConfidenceMeter value={verdict.confidence} />
          <p className="mt-1 font-mono text-[9px] text-muted-foreground/60">
            the lower of the two sensors, never their average
          </p>
        </div>
      ) : null}
      <Tally counts={counts} />
      <AdvisoryNotes advisory={advisory} />
    </Shell>
  );
}

function Tally({ counts }: { counts: Readonly<Record<AgreementState, number>> }) {
  const present = AGREEMENT_ORDER.filter((state) => counts[state] > 0);
  if (present.length === 0) {
    return null;
  }

  return (
    <ul className="mt-2 flex flex-col gap-0.5 border-t border-border-soft pt-1.5">
      {present.map((state) => (
        <li key={state} className="flex items-baseline gap-2">
          <span className={cn("w-6 text-right font-mono text-xs tabular-nums", COUNT_TONE[state])}>
            {counts[state]}
          </span>
          <span className="font-mono text-[10px] text-foreground">{AGREEMENT[state].label}</span>
          <span className="min-w-0 flex-1 truncate text-[10px] text-muted-foreground/60">
            {AGREEMENT[state].summary}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Whether the pair was comparable at all. Always shown — it qualifies everything above it. */
function AdvisoryNotes({ advisory }: { advisory: ModalityAdvisory }) {
  return (
    <ul className="mt-2 flex flex-col gap-0.5 border-t border-border-soft pt-1.5">
      {advisory.notes.map((note) => (
        <li
          key={note}
          className={cn(
            "font-mono text-[9px] leading-relaxed",
            advisory.verdict === "fair" ? "text-muted-foreground/60" : "text-aeris-amber/80",
          )}
        >
          {note}
        </li>
      ))}
    </ul>
  );
}

function Shell({
  tone,
  icon: Icon,
  title,
  children,
}: {
  tone: "positive" | "neutral" | "warning";
  icon: typeof Ban;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className={cn(
        "rounded-md border px-2.5 py-2",
        tone === "warning" && "border-aeris-amber/40 bg-aeris-amber/5",
        tone === "positive" && "border-aeris-green/30 bg-aeris-green/5",
        tone === "neutral" && "border-border-soft bg-surface-2/40",
      )}
    >
      <header className="flex items-center gap-1.5">
        <Icon
          className={cn(
            "size-3.5 shrink-0",
            tone === "warning" && "text-aeris-amber",
            tone === "positive" && "text-aeris-green",
            tone === "neutral" && "text-muted-foreground",
          )}
          aria-hidden="true"
        />
        <h2 className="aeris-technical">{title}</h2>
      </header>
      <div className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">{children}</div>
    </section>
  );
}

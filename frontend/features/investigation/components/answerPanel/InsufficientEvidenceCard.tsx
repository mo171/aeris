// features/investigation/components/answerPanel/InsufficientEvidenceCard.tsx — the honest refusal.
//
// what  : Renders the state where AERIS declines to assert an answer, with the reason and the concrete
//         actions that might produce one.
// where : Rendered by AnswerPanel in place of the claims when a run completes without sufficient evidence.
// how   : This is a first-class result, not an error, which is why it does not use the error styling. A
//         confidence of zero would be a claim about the world; declining to assert one is a claim about
//         the evidence, and the two must not look alike.
//
//         Every remedy carries the prompt it re-asks with, so acting on it is one click rather than a
//         retyping exercise. Naming a way forward is what separates a useful refusal from a dead end.

"use client";

import { ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";

import type { InsufficientEvidence } from "../../types/evidence.types";

interface InsufficientEvidenceCardProps {
  insufficientEvidence: InsufficientEvidence;
  onRemedy: (prompt: string) => void;
}

export function InsufficientEvidenceCard({
  insufficientEvidence,
  onRemedy,
}: InsufficientEvidenceCardProps) {
  return (
    <section className="rounded-md border border-aeris-amber/40 bg-aeris-amber/5 p-3">
      <header className="flex items-start gap-2">
        <ShieldAlert className="mt-0.5 size-4 shrink-0 text-aeris-amber" aria-hidden="true" />
        <div className="min-w-0">
          <h3 className="aeris-technical text-aeris-amber">Insufficient evidence</h3>
          <p className="mt-1 text-sm leading-snug text-foreground">
            {insufficientEvidence.reason}
          </p>
        </div>
      </header>

      {insufficientEvidence.remedies.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {insufficientEvidence.remedies.map((remedy) => (
            <Button
              key={remedy.id}
              type="button"
              size="sm"
              variant="outline"
              onClick={() => onRemedy(remedy.prompt)}
            >
              {remedy.label}
            </Button>
          ))}
        </div>
      ) : null}
    </section>
  );
}

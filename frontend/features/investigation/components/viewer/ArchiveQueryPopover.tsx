// features/investigation/components/viewer/ArchiveQueryPopover.tsx — composing the request sent to the archive.
//
// what  : The window, modalities and cloud ceiling the operator wants searched, and the button that asks
//         for it. Shows back what the catalogue said about the window it was given.
// where : Opened from the timeline scrubber's header row.
// how   : This is the one surface in the workspace where the operator writes the query the backend
//         receives. Everything else on this page narrows or interprets a result; this decides what the
//         result is drawn from, which is why the request is shown in full rather than being assembled
//         invisibly from whatever happens to be selected.
//
//         The cloud ceiling is part of the QUERY, not a display filter. Sending it means the archive can
//         answer "there is nothing under 20% cloud in this window" as a fact about coverage rather than
//         handing back scenes the interface then quietly hides — a distinction that decides whether the
//         operator learns their question is unanswerable or just looks like it has no data.
//
//         The recommended pair comes back as an offer with a stated reason and is never applied on its
//         own. The catalogue can see the archive; the operator can see the question.

"use client";

import { Check, Search, Sparkles } from "lucide-react";
import { useState } from "react";

import { Chip } from "@/components/sharedUI/dumbComponent/Chip";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Slider } from "@/components/ui/slider";
import { TIMELINE_QUERY } from "@/lib/constants/timeline";
import { cn } from "@/lib/utils";

import type { AcquisitionModality, CoverageGap, PairRecommendation } from "../../types/catalogue.types";

const MODALITY_OPTIONS: readonly { id: AcquisitionModality; label: string; hint: string }[] = [
  { id: "optical", label: "Optical", hint: "Reflectance. Blocked by cloud." },
  { id: "sar", label: "Radar", hint: "Backscatter. Sees through cloud." },
  { id: "multispectral", label: "Multispectral", hint: "Band maths and indices." },
  { id: "hyperspectral", label: "Hyperspectral", hint: "Material signatures." },
];

interface ArchiveQueryPopoverProps {
  from: string;
  to: string;
  modalities: AcquisitionModality[];
  cloudCeilingPercentage: number;
  isSearching: boolean;
  error: Error | null;
  coverageGaps: CoverageGap[];
  recommendation: PairRecommendation | null;
  advisory: string | null;
  onSearch: (window: {
    from: string;
    to: string;
    modalities: AcquisitionModality[];
    cloudCeilingPercentage: number;
  }) => void;
  onApplyRecommendation: (recommendation: PairRecommendation) => void;
  onDismissRecommendation: () => void;
}

export function ArchiveQueryPopover({
  from,
  to,
  modalities,
  cloudCeilingPercentage,
  isSearching,
  error,
  coverageGaps,
  recommendation,
  advisory,
  onSearch,
  onApplyRecommendation,
  onDismissRecommendation,
}: ArchiveQueryPopoverProps) {
  const [draftFrom, setDraftFrom] = useState(from.slice(0, 10));
  const [draftTo, setDraftTo] = useState(to.slice(0, 10));
  const [draftModalities, setDraftModalities] = useState<AcquisitionModality[]>(modalities);
  const [draftCloud, setDraftCloud] = useState(cloudCeilingPercentage);

  const isWindowValid = Date.parse(draftFrom) < Date.parse(draftTo);
  const canSearch = isWindowValid && draftModalities.length > 0 && !isSearching;

  const toggleModality = (modality: AcquisitionModality) => {
    setDraftModalities((current) =>
      current.includes(modality)
        ? current.filter((candidate) => candidate !== modality)
        : [...current, modality],
    );
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-6 gap-1.5 px-2 font-mono text-[10px] tracking-wide text-muted-foreground"
        >
          <Search className="size-3" />
          Archive
          {recommendation ? (
            <span className="size-1.5 rounded-full bg-aeris-teal" aria-label="A pair is suggested" />
          ) : null}
        </Button>
      </PopoverTrigger>

      <PopoverContent side="top" align="end" className="w-80 p-3">
        <p className="aeris-technical">Search the archive</p>
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
          The area of interest travels with this query, so the catalogue answers about this ground
          rather than about a scene footprint.
        </p>

        <div className="mt-3 grid grid-cols-2 gap-2">
          <div>
            <Label htmlFor="archive-from" className="aeris-technical">
              From
            </Label>
            <Input
              id="archive-from"
              type="date"
              value={draftFrom}
              onChange={(event) => setDraftFrom(event.target.value)}
              className="mt-1 h-7 font-mono text-[11px]"
            />
          </div>
          <div>
            <Label htmlFor="archive-to" className="aeris-technical">
              To
            </Label>
            <Input
              id="archive-to"
              type="date"
              value={draftTo}
              onChange={(event) => setDraftTo(event.target.value)}
              className="mt-1 h-7 font-mono text-[11px]"
            />
          </div>
        </div>

        {!isWindowValid ? (
          <p className="mt-1.5 text-[10px] text-aeris-amber">
            The start of the window must fall before its end.
          </p>
        ) : null}

        <fieldset className="mt-3">
          <legend className="aeris-technical">Sensors</legend>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {MODALITY_OPTIONS.map((option) => {
              const isOn = draftModalities.includes(option.id);
              return (
                <button
                  key={option.id}
                  type="button"
                  title={option.hint}
                  aria-pressed={isOn}
                  onClick={() => toggleModality(option.id)}
                  className={cn(
                    "rounded-sm border px-1.5 py-0.5 font-mono text-[10px] tracking-wide transition-colors duration-fast",
                    isOn
                      ? "border-aeris-teal/45 bg-aeris-teal/10 text-aeris-teal"
                      : "border-border text-muted-foreground hover:text-foreground",
                  )}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        </fieldset>

        <div className="mt-3">
          <div className="flex items-baseline justify-between">
            <Label htmlFor="archive-cloud" className="aeris-technical">
              Cloud ceiling
            </Label>
            <span className="font-mono text-[10px] tabular-nums text-foreground">
              {draftCloud}%
            </span>
          </div>
          <Slider
            id="archive-cloud"
            className="mt-2"
            min={0}
            max={100}
            step={TIMELINE_QUERY.cloudCeilingStepPercentage}
            value={[draftCloud]}
            onValueChange={([next]) => setDraftCloud(next ?? draftCloud)}
          />
          <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
            Optical acquisitions above this stay visible on the timeline but cannot be chosen as inputs.
          </p>
        </div>

        <Button
          type="button"
          size="sm"
          className="mt-3 w-full"
          disabled={!canSearch}
          onClick={() =>
            onSearch({
              from: new Date(`${draftFrom}T00:00:00.000Z`).toISOString(),
              to: new Date(`${draftTo}T23:59:59.000Z`).toISOString(),
              modalities: draftModalities,
              cloudCeilingPercentage: draftCloud,
            })
          }
        >
          {isSearching ? "Searching…" : "Search archive"}
        </Button>

        {error ? (
          <p className="mt-2 text-[10px] text-aeris-red">{error.message}</p>
        ) : null}

        {advisory ? (
          <p className="mt-3 border-t border-border-soft pt-2 text-[11px] leading-relaxed text-muted-foreground">
            {advisory}
          </p>
        ) : null}

        {coverageGaps.length > 0 ? (
          <div className="mt-2">
            <p className="aeris-technical">Coverage holes</p>
            <ul className="mt-1 flex flex-col gap-0.5">
              {coverageGaps.map((gap) => (
                <li
                  key={`${gap.from}-${gap.to}`}
                  className="font-mono text-[10px] leading-relaxed text-aeris-amber"
                >
                  {gap.from.slice(0, 10)} → {gap.to.slice(0, 10)} · {gap.days}d · {gap.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {recommendation ? (
          <div className="mt-3 rounded-md border border-aeris-teal/35 bg-aeris-teal/5 p-2">
            <span className="flex items-center gap-1.5">
              <Sparkles className="size-3 text-aeris-teal" aria-hidden="true" />
              <Chip tone="teal">Suggested pair</Chip>
            </span>
            <p className="mt-1.5 text-[11px] leading-relaxed text-foreground">
              {recommendation.reason}
            </p>
            <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
              {recommendation.separationDays} days apart
            </p>
            <div className="mt-2 flex gap-1.5">
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-6 flex-1 gap-1 text-[11px]"
                onClick={() => onApplyRecommendation(recommendation)}
              >
                <Check className="size-3" />
                Use it
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-6 text-[11px]"
                onClick={onDismissRecommendation}
              >
                Keep mine
              </Button>
            </div>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

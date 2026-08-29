// features/investigation/components/inputsPanel/EvidenceLayerRow.tsx — one layer in the evidence stack.
//
// what  : A layer control that also carries the layer provenance: which model produced it, at which
//         version, and how confident it was.
// where : Rendered by EvidenceLayerStack, once per layer.
// how   : Most products render this as a generic GIS table of contents. This one refuses to. Every row
//         states where the layer came from, so the stack reads as a table of contents for the argument
//         rather than for the pixels — which is the difference between an evidence system and a map.
//
//         Opacity is a slider rather than a numeric field because it is a perceptual judgement, and it
//         writes straight through to the stage on every change so the operator is adjusting what they can
//         see rather than committing a value and waiting.
//
//         Each row also QUANTIFIES what the layer contains: how many features, how much ground they cover,
//         and how confident the model was across them. A layer stack that only toggles visibility makes the
//         operator open the answer panel to find out how much was detected — and the numbers are already
//         on the features, so not showing them was withholding what the row already knew.
//
//         The figures are measured from the features present, never quoted from elsewhere. A count that
//         disagrees with the geometry on screen is the failure mode this product exists to prevent.

"use client";

import { Eye, EyeOff, Focus } from "lucide-react";

import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatPercentage } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import type { EvidenceLayer } from "../../types/layer.types";

/**
 * What this layer actually contains, measured from its own features.
 *
 * Confidence is averaged only over the features that assert one. Treating "not asserted" as zero would
 * drag the mean down and report a model as less certain than it ever claimed to be.
 */
function summarise(layer: EvidenceLayer) {
  const withArea = layer.features.filter((feature) => feature.areaHectares !== null);
  const withConfidence = layer.features.filter((feature) => feature.confidence !== null);

  const totalHectares = withArea.reduce((sum, feature) => sum + (feature.areaHectares ?? 0), 0);
  const meanConfidence =
    withConfidence.length === 0
      ? null
      : withConfidence.reduce((sum, feature) => sum + (feature.confidence ?? 0), 0) /
        withConfidence.length;

  return { count: layer.features.length, totalHectares, meanConfidence };
}

function formatArea(hectares: number): string {
  return hectares >= 100 ? `${(hectares / 100).toFixed(2)} km²` : `${hectares.toFixed(1)} ha`;
}

interface EvidenceLayerRowProps {
  layer: EvidenceLayer;
  isSoloed: boolean;
  onToggleVisibility: () => void;
  onToggleSolo: () => void;
  onOpacityChange: (opacity: number) => void;
}

export function EvidenceLayerRow({
  layer,
  isSoloed,
  onToggleVisibility,
  onToggleSolo,
  onOpacityChange,
}: EvidenceLayerRowProps) {
  const VisibilityIcon = layer.isVisible ? Eye : EyeOff;
  const summary = summarise(layer);

  return (
    <div
      className={cn(
        "rounded-md border border-border-soft bg-surface-2/40 px-2 py-1.5 transition-opacity duration-base",
        !layer.isVisible && "opacity-55",
      )}
    >
      <div className="flex items-center gap-1.5">
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          aria-pressed={layer.isVisible}
          aria-label={layer.isVisible ? `Hide ${layer.title}` : `Show ${layer.title}`}
          onClick={onToggleVisibility}
        >
          <VisibilityIcon className={layer.isVisible ? "text-aeris-teal" : undefined} />
        </Button>

        <span className="min-w-0 flex-1 truncate text-xs text-foreground" title={layer.title}>
          {layer.title}
        </span>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              aria-pressed={isSoloed}
              aria-label={isSoloed ? "Stop soloing this layer" : "Show only this layer"}
              onClick={onToggleSolo}
              className={cn(isSoloed && "text-aeris-teal")}
            >
              <Focus />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="left">Show only this layer</TooltipContent>
        </Tooltip>
      </div>

      <div className="mt-1 flex items-center gap-2 pl-1">
        <Slider
          value={[layer.opacity]}
          min={0}
          max={1}
          step={0.05}
          onValueChange={([next]) => onOpacityChange(next)}
          aria-label={`${layer.title} opacity`}
          className="flex-1"
        />
        <span className="w-8 shrink-0 text-right font-mono text-[10px] tabular-nums text-muted-foreground">
          {formatPercentage(layer.opacity)}
        </span>
      </div>

      {summary.count > 0 ? (
        <p className="mt-1 flex flex-wrap items-baseline gap-x-2 pl-1 font-mono text-[10px] tabular-nums text-foreground">
          <span>
            {summary.count} {summary.count === 1 ? "feature" : "features"}
          </span>
          {summary.totalHectares > 0 ? (
            <span className="text-muted-foreground">{formatArea(summary.totalHectares)}</span>
          ) : null}
          {summary.meanConfidence !== null ? (
            <span className="text-muted-foreground">
              {formatPercentage(summary.meanConfidence)} mean
            </span>
          ) : null}
        </p>
      ) : null}

      <p className="mt-1 truncate pl-1 font-mono text-[10px] text-muted-foreground/70">
        {layer.provenance.modelId}@{layer.provenance.modelVersion}
        {layer.provenance.confidence !== null
          ? ` · ${formatPercentage(layer.provenance.confidence)}`
          : " · confidence not asserted"}
      </p>
    </div>
  );
}

// features/investigation/components/inputsPanel/LayerMetadataDrawer.tsx — per-layer provenance and metadata.
//
// what  : A slide-out drawer showing the full provenance and metadata for an evidence layer — model,
//         version, pipeline stage, trace step, confidence, feature statistics, overlay description,
//         and operator annotations.
// where : Opened from EvidenceLayerRow via a metadata button; slides over the left panel.
// how   : The Layers tab shows summaries. This drawer shows everything the layer knows about itself,
//         which is the difference between "I can see a layer" and "I can evaluate a layer". Every
//         section reads from the existing layer and overlay descriptors — no additional fetch required.

"use client";

import { FileText, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatPercentage } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import type { EvidenceLayer } from "../../types/layer.types";

interface LayerMetadataDrawerProps {
  layer: EvidenceLayer;
  onClose: () => void;
  /** Operator-authored note stored beside the descriptor, never in it. */
  annotation?: string;
  onAnnotationChange?: (text: string) => void;
}

function MetadataRow({ label, value }: { label: string; value: string | number | null }) {
  if (value === null || value === undefined) return null;
  return (
    <div className="flex items-baseline justify-between gap-2 py-1">
      <span className="shrink-0 text-[11px] text-muted-foreground">{label}</span>
      <span className="truncate text-right font-mono text-[11px] text-foreground">{String(value)}</span>
    </div>
  );
}

export function LayerMetadataDrawer({
  layer,
  onClose,
  annotation,
  onAnnotationChange,
}: LayerMetadataDrawerProps) {
  const withArea = layer.features.filter((f) => f.areaHectares !== null);
  const totalArea = withArea.reduce((sum, f) => sum + (f.areaHectares ?? 0), 0);
  const withConf = layer.features.filter((f) => f.confidence !== null);
  const meanConfidence =
    withConf.length > 0
      ? withConf.reduce((sum, f) => sum + (f.confidence ?? 0), 0) / withConf.length
      : null;

  return (
    <div
      className={cn(
        "absolute inset-0 z-30 flex flex-col bg-surface/95 backdrop-blur-sm",
        "animate-in slide-in-from-right-4 duration-200",
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border-soft px-3 py-2">
        <FileText className="size-4 text-aeris-teal" />
        <h3 className="min-w-0 flex-1 truncate text-xs font-semibold text-foreground">
          {layer.title}
        </h3>
        <Button type="button" size="icon-sm" variant="ghost" onClick={onClose}>
          <X className="size-3.5" />
        </Button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-3">
        {/* Provenance */}
        <section>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Provenance
          </p>
          <div className="divide-y divide-border-soft">
            <MetadataRow label="Model" value={layer.provenance.modelId} />
            <MetadataRow label="Version" value={layer.provenance.modelVersion} />
            <MetadataRow label="Trace step" value={layer.provenance.traceStepId} />
            <MetadataRow
              label="Confidence"
              value={
                layer.provenance.confidence !== null
                  ? formatPercentage(layer.provenance.confidence)
                  : "Not asserted"
              }
            />
          </div>
        </section>

        {/* Layer properties */}
        <section>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Layer
          </p>
          <div className="divide-y divide-border-soft">
            <MetadataRow label="Kind" value={layer.kind} />
            <MetadataRow label="Render mode" value={layer.renderMode} />
            <MetadataRow label="Overlay" value={layer.overlayId ?? "none"} />
            <MetadataRow label="Color ramp" value={layer.colorRampId} />
            <MetadataRow label="Comparator side" value={layer.comparatorSide} />
            {layer.valueDomain ? (
              <>
                <MetadataRow label="Domain min" value={layer.valueDomain.minimum} />
                <MetadataRow label="Domain max" value={layer.valueDomain.maximum} />
              </>
            ) : null}
          </div>
        </section>

        {/* Statistics */}
        <section>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Statistics
          </p>
          <div className="divide-y divide-border-soft">
            <MetadataRow label="Features" value={layer.features.length} />
            <MetadataRow
              label="Total area"
              value={totalArea > 0 ? `${totalArea >= 100 ? `${(totalArea / 100).toFixed(2)} km²` : `${totalArea.toFixed(1)} ha`}` : null}
            />
            <MetadataRow
              label="Mean confidence"
              value={meanConfidence !== null ? formatPercentage(meanConfidence) : null}
            />
          </div>
        </section>

        {/* Annotation */}
        <section>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Annotation
          </p>
          <textarea
            className="w-full rounded-md border border-border-soft bg-surface-2/60 px-2 py-1.5 font-mono text-[11px] text-foreground placeholder:text-muted-foreground/50 focus:border-aeris-teal focus:outline-none focus:ring-1 focus:ring-aeris-teal/30"
            rows={3}
            placeholder="Add an operator note about this layer…"
            value={annotation ?? ""}
            onChange={(e) => onAnnotationChange?.(e.target.value)}
          />
        </section>
      </div>
    </div>
  );
}

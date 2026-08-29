// features/investigation/components/viewer/EvidenceLegend.tsx — what the colours on the scene mean.
//
// what  : A key for every visible overlay — a ramp bar with its domain and units for continuous products,
//         a swatch list for classified ones, a stepped bar with break labels for graduated ones.
// where : Rendered into the centre column of InvestigationScreen, above the readout.
// how   : A scene covered in coloured geometry that never says what the colours mean is a picture, not
//         evidence. An analyst has to be able to answer "what is the amber?" without asking anyone, and
//         a judge has to be able to answer it without being told.
//
//         Every form here is DERIVED from the overlay catalogue's `encoding`, never authored per product.
//         This file used to hold a hardcoded map of ramp id to meaning, which meant adding an analysis
//         product edited a component — the exact coupling layer.schema.ts says it avoids. Now the three
//         encodings are the only three branches, and a new overlay is one catalogue entry.
//
//         The swatches and the bar sample the SAME ramp function the geometry samples, so a legend
//         physically cannot describe a picture nobody is looking at.
//
//         Continuous bars are drawn against the OBSERVED domain where the layer carries one. NDVI's
//         theoretical range is −1 to +1; a scene spanning 0.1 to 0.7 wastes most of that bar on values
//         that are not present, and flattens every distinction that is.
//
//         It lists only VISIBLE layers and disappears entirely when nothing is drawn. A legend for layers
//         that are switched off is noise, and a permanently present empty box is worse.
//
//         ANCHORED TOP-LEFT, NOT CENTRED, and capped in height. It used to sit in the centre column's
//         flow, which was fine at two layers and became a wall across the middle of the scene at six —
//         a key is a reference you glance at, never something that occludes the thing it describes. It
//         now takes the corner opposite the inspector, scrolls past the cap rather than growing, and
//         collapses to its header so an operator who knows the palette can reclaim the corner entirely.

"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

import {
  BIN_SCHEMES,
  CLASS_PALETTES,
  binRampPosition,
  findOverlay,
  formatOverlayValue,
  rampToCssGradient,
  sampleRamp,
  type OverlayDefinition,
} from "@/lib/constants/overlays";
import { VECTOR_PALETTE } from "@/lib/constants/layers";

import { useInvestigationStore } from "../../store/investigation-store";
import type { EvidenceLayer } from "../../types/layer.types";

interface EvidenceLegendProps {
  layers: EvidenceLayer[];
}

export function EvidenceLegend({ layers }: EvidenceLegendProps) {
  const projection = useInvestigationStore((state) => state.projection);
  const renderMode = useInvestigationStore((state) => state.renderMode);
  const [isExpanded, setIsExpanded] = useState(true);
  // Must match the rule the stage binding applies, or the legend describes a picture nobody sees.
  const isExtruded = projection !== "2D" && renderMode === "extruded";

  const visibleLayers = layers.filter(
    (layer) => layer.isVisible && layer.kind !== "raster-tiles" && layer.features.length > 0,
  );

  if (visibleLayers.length === 0) {
    return null;
  }

  const ExpandIcon = isExpanded ? ChevronDown : ChevronRight;

  return (
    <div className="pointer-events-auto flex w-52 flex-col rounded-md border border-border bg-surface-2/80 backdrop-blur-md">
      <button
        type="button"
        onClick={() => setIsExpanded((current) => !current)}
        aria-expanded={isExpanded}
        className="flex items-center gap-1.5 px-2 py-1.5 text-left"
      >
        <ExpandIcon className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
        <span className="aeris-technical">Legend</span>
        <span className="ml-auto font-mono text-[10px] tabular-nums text-muted-foreground">
          {visibleLayers.length}
        </span>
      </button>

      {/*
        Scrolls past the cap rather than growing. Height is the scene's, not the legend's, to spend.
      */}
      {isExpanded ? (
        <div className="flex max-h-[40vh] flex-col gap-2 overflow-y-auto border-t border-border-soft px-2.5 py-2">
          {visibleLayers.map((layer) => (
            <LayerKey key={layer.id} layer={layer} isExtruded={isExtruded} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function LayerKey({ layer, isExtruded }: { layer: EvidenceLayer; isExtruded: boolean }) {
  const overlay = findOverlay(layer.overlayId);

  return (
    <div className="flex flex-col gap-1">
      <p className="font-mono text-[10px] whitespace-nowrap text-foreground">{layer.title}</p>
      {overlay ? (
        <EncodingKey layer={layer} overlay={overlay} isExtruded={isExtruded} />
      ) : (
        <UncataloguedKey layer={layer} />
      )}
    </div>
  );
}

function EncodingKey({
  layer,
  overlay,
  isExtruded,
}: {
  layer: EvidenceLayer;
  overlay: OverlayDefinition;
  isExtruded: boolean;
}) {
  switch (overlay.encoding.kind) {
    case "continuous": {
      const domain = layer.valueDomain ?? overlay.encoding.domain;
      return (
        <div className="flex flex-col gap-0.5">
          <span
            className="h-1.5 w-full rounded-[2px] border border-border-soft"
            style={{ background: rampToCssGradient(overlay.encoding.rampId) }}
            aria-hidden="true"
          />
          <span className="flex justify-between font-mono text-[9px] tabular-nums text-muted-foreground">
            <span>{formatOverlayValue(domain.minimum, overlay.encoding.unitId)}</span>
            <span>{formatOverlayValue(domain.maximum, overlay.encoding.unitId)}</span>
          </span>
          {overlay.interpretation ? (
            <span className="font-mono text-[9px] leading-tight text-muted-foreground">
              {overlay.interpretation}
            </span>
          ) : null}
        </div>
      );
    }

    case "graduated": {
      const scheme = BIN_SCHEMES[overlay.encoding.schemeId];
      return (
        <div className="flex flex-col gap-0.5">
          <span className="flex gap-px" aria-hidden="true">
            {scheme.bins.map((bin, index) => (
              <span
                key={bin.label}
                className="h-1.5 flex-1 rounded-[1px]"
                style={{ backgroundColor: sampleRamp(scheme.rampId, binRampPosition(scheme.id, index)) }}
              />
            ))}
          </span>
          <span className="flex justify-between gap-1 font-mono text-[9px] text-muted-foreground">
            <span>{scheme.bins[0].label}</span>
            <span>{scheme.bins[scheme.bins.length - 1].label}</span>
          </span>
          {isExtruded ? (
            <span className="font-mono text-[9px] text-muted-foreground">taller = higher band</span>
          ) : null}
        </div>
      );
    }

    case "categorical": {
      const palette = CLASS_PALETTES[overlay.encoding.paletteId];
      // Only the classes actually present. A nine-class land-cover key over a scene containing three of
      // them is a legend for somebody else's investigation.
      const presentClassIds = new Set(
        layer.features.map((feature) => feature.classId).filter((id): id is string => id !== null),
      );
      const presentClasses = palette.classes.filter((entry) => presentClassIds.has(entry.id));
      const shownClasses = presentClasses.length > 0 ? presentClasses : palette.classes;

      return (
        <ul className="flex flex-col gap-0.5">
          {shownClasses.map((entry) => (
            <li key={entry.id} className="flex items-center gap-1.5" title={entry.description}>
              {/* The swatch hatches when the geometry hatches, so the key matches the scene exactly. */}
              <span
                className="size-2 shrink-0 rounded-[2px] border"
                style={
                  overlay.rendersAsHatch
                    ? {
                        backgroundImage: `repeating-linear-gradient(90deg, ${entry.color} 0 1px, transparent 1px 3px)`,
                        borderColor: entry.color,
                      }
                    : { backgroundColor: `${entry.color}88`, borderColor: entry.color }
                }
                aria-hidden="true"
              />
              <span className="font-mono text-[9px] whitespace-nowrap text-muted-foreground">
                {entry.label}
              </span>
            </li>
          ))}
        </ul>
      );
    }
  }
}

/** A product this build has not learned about still gets a key, from its own ramp and title. */
function UncataloguedKey({ layer }: { layer: EvidenceLayer }) {
  const palette = VECTOR_PALETTE[layer.colorRampId];

  return (
    <span className="flex items-center gap-1.5">
      <span
        className="size-2 shrink-0 rounded-[2px] border"
        style={{ backgroundColor: `${palette.fill}55`, borderColor: palette.outline }}
        aria-hidden="true"
      />
      <span className="font-mono text-[9px] text-muted-foreground">uncatalogued product</span>
    </span>
  );
}

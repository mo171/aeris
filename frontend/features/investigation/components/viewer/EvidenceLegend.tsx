// features/investigation/components/viewer/EvidenceLegend.tsx — what the colours on the scene mean.
//
// what  : Names every visible evidence layer, its colour, and — for magnitude-ranked layers — what the
//         extremes of the ramp represent.
// where : Rendered into the centre column of InvestigationScreen, above the readout.
// how   : A scene covered in coloured geometry that never says what the colours mean is a picture, not
//         evidence. An analyst has to be able to answer "what is the amber?" without asking anyone, and
//         a judge has to be able to answer it without being told.
//
//         It lists only VISIBLE layers, and disappears entirely when nothing is drawn. A legend for
//         layers that are switched off is noise, and a permanently present empty box is worse.
//
//         Colours come from the same palette the renderer resolves, so the swatch and the geometry can
//         never disagree — both read `VECTOR_PALETTE` keyed by the layer's ramp id.

"use client";

import { VECTOR_PALETTE } from "@/lib/constants/layers";

import type { EvidenceLayer } from "../../types/layer.types";

/** What the ramp means, per product. Stated in the operator's terms, not the model's. */
const RAMP_MEANING: Partial<Record<EvidenceLayer["colorRampId"], string>> = {
  "change-diverging": "taller and brighter = larger change",
  "detection-teal": "outlined = detected object",
  "index-vegetation": "brighter = denser vegetation",
  "confidence-magma": "brighter = more confident",
  "mask-amber": "filled = masked",
  "artefact-neutral": "pipeline output, not a finding",
};

interface EvidenceLegendProps {
  layers: EvidenceLayer[];
}

export function EvidenceLegend({ layers }: EvidenceLegendProps) {
  const visibleVectorLayers = layers.filter(
    (layer) => layer.isVisible && layer.kind !== "raster-tiles" && layer.features.length > 0,
  );

  if (visibleVectorLayers.length === 0) {
    return null;
  }

  return (
    <div className="pointer-events-none flex flex-col gap-1 rounded-md border border-border bg-surface-2/70 px-2.5 py-1.5 backdrop-blur-md">
      {visibleVectorLayers.map((layer) => {
        const palette = VECTOR_PALETTE[layer.colorRampId];
        const meaning = RAMP_MEANING[layer.colorRampId];

        return (
          <span key={layer.id} className="flex items-center gap-2">
            <span
              className="size-2.5 shrink-0 rounded-[2px] border"
              style={{ backgroundColor: `${palette.fill}55`, borderColor: palette.outline }}
              aria-hidden="true"
            />
            <span className="font-mono text-[10px] whitespace-nowrap text-foreground">
              {layer.title}
            </span>
            {meaning ? (
              <span className="font-mono text-[10px] whitespace-nowrap text-muted-foreground">
                {meaning}
              </span>
            ) : null}
          </span>
        );
      })}
    </div>
  );
}

// features/investigation/components/inputsPanel/OverlayBrowser.tsx — the catalogue, made visible.
//
// what  : Everything the system can draw on the scene — findings, spectral indices, validity masks and
//         structural context — grouped, each with its key, how to read it, and what it cannot be trusted
//         to say. Rows that are already on the scene are marked as such.
// where : The third section of the Toolbox tab, beneath the operations and the commands.
// how   : The layer stack can only ever show what a run HAPPENED to produce. That leaves an operator
//         unable to learn that MNDWI exists, or that burn severity is available, until something
//         coincidentally produces one — the same discoverability failure the Toolbox was built to fix for
//         operations, still open for products.
//
//         So this lists CAPABILITY, not state. It is read straight from the overlay catalogue, which
//         means it cannot drift: adding a catalogue entry makes a row appear here, in the legend, and in
//         the renderer, with no component edited.
//
//         Each row carries the same key form the legend uses, from the same sampling functions, so an
//         operator learning what a product looks like here recognises it on the scene. Limitations are
//         shown rather than hidden — "confuses bare soil with buildings" is the single most useful thing
//         to know about NDBI before asking for it, and the design document says it in as many words.
//
//         Nothing here is a control. An overlay appears on the scene because an analysis produced it, and
//         a switch that promised otherwise would be a button that fabricates evidence.

"use client";

import { useMemo, useState } from "react";

import {
  BIN_SCHEMES,
  CLASS_PALETTES,
  OVERLAY_GROUPS,
  OVERLAY_CATALOGUE,
  SPECTRAL_INDICES,
  binRampPosition,
  rampToCssGradient,
  sampleRamp,
  type OverlayDefinition,
  type OverlayGroup,
} from "@/lib/constants/overlays";
import { getPipelineStage } from "@/lib/constants/pipeline-stages";
import { cn } from "@/lib/utils";

/** Said in the operator's terms, and stating what the group is CLAIMING rather than what it contains. */
const GROUP_COPY: Record<OverlayGroup, { label: string; caption: string }> = {
  finding: { label: "Findings", caption: "Produced by a model, and carry the version that produced them." },
  index: { label: "Spectral indices", caption: "Closed-form band arithmetic. Cheap, and defensible." },
  mask: { label: "Masks", caption: "Where nothing can be asserted, and why." },
  structure: { label: "Structure", caption: "Mapped footprints. Context for a question, never evidence." },
  context: { label: "Context", caption: "The ground it is all read against." },
};

interface OverlayBrowserProps {
  /** Overlay ids currently on the scene, so a row can say it is already drawn. */
  activeOverlayIds: readonly string[];
  /** Shared with the Toolbox's filter box, so one search covers operations and products alike. */
  query: string;
}

export function OverlayBrowser({ activeOverlayIds, query }: OverlayBrowserProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const active = useMemo(() => new Set(activeOverlayIds), [activeOverlayIds]);

  const grouped = useMemo(() => {
    const search = query.trim().toLowerCase();
    const overlays = Object.values(OVERLAY_CATALOGUE).filter((overlay) => {
      if (!search) {
        return true;
      }
      return `${overlay.label} ${overlay.description}`.toLowerCase().includes(search);
    });

    return OVERLAY_GROUPS.map((group) => ({
      group,
      overlays: overlays.filter((overlay) => overlay.group === group),
    })).filter((section) => section.overlays.length > 0);
  }, [query]);

  if (grouped.length === 0) {
    return null;
  }

  return (
    <section className="flex flex-col gap-2">
      <h3 className="aeris-technical px-1">Overlays · what can be shown</h3>

      {grouped.map(({ group, overlays }) => (
        <div key={group} className="flex flex-col gap-1">
          <p className="px-1 font-mono text-[9px] tracking-wide text-muted-foreground/60 uppercase">
            {GROUP_COPY[group].label}
            <span className="ml-1.5 normal-case tracking-normal text-muted-foreground/45">
              {GROUP_COPY[group].caption}
            </span>
          </p>

          {overlays.map((overlay) => (
            <OverlayRow
              key={overlay.id}
              overlay={overlay}
              isActive={active.has(overlay.id)}
              isExpanded={expandedId === overlay.id}
              onToggle={() =>
                setExpandedId((current) => (current === overlay.id ? null : overlay.id))
              }
            />
          ))}
        </div>
      ))}
    </section>
  );
}

function OverlayRow({
  overlay,
  isActive,
  isExpanded,
  onToggle,
}: {
  overlay: OverlayDefinition;
  isActive: boolean;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const stage = getPipelineStage(overlay.producedBy);
  const index = overlay.spectralIndexId ? SPECTRAL_INDICES[overlay.spectralIndexId] : null;

  return (
    <div
      className={cn(
        "rounded-md border px-2 py-1.5 transition-colors duration-fast",
        isActive ? "border-aeris-teal/35 bg-aeris-teal/5" : "border-border-soft/60",
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isExpanded}
        className="flex w-full items-start gap-2 text-left"
      >
        <span className="mt-0.5 w-9 shrink-0">
          <OverlayKey overlay={overlay} />
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-1.5">
            <span className="truncate text-xs text-foreground">{overlay.label}</span>
            <span className="shrink-0 font-mono text-[9px] text-muted-foreground/50">
              {overlay.producedBy} · {stage.label}
            </span>
            {isActive ? (
              <span className="ml-auto shrink-0 font-mono text-[9px] tracking-wide text-aeris-teal uppercase">
                on scene
              </span>
            ) : null}
          </span>
          <span className="mt-0.5 block text-[10px] leading-relaxed text-muted-foreground/70">
            {overlay.description}
          </span>
        </span>
      </button>

      {isExpanded ? (
        <dl className="mt-1.5 flex flex-col gap-1 border-t border-border-soft/60 pt-1.5">
          {index ? (
            <Detail label="Formula">
              <span className="font-mono text-[10px] text-foreground">{index.sentinel2Formula}</span>
              <span className="mt-0.5 block font-mono text-[9px] text-muted-foreground/60">
                bands: {index.requiredBands.join(", ")}
              </span>
            </Detail>
          ) : null}

          {overlay.interpretation ? (
            <Detail label="Reading">{overlay.interpretation}</Detail>
          ) : null}

          {overlay.limitations.length > 0 ? (
            <Detail label="Cannot say">
              <ul className="flex flex-col gap-0.5">
                {overlay.limitations.map((limitation) => (
                  <li key={limitation} className="text-aeris-amber/75">
                    {limitation}
                  </li>
                ))}
              </ul>
            </Detail>
          ) : null}
        </dl>
      ) : null}
    </div>
  );
}

/** The same key form the legend draws, so a product looks the same wherever it is described. */
function OverlayKey({ overlay }: { overlay: OverlayDefinition }) {
  switch (overlay.encoding.kind) {
    case "continuous":
      return (
        <span
          className="block h-2 w-full rounded-[2px] border border-border-soft"
          style={{ background: rampToCssGradient(overlay.encoding.rampId) }}
          aria-hidden="true"
        />
      );

    case "graduated": {
      const scheme = BIN_SCHEMES[overlay.encoding.schemeId];
      return (
        <span className="flex gap-px" aria-hidden="true">
          {scheme.bins.map((bin, binIndex) => (
            <span
              key={bin.label}
              className="h-2 flex-1 rounded-[1px]"
              style={{
                backgroundColor: sampleRamp(scheme.rampId, binRampPosition(scheme.id, binIndex)),
              }}
            />
          ))}
        </span>
      );
    }

    case "categorical": {
      const palette = CLASS_PALETTES[overlay.encoding.paletteId];
      // Capped: a nine-class key at this size is a smear, and the full list is one row away in the legend.
      return (
        <span className="flex gap-px" aria-hidden="true">
          {palette.classes.slice(0, 5).map((entry) => (
            <span
              key={entry.id}
              className="h-2 flex-1 rounded-[1px] border"
              style={
                overlay.rendersAsHatch
                  ? {
                      backgroundImage: `repeating-linear-gradient(90deg, ${entry.color} 0 1px, transparent 1px 3px)`,
                      borderColor: entry.color,
                    }
                  : { backgroundColor: entry.color, borderColor: entry.color }
              }
            />
          ))}
        </span>
      );
    }
  }
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="font-mono text-[9px] tracking-wide text-muted-foreground/50 uppercase">
        {label}
      </dt>
      <dd className="text-[10px] leading-relaxed text-muted-foreground">{children}</dd>
    </div>
  );
}

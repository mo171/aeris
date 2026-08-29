// features/investigation/components/viewer/FeatureInspector.tsx — the full record behind one piece of geometry.
//
// what  : Everything known about the feature the operator clicked: what it is, where it is, how big, how
//         confident the model was, which model produced it and which claim it supports.
// where : Floats over the scene in the centre column of InvestigationScreen.
// how   : This is the identify tool, and its absence was the largest working gap on the surface. Clicking
//         a detection used to highlight it and say nothing — the operator could see that the system had
//         found something and had no way to ask what. Every GIS has this verb; an evidence system that
//         asks to be checked against pixels needs it more than most.
//
//         It runs the spotlight relationship BACKWARDS. Hovering a claim raises the geometry that supports
//         it; clicking geometry names the claim it supports and offers to open it. The two directions
//         resolve through the same graph, so they cannot disagree about what backs what.
//
//         Provenance is shown at the same level as the measurement, not tucked underneath. A polygon's
//         area is only meaningful alongside the model and version that drew it — an area without a source
//         is exactly the unfalsifiable number this product exists to replace.
//
//         Anchored to a corner rather than to the feature. A card that chases the geometry covers the
//         thing being inspected, and moves under the pointer every time the camera drifts.

"use client";

import { Crosshair, X } from "lucide-react";

import { Chip } from "@/components/sharedUI/dumbComponent/Chip";
import { Button } from "@/components/ui/button";
import { VECTOR_PALETTE } from "@/lib/constants/layers";
import { formatCoordinates, formatPercentage } from "@/lib/formatters";

import type { Claim } from "../../types/evidence.types";
import type { EvidenceFeature, EvidenceLayer } from "../../types/layer.types";

interface FeatureInspectorProps {
  feature: EvidenceFeature;
  layer: EvidenceLayer;
  /** Claims this feature supports, resolved through the evidence graph. */
  claims: Claim[];
  onFocusClaim: (claim: Claim) => void;
  onClose: () => void;
}

/** A representative ground position for any of the three geometry kinds. */
function centroidOf(geometry: EvidenceFeature["geometry"]): { latitude: number; longitude: number } {
  if (geometry.type === "point") {
    return geometry.position;
  }

  if (geometry.type === "bbox") {
    return {
      latitude: (geometry.bounds.north + geometry.bounds.south) / 2,
      longitude: (geometry.bounds.east + geometry.bounds.west) / 2,
    };
  }

  // Mean of the ring's vertices. Not the true centroid of an irregular polygon, and deliberately not
  // presented as one — it is a place to fly to and a coordinate to quote, not a measurement.
  const total = geometry.ring.reduce(
    (sum, point) => ({
      latitude: sum.latitude + point.latitude,
      longitude: sum.longitude + point.longitude,
    }),
    { latitude: 0, longitude: 0 },
  );

  return {
    latitude: total.latitude / geometry.ring.length,
    longitude: total.longitude / geometry.ring.length,
  };
}

const GEOMETRY_LABEL: Record<EvidenceFeature["geometry"]["type"], string> = {
  polygon: "Polygon",
  point: "Point",
  bbox: "Bounding box",
};

export function FeatureInspector({
  feature,
  layer,
  claims,
  onFocusClaim,
  onClose,
}: FeatureInspectorProps) {
  const centroid = centroidOf(feature.geometry);
  const palette = VECTOR_PALETTE[layer.colorRampId];
  const vertexCount = feature.geometry.type === "polygon" ? feature.geometry.ring.length : null;

  return (
    <div className="pointer-events-auto w-72 rounded-md border border-border bg-surface-2/90 backdrop-blur-md">
      <header className="flex items-start gap-2 border-b border-border-soft px-3 py-2">
        <span
          className="mt-1 size-2.5 shrink-0 rounded-[2px] border"
          style={{ backgroundColor: `${palette.fill}55`, borderColor: palette.outline }}
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-xs font-medium text-foreground" title={feature.label}>
            {feature.label}
          </h2>
          <p className="truncate font-mono text-[10px] text-muted-foreground" title={layer.title}>
            {layer.title}
          </p>
        </div>
        <Button type="button" size="icon-sm" variant="ghost" aria-label="Close inspector" onClick={onClose}>
          <X />
        </Button>
      </header>

      <dl className="grid grid-cols-2 gap-x-3 gap-y-2 px-3 py-2.5">
        <Field label="Geometry">
          {GEOMETRY_LABEL[feature.geometry.type]}
          {vertexCount !== null ? ` · ${vertexCount} pts` : ""}
        </Field>
        <Field label="Centre">{formatCoordinates(centroid.latitude, centroid.longitude)}</Field>
        <Field label="Area">
          {feature.areaHectares === null ? "—" : `${feature.areaHectares.toFixed(2)} ha`}
        </Field>
        <Field label="Confidence">
          {/* Null is not zero. A model declining to assert a confidence is a different statement from
              one asserting no confidence, and collapsing them would misreport the evidence. */}
          {feature.confidence === null ? "not asserted" : formatPercentage(feature.confidence)}
        </Field>
      </dl>

      <div className="px-3 pb-2.5">
        <span className="aeris-technical">Magnitude</span>
        <div className="mt-1 flex items-center gap-2">
          <span className="h-1 flex-1 overflow-hidden rounded-full bg-surface-3">
            <span
              className="block h-full rounded-full bg-aeris-teal"
              style={{ width: `${Math.round(feature.magnitude * 100)}%` }}
            />
          </span>
          <span className="w-8 shrink-0 text-right font-mono text-[10px] tabular-nums text-muted-foreground">
            {formatPercentage(feature.magnitude)}
          </span>
        </div>
      </div>

      {/* The other direction of the spotlight: this geometry, and what it is evidence FOR. */}
      {claims.length > 0 ? (
        <section className="border-t border-border-soft px-3 py-2.5">
          <span className="aeris-technical">Supports</span>
          <ul className="mt-1 flex flex-col gap-1">
            {claims.map((claim) => (
              <li key={claim.id}>
                <button
                  type="button"
                  onClick={() => onFocusClaim(claim)}
                  className="flex w-full items-start gap-1.5 rounded-sm px-1 py-0.5 text-left transition-colors duration-fast hover:bg-aeris-teal/10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  <Crosshair className="mt-0.5 size-3 shrink-0 text-aeris-teal" aria-hidden="true" />
                  <span className="min-w-0 flex-1 text-[11px] leading-relaxed text-foreground">
                    {claim.text}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <footer className="flex items-center gap-1.5 border-t border-border-soft px-3 py-2">
        <Chip tone="neutral">{layer.provenance.modelId}</Chip>
        <span className="truncate font-mono text-[10px] text-muted-foreground">
          v{layer.provenance.modelVersion}
          {layer.provenance.confidence !== null
            ? ` · ${formatPercentage(layer.provenance.confidence)}`
            : ""}
        </span>
      </footer>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="aeris-technical">{label}</dt>
      <dd className="truncate font-mono text-[11px] text-foreground">{children}</dd>
    </div>
  );
}

// features/investigation/hooks/use-reference-layers.ts — context layers, and where they sit in the stack.
//
// what  : Turns the reference catalogue plus the operator's visibility and opacity choices into stage
//         layer descriptors, split into the ones that go under the imagery and the ones that go over it.
// where : Called by InvestigationScreen; its two lists bracket the scene layers handed to the stage.
// how   : Reference layers are pushed as plain stage layers with NO provenance block, because nothing
//         asserted them — a coastline is not a finding and must not be able to look like one. That is the
//         same reason scrubbed timeline imagery carries no provenance either.
//
//         The split is the substance. Draw order in the stage is descriptor order, so "under" and "over"
//         are not a styling preference: shaded relief beneath the imagery gives it landform to sit on,
//         while boundaries and roads beneath the imagery are simply invisible. One list would force both
//         to be wrong for one of them.
//
//         Bounds are deliberately NOT set. These are global products, and constraining them to the area of
//         interest would blank the context exactly when the operator pans out to ask where they are.

"use client";

import { useMemo } from "react";

import type { StageLayer } from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";
import { REFERENCE_LAYERS } from "@/lib/constants/reference-layers";

import { useInvestigationStore } from "../store/investigation-store";

interface ReferenceLayerSet {
  /** Drawn beneath the operator's imagery — ground for it to sit on. */
  under: StageLayer[];
  /** Drawn above the imagery — annotation that would otherwise be buried. */
  over: StageLayer[];
}

export function useReferenceLayers(): ReferenceLayerSet {
  const referenceLayerState = useInvestigationStore((state) => state.referenceLayerState);

  return useMemo(() => {
    const under: StageLayer[] = [];
    const over: StageLayer[] = [];

    for (const definition of REFERENCE_LAYERS) {
      const operatorState = referenceLayerState[definition.id];
      const isVisible = operatorState?.isVisible ?? definition.isVisibleByDefault;

      // A hidden reference layer is not built at all rather than built and hidden. These are global
      // tilesets; leaving one resident and invisible keeps it requesting tiles on every pan for nothing.
      if (!isVisible) {
        continue;
      }

      const descriptor: StageLayer = {
        id: definition.id,
        kind: "raster-tiles",
        renderMode: "draped",
        title: definition.title,
        colorRampId: definition.colorRampId,
        opacity: operatorState?.opacity ?? definition.defaultOpacity,
        isVisible: true,
        comparatorSide: "both",
        tileUrlTemplate: definition.tileUrlTemplate,
        attribution: definition.attribution,
        bounds: null,
        minimumZoom: 0,
        maximumZoom: definition.maximumZoom,
        features: [],
      };

      if (definition.stackPosition === "under-imagery") {
        under.push(descriptor);
      } else {
        over.push(descriptor);
      }
    }

    return { under, over };
  }, [referenceLayerState]);
}

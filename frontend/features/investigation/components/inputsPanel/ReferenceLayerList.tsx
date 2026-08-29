// features/investigation/components/inputsPanel/ReferenceLayerList.tsx — the context you read the scene against.
//
// what  : Terrain shading, administrative boundaries and the transport network, each with a switch and an
//         opacity control, and a line saying what it is for.
// where : A section of InputsPanel, beneath the evidence layers.
// how   : Deliberately a DIFFERENT control from the evidence rows above it, and it should stay that way.
//         An evidence row states the model, the version and the confidence behind what it draws, because
//         something asserted it. A reference row states a source and a purpose, because nothing did — a
//         district boundary is a fact about administration, not a finding about the ground.
//
//         Making them look alike would be the mistake: an operator scanning the panel has to be able to
//         tell at a glance which layers are claims the system is making and which are the map it made them
//         against. That distinction is the product.
//
//         Everything starts off. Context is what you reach for when a specific question needs it — which
//         district is this, can a lorry get there — and switching all of it on by default would bury the
//         imagery under annotation before the operator has asked anything.

"use client";

import { Eye, EyeOff } from "lucide-react";

import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { REFERENCE_LAYERS } from "@/lib/constants/reference-layers";
import { formatPercentage } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import { useInvestigationStore } from "../../store/investigation-store";

export function ReferenceLayerList() {
  const referenceLayerState = useInvestigationStore((state) => state.referenceLayerState);
  const setVisibility = useInvestigationStore((state) => state.setReferenceLayerVisibility);
  const setOpacity = useInvestigationStore((state) => state.setReferenceLayerOpacity);

  return (
    <ul className="flex flex-col gap-1">
      {REFERENCE_LAYERS.map((definition) => {
        const state = referenceLayerState[definition.id];
        const isVisible = state?.isVisible ?? definition.isVisibleByDefault;
        const opacity = state?.opacity ?? definition.defaultOpacity;
        const VisibilityIcon = isVisible ? Eye : EyeOff;

        return (
          <li
            key={definition.id}
            className={cn(
              "rounded-md border border-border-soft bg-surface-2/30 px-2 py-1.5 transition-opacity duration-base",
              !isVisible && "opacity-60",
            )}
          >
            <div className="flex items-center gap-1.5">
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                aria-pressed={isVisible}
                aria-label={isVisible ? `Hide ${definition.title}` : `Show ${definition.title}`}
                onClick={() => setVisibility(definition.id, !isVisible)}
              >
                <VisibilityIcon className={isVisible ? "text-aeris-blue" : undefined} />
              </Button>

              <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                {definition.title}
              </span>

              {isVisible ? (
                <span className="w-8 shrink-0 text-right font-mono text-[10px] tabular-nums text-muted-foreground">
                  {formatPercentage(opacity)}
                </span>
              ) : null}
            </div>

            {isVisible ? (
              <Slider
                value={[opacity]}
                min={0}
                max={1}
                step={0.05}
                onValueChange={([next]) => setOpacity(definition.id, next)}
                aria-label={`${definition.title} opacity`}
                className="mt-1.5 pl-1"
              />
            ) : (
              <p className="mt-0.5 pl-1 text-[10px] leading-relaxed text-muted-foreground/70">
                {definition.description}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

// features/investigation/components/inputsPanel/BasemapSwitcher.tsx — the basemap source selector.
//
// what  : A compact row of basemap choices at the bottom of the Layers tab, letting the operator choose
//         what sits beneath the evidence layers — satellite, streets, topographic, dark or nothing.
// where : Rendered inside LayersPanel after the reference layers section.
// how   : The active basemap id is stored in the investigation store as view state. Each option is a
//         small labelled tile preview. The catalogue is read from lib/constants/basemaps.ts, so adding
//         a new basemap never touches this component.

"use client";

import { Map } from "lucide-react";

import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { cn } from "@/lib/utils";
import { BASEMAPS, type BasemapDefinition } from "@/lib/constants/basemaps";
import { useInvestigationStore } from "../../store/investigation-store";
import { useState } from "react";

function BasemapOption({
  basemap,
  isActive,
  onSelect,
}: {
  basemap: BasemapDefinition;
  isActive: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex flex-col items-center gap-1 rounded-md border p-1.5 transition-all",
        "hover:border-aeris-teal/50 hover:bg-surface-2",
        isActive
          ? "border-aeris-teal bg-surface-2 ring-1 ring-aeris-teal/30"
          : "border-border-soft bg-surface/50",
      )}
      title={basemap.description}
    >
      <div
        className={cn(
          "flex h-8 w-12 items-center justify-center rounded-sm text-[9px] font-medium",
          basemap.isDark ? "bg-zinc-800 text-zinc-300" : "bg-zinc-200 text-zinc-700",
        )}
      >
        {basemap.id === "none" ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          <Map className="size-3.5 opacity-60" />
        )}
      </div>
      <span className="text-[10px] text-muted-foreground">{basemap.label}</span>
    </button>
  );
}

export function BasemapSwitcher() {
  const [isExpanded, setIsExpanded] = useState(false);
  const activeBasemapId = useInvestigationStore((state) => state.activeBasemapId);
  const setActiveBasemapId = useInvestigationStore((state) => state.setActiveBasemapId);

  return (
    <section className="flex flex-col border-t border-border-soft pt-2">
      <SectionHeader
        title="Basemap"
        isExpanded={isExpanded}
        onToggle={() => setIsExpanded((c) => !c)}
        trailing={
          <span className="font-mono text-[10px] text-muted-foreground">
            {BASEMAPS.find((b) => b.id === activeBasemapId)?.label ?? "Satellite"}
          </span>
        }
      />

      {isExpanded ? (
        <div className="flex flex-wrap gap-1.5 px-2 pb-2">
          {BASEMAPS.map((basemap) => (
            <BasemapOption
              key={basemap.id}
              basemap={basemap}
              isActive={activeBasemapId === basemap.id}
              onSelect={() => setActiveBasemapId(basemap.id)}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

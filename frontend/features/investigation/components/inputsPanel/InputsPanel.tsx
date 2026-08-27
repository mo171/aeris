// features/investigation/components/inputsPanel/InputsPanel.tsx — the left zone: inputs and evidence layers.
//
// what  : Two collapsible sections — the scenes attached to this investigation, and the evidence layers
//         produced from them.
// where : The left zone of InvestigationScreen.
// how   : The two sections compete for the same vertical space, and which one matters depends entirely on
//         what the operator is doing — checking what went in, or controlling what came out. Each claims
//         flex space only while expanded, so collapsing one hands its height to the other rather than
//         leaving both cramped. That is the same fix Mission Command needed, applied before it bites here.
//
//         Layers are presented as evidence rather than as a generic layer tree: every row states the model
//         and version behind it. See EvidenceLayerRow for why that framing is load-bearing.

"use client";

import { Layers, Satellite } from "lucide-react";
import { useState } from "react";

import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { EmptyState } from "@/components/sharedUI/functionalComponent/feedback/EmptyState";
import { cn } from "@/lib/utils";

import { useInvestigationStore } from "../../store/investigation-store";
import type { InvestigationSceneSlot } from "../../types/investigation.types";
import type { EvidenceLayer } from "../../types/layer.types";
import { EvidenceLayerRow } from "./EvidenceLayerRow";
import { SceneSlotCard } from "./SceneSlotCard";

interface InputsPanelProps {
  sceneSlots: InvestigationSceneSlot[];
  layers: EvidenceLayer[];
  onFocusScene: (slot: InvestigationSceneSlot) => void;
}

export function InputsPanel({ sceneSlots, layers, onFocusScene }: InputsPanelProps) {
  const [isInputsExpanded, setIsInputsExpanded] = useState(true);
  const [isLayersExpanded, setIsLayersExpanded] = useState(true);

  const visibilityOverrides = useInvestigationStore((state) => state.layerVisibilityOverrides);
  const soloLayerId = useInvestigationStore((state) => state.soloLayerId);
  const setLayerVisibility = useInvestigationStore((state) => state.setLayerVisibility);
  const setLayerOpacity = useInvestigationStore((state) => state.setLayerOpacity);
  const toggleSoloLayer = useInvestigationStore((state) => state.toggleSoloLayer);

  // Scene rasters are layers too, so their visibility toggles run through exactly the same override map.
  // A scene and a change mask being hidden by two different mechanisms is how a layer stack starts lying.
  const isSceneVisible = (slot: InvestigationSceneSlot) =>
    soloLayerId === null ? (visibilityOverrides[slot.layerId] ?? true) : soloLayerId === slot.layerId;

  const evidenceLayers = layers.filter(
    (layer) => !sceneSlots.some((slot) => slot.layerId === layer.id),
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <section
        className={cn("flex flex-col", isInputsExpanded ? "min-h-0 flex-1" : "shrink-0")}
      >
        <SectionHeader
          title="Inputs"
          isExpanded={isInputsExpanded}
          onToggle={() => setIsInputsExpanded((current) => !current)}
          trailing={
            <span className="font-mono text-[10px] text-muted-foreground">{sceneSlots.length}</span>
          }
        />

        {isInputsExpanded ? (
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            {sceneSlots.length === 0 ? (
              <EmptyState icon={Satellite} title="No scenes attached" />
            ) : (
              <div className="flex flex-col gap-1.5">
                {sceneSlots.map((slot) => (
                  <SceneSlotCard
                    key={slot.sceneId}
                    slot={slot}
                    isVisible={isSceneVisible(slot)}
                    onToggleVisibility={() =>
                      setLayerVisibility(slot.layerId, !isSceneVisible(slot))
                    }
                    onFocus={() => onFocusScene(slot)}
                  />
                ))}
              </div>
            )}
          </div>
        ) : null}
      </section>

      <section
        className={cn(
          "flex flex-col border-t border-border-soft pt-2",
          isLayersExpanded ? "min-h-0 flex-1" : "shrink-0",
        )}
      >
        <SectionHeader
          title="Evidence Layers"
          isExpanded={isLayersExpanded}
          onToggle={() => setIsLayersExpanded((current) => !current)}
          trailing={
            <span className="font-mono text-[10px] text-muted-foreground">
              {evidenceLayers.length}
            </span>
          }
        />

        {isLayersExpanded ? (
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            {evidenceLayers.length === 0 ? (
              <EmptyState
                icon={Layers}
                title="No evidence yet"
                description="Ask a question and the layers AERIS produces will appear here."
              />
            ) : (
              <div className="flex flex-col gap-1.5">
                {evidenceLayers.map((layer) => (
                  <EvidenceLayerRow
                    key={layer.id}
                    layer={layer}
                    isSoloed={soloLayerId === layer.id}
                    onToggleVisibility={() => setLayerVisibility(layer.id, !layer.isVisible)}
                    onToggleSolo={() => toggleSoloLayer(layer.id)}
                    onOpacityChange={(opacity) => setLayerOpacity(layer.id, opacity)}
                  />
                ))}
              </div>
            )}
          </div>
        ) : null}
      </section>
    </div>
  );
}

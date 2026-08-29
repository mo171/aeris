// features/investigation/components/inputsPanel/InputsPanel.tsx — the left zone: inputs and evidence layers.
//
// what  : Five collapsible sections — the scenes bound to comparison roles, the acquisition history over
//         the area, the regions the operator has drawn, the evidence layers produced, and the reference
//         context those are read against.
// where : The left zone of InvestigationScreen.
// how   : The sections compete for the same vertical space, and which one matters depends entirely on
//         what the operator is doing — checking what went in, or controlling what came out. Each claims
//         flex space only while expanded, so collapsing one hands its height to the other rather than
//         leaving both cramped. That is the same fix Mission Command needed, applied before it bites here.
//
//         Layers are presented as evidence rather than as a generic layer tree: every row states the model
//         and version behind it. See EvidenceLayerRow for why that framing is load-bearing.

"use client";

import { History, Layers, Satellite } from "lucide-react";
import { useState } from "react";

import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { EmptyState } from "@/components/sharedUI/functionalComponent/feedback/EmptyState";
import { cn } from "@/lib/utils";

import { useInvestigationStore } from "../../store/investigation-store";
import type {
  Acquisition,
  InvestigationSceneSlot,
  SceneRole,
} from "../../types/investigation.types";
import type { EvidenceLayer } from "../../types/layer.types";
import type { StageDrawnRegion } from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";

import { REFERENCE_LAYERS } from "@/lib/constants/reference-layers";

import { AcquisitionList } from "./AcquisitionList";
import { EvidenceLayerRow } from "./EvidenceLayerRow";
import { ReferenceLayerList } from "./ReferenceLayerList";
import { RegionList } from "./RegionList";
import { SceneSlotCard } from "./SceneSlotCard";

interface InputsPanelProps {
  sceneSlots: InvestigationSceneSlot[];
  acquisitions: Acquisition[];
  roleBySceneId: Record<string, SceneRole>;
  openSceneIds: readonly string[];
  onOpenScene: (sceneId: string) => void;
  layers: EvidenceLayer[];
  regions: readonly StageDrawnRegion[];
  activeRegionId: string | null;
  onSelectRegion: (regionId: string | null) => void;
  onRemoveRegion: (regionId: string) => void;
  onFocusScene: (slot: InvestigationSceneSlot) => void;
}

export function InputsPanel({
  sceneSlots,
  acquisitions,
  roleBySceneId,
  openSceneIds,
  onOpenScene,
  layers,
  regions,
  activeRegionId,
  onSelectRegion,
  onRemoveRegion,
  onFocusScene,
}: InputsPanelProps) {
  const [isInputsExpanded, setIsInputsExpanded] = useState(true);
  // Collapsed by default: the history matters when choosing scenes, not while reading an answer.
  const [isHistoryExpanded, setIsHistoryExpanded] = useState(false);
  const [isRegionsExpanded, setIsRegionsExpanded] = useState(true);
  const [isLayersExpanded, setIsLayersExpanded] = useState(true);
  // Collapsed by default: context is what an operator reaches for when a specific question needs it.
  const [isReferenceExpanded, setIsReferenceExpanded] = useState(false);

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
    <div className="flex h-full min-h-0 flex-1 flex-col">
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
          isHistoryExpanded ? "min-h-0 flex-1" : "shrink-0",
        )}
      >
        <SectionHeader
          title="Acquisition History"
          isExpanded={isHistoryExpanded}
          onToggle={() => setIsHistoryExpanded((current) => !current)}
          trailing={
            <span className="font-mono text-[10px] text-muted-foreground">
              {acquisitions.length}
            </span>
          }
        />

        {isHistoryExpanded ? (
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            {acquisitions.length === 0 ? (
              <EmptyState icon={History} title="No archive coverage" />
            ) : (
              <AcquisitionList
                acquisitions={acquisitions}
                roleBySceneId={roleBySceneId}
                openSceneIds={openSceneIds}
                onOpenScene={onOpenScene}
              />
            )}
          </div>
        ) : null}
      </section>

      {/* Regions only claim space once something has been drawn — an empty section between two useful
          ones is just a line the operator has to read past. */}
      {regions.length > 0 ? (
        <section
          className={cn(
            "flex flex-col border-t border-border-soft pt-2",
            isRegionsExpanded ? "min-h-0 flex-1" : "shrink-0",
          )}
        >
          <SectionHeader
            title="Areas of Interest"
            isExpanded={isRegionsExpanded}
            onToggle={() => setIsRegionsExpanded((current) => !current)}
            trailing={
              <span className="font-mono text-[10px] text-muted-foreground">{regions.length}</span>
            }
          />

          {isRegionsExpanded ? (
            <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
              <RegionList
                regions={regions}
                activeRegionId={activeRegionId}
                onSelect={onSelectRegion}
                onRemove={onRemoveRegion}
              />
            </div>
          ) : null}
        </section>
      ) : null}

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

      {/*
        Context, kept visually distinct from the evidence above it. An evidence row names the model that
        asserted it; a reference row names a source and a purpose, because nothing asserted a coastline.
      */}
      <section className={cn("flex flex-col", isReferenceExpanded ? "min-h-0 flex-1" : "shrink-0")}>
        <SectionHeader
          title="Reference"
          isExpanded={isReferenceExpanded}
          onToggle={() => setIsReferenceExpanded((current) => !current)}
          trailing={
            <span className="font-mono text-[10px] text-muted-foreground">
              {REFERENCE_LAYERS.length}
            </span>
          }
        />

        {isReferenceExpanded ? (
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            <ReferenceLayerList />
          </div>
        ) : null}
      </section>
    </div>
  );
}

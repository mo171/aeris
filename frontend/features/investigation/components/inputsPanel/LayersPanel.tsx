"use client";

import { DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors, DragEndEvent } from "@dnd-kit/core";
import { arrayMove, SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy, useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Layers, Lock, Edit2 } from "lucide-react";
import { useState, useMemo } from "react";

import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { EmptyState } from "@/components/sharedUI/functionalComponent/feedback/EmptyState";
import { cn } from "@/lib/utils";
import { sectionForOverlay, OVERLAY_SECTIONS } from "@/lib/constants/overlays";
import { REFERENCE_LAYERS } from "@/lib/constants/reference-layers";

import { EvidenceLayerRow } from "./EvidenceLayerRow";
import { ReferenceLayerList } from "./ReferenceLayerList";
import type { EvidenceLayer } from "../../types/layer.types";
import { useInvestigationStore } from "../../store/investigation-store";
import type { InvestigationSceneSlot } from "../../types/investigation.types";

interface LayersPanelProps {
  sensorsSection?: React.ReactNode;
  layers: EvidenceLayer[];
  sceneSlots: InvestigationSceneSlot[];
}

function SortableLayerItem({
  layer,
  isSoloed,
  onToggleVisibility,
  onToggleSolo,
  onOpacityChange,
  isImmutable,
}: {
  layer: EvidenceLayer;
  isSoloed: boolean;
  onToggleVisibility: () => void;
  onToggleSolo: () => void;
  onOpacityChange: (opacity: number) => void;
  isImmutable: boolean;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: layer.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 1 : 0,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "relative rounded-sm border border-transparent transition-colors group bg-background/50",
        isDragging && "opacity-50 ring-2 ring-aeris-teal ring-offset-1 bg-surface-2",
      )}
      {...attributes}
      {...listeners}
    >
      <EvidenceLayerRow
        layer={layer}
        isSoloed={isSoloed}
        onToggleVisibility={onToggleVisibility}
        onToggleSolo={onToggleSolo}
        onOpacityChange={onOpacityChange}
      />
      
      {/* Visual lock for immutable layers, edit for regions. Placed on hover or as a persistent badge. */}
      <div className="absolute right-1 top-2 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100 bg-surface border border-border/50 rounded-full p-1 shadow-sm pointer-events-none">
        {isImmutable ? <Lock className="size-3 text-aeris-amber" /> : <Edit2 className="size-3 text-aeris-teal" />}
      </div>
    </div>
  );
}

export function LayersPanel({
  sensorsSection,
  layers,
  sceneSlots,
}: LayersPanelProps) {
  const [isLayersExpanded, setIsLayersExpanded] = useState(true);
  const [isReferenceExpanded, setIsReferenceExpanded] = useState(false);

  const soloLayerId = useInvestigationStore((state) => state.soloLayerId);
  const setLayerVisibility = useInvestigationStore((state) => state.setLayerVisibility);
  const setLayerOpacity = useInvestigationStore((state) => state.setLayerOpacity);
  const toggleSoloLayer = useInvestigationStore((state) => state.toggleSoloLayer);
  const setLayerOrder = useInvestigationStore((state) => state.setLayerOrder);
  const currentLayerOrder = useInvestigationStore((state) => state.layerOrder);

  const producedLayers = useMemo(
    () => layers.filter((layer) => !sceneSlots.some((slot) => slot.layerId === layer.id)),
    [layers, sceneSlots]
  );

  const evidenceLayers = useMemo(
    () => producedLayers.filter((layer) => sectionForOverlay(layer.overlayId) !== "masks"),
    [producedLayers]
  );

  const maskLayers = useMemo(
    () => producedLayers.filter((layer) => sectionForOverlay(layer.overlayId) === "masks"),
    [producedLayers]
  );

  const sortableLayers = useMemo(() => [...evidenceLayers, ...maskLayers], [evidenceLayers, maskLayers]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const activeIndex = layers.findIndex((l) => l.id === active.id);
      const overIndex = layers.findIndex((l) => l.id === over.id);
      if (activeIndex !== -1 && overIndex !== -1) {
        // The list we are reordering is the full layers array.
        // Wait, the store's layerOrder should probably contain all layers.
        // If it's not set yet, use the initial order.
        const baseOrder = currentLayerOrder ?? layers.map((l) => l.id);
        const aIdx = baseOrder.indexOf(active.id as string);
        const oIdx = baseOrder.indexOf(over.id as string);
        
        if (aIdx !== -1 && oIdx !== -1) {
          const newOrder = arrayMove(baseOrder, aIdx, oIdx);
          setLayerOrder(newOrder);
        }
      }
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      {sensorsSection}

      <section
        className={cn(
          "flex flex-col border-t border-border-soft pt-2",
          isLayersExpanded ? "min-h-0 flex-1" : "shrink-0",
        )}
      >
        <SectionHeader
          title="Evidence & Masks"
          isExpanded={isLayersExpanded}
          onToggle={() => setIsLayersExpanded((current) => !current)}
          trailing={
            <span className="font-mono text-[10px] text-muted-foreground">
              {sortableLayers.length}
            </span>
          }
        />

        {isLayersExpanded ? (
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            {sortableLayers.length === 0 ? (
              <EmptyState
                icon={Layers}
                title="No layers yet"
                description="Layers produced by analysis will appear here."
              />
            ) : (
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={sortableLayers.map((l) => l.id)} strategy={verticalListSortingStrategy}>
                  <div className="flex flex-col gap-1.5">
                    {sortableLayers.map((layer) => {
                      // We consider regions (operator drawn) editable, and model findings immutable.
                      // Regions do not have provenance.modelId or it's a specific kind.
                      // But wait, the drawn regions are NOT in this list. They are in RegionList.
                      // Wait, if Regions are in RegionList in InputsTab, then what are the editable layers here?
                      // The prompt says "Add visual locks (🔒) for immutable evidence vs editable (✎) layers."
                      // If there are no editable layers here, maybe drawn regions ARE drawn as layers? No, they have regions.
                      // Let's assume drawn regions ARE in layers, wait, are they?
                      // In use-scene-stage-binding, regions are passed separately to stage.drawRegions.
                      // Wait! The user says "Add visual locks (🔒) for immutable evidence vs editable (✎) layers."
                      // So all model-produced evidence is immutable.
                      const isImmutable = !!layer.provenance;
                      return (
                        <SortableLayerItem
                          key={layer.id}
                          layer={layer}
                          isSoloed={soloLayerId === layer.id}
                          onToggleVisibility={() => setLayerVisibility(layer.id, !layer.isVisible)}
                          onToggleSolo={() => toggleSoloLayer(layer.id)}
                          onOpacityChange={(opacity) => setLayerOpacity(layer.id, opacity)}
                          isImmutable={isImmutable}
                        />
                      );
                    })}
                  </div>
                </SortableContext>
              </DndContext>
            )}
          </div>
        ) : null}
      </section>

      <section className={cn("flex flex-col border-t border-border-soft pt-2", isReferenceExpanded ? "min-h-0 flex-1" : "shrink-0")}>
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

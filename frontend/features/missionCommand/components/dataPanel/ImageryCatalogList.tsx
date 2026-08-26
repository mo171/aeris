// features/missionCommand/components/dataPanel/ImageryCatalogList.tsx — the searchable scene catalogue.
//
// what  : Search field plus a virtualised, infinitely-scrolling list of scenes with loading, empty and
//         error states.
// where : The middle section of the Data & Context panel.
// how   : This is the panel most exposed to data volume — an operator's scene library is unbounded — so it
//         is virtualised and cursor-paginated end to end. The row count in the header reads from the
//         server's total rather than the loaded length, so it tells the truth about the catalogue rather
//         than about what happens to be in memory.

"use client";

import { ImageOff, LoaderCircle, Search } from "lucide-react";
import { useCallback } from "react";

import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { VirtualizedList } from "@/components/sharedUI/functionalComponent/dataDisplay/VirtualizedList";
import { EmptyState } from "@/components/sharedUI/functionalComponent/feedback/EmptyState";
import { ErrorState } from "@/components/sharedUI/functionalComponent/feedback/ErrorState";
import { PanelSkeleton } from "@/components/sharedUI/functionalComponent/feedback/PanelSkeleton";

import { useImageryCatalog } from "../../hooks/use-imagery-catalog";
import { useMissionCommandStore } from "../../store/mission-command-store";
import type { ImageryScene } from "../../types/imagery.types";
import { ImageryCatalogItem } from "./ImageryCatalogItem";

/** Approximate rendered height of one scene row; the virtualiser measures the real value after mount. */
const ESTIMATED_ROW_HEIGHT = 92;

interface ImageryCatalogListProps {
  onLocateScene: (scene: ImageryScene) => void;
}

export function ImageryCatalogList({ onLocateScene }: ImageryCatalogListProps) {
  const {
    scenes,
    totalCount,
    searchTerm,
    setSearchTerm,
    isLoading,
    isFetchingNextPage,
    fetchNextPage,
    error,
    refetch,
  } = useImageryCatalog();

  const selectedSceneIds = useMissionCommandStore((state) => state.selectedSceneIds);
  const toggleSceneSelection = useMissionCommandStore((state) => state.toggleSceneSelection);

  const renderScene = useCallback(
    (scene: ImageryScene) => (
      <ImageryCatalogItem
        scene={scene}
        isSelected={selectedSceneIds.includes(scene.id)}
        onToggleSelect={toggleSceneSelection}
        onLocate={onLocateScene}
      />
    ),
    [onLocateScene, selectedSceneIds, toggleSceneSelection],
  );

  return (
    <section className="flex min-h-0 flex-1 flex-col border-t border-border-soft pt-2">
      <SectionHeader
        title="Imagery catalogue"
        trailing={
          totalCount !== null ? (
            <span className="font-mono text-[10px] text-muted-foreground">
              {totalCount.toLocaleString()}
            </span>
          ) : null
        }
      />

      <div className="px-3 pt-1.5 pb-2">
        <label className="flex h-7 items-center gap-2 rounded-md border border-border bg-surface-2/60 px-2 transition-colors duration-fast focus-within:border-aeris-teal/50">
          <Search className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <input
            type="search"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Filter by place, platform or modality"
            className="w-full bg-transparent text-[11px] text-foreground outline-none placeholder:text-muted-foreground/70"
            aria-label="Filter imagery catalogue"
          />
        </label>
      </div>

      {error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : isLoading ? (
        <PanelSkeleton rowCount={5} rowHeight={ESTIMATED_ROW_HEIGHT - 8} />
      ) : scenes.length === 0 ? (
        <EmptyState
          icon={ImageOff}
          title={searchTerm.length > 0 ? "No matching scenes" : "No imagery yet"}
          description={
            searchTerm.length > 0
              ? "Try a different place name, platform or modality."
              : "Upload a GeoTIFF above to start an investigation."
          }
        />
      ) : (
        <VirtualizedList
          items={scenes}
          estimateItemHeight={ESTIMATED_ROW_HEIGHT}
          getItemKey={(scene) => scene.id}
          renderItem={renderScene}
          onEndReached={fetchNextPage}
          footer={
            isFetchingNextPage ? (
              <div className="flex items-center justify-center gap-2 py-3">
                <LoaderCircle
                  className="size-3 animate-spin text-aeris-teal"
                  aria-hidden="true"
                />
                <span className="font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
                  Loading more scenes
                </span>
              </div>
            ) : null
          }
        />
      )}
    </section>
  );
}

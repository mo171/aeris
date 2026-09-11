// features/missionCommand/components/dataPanel/ActiveMissionsList.tsx — saved and monitoring missions.
//
// what  : A virtualised list of missions with status, confidence, alert count and next scheduled run.
// where : The lower section of the Data & Context panel.
// how   : Also virtualised — a monitoring-heavy account accumulates hundreds of missions, and the panel
//         must cost the same whether there are ten or ten thousand. Selecting a mission flies the globe to
//         its area of interest, which is the link that makes the left panel and the centre canvas feel
//         like one instrument rather than two widgets sharing a screen.

"use client";

import { LoaderCircle, Radar, FileSearch } from "lucide-react";
import Link from "next/link";
import { memo, useCallback } from "react";

import { Chip, type ChipTone } from "@/components/sharedUI/dumbComponent/Chip";
import { GlowDot, type GlowDotTone } from "@/components/sharedUI/dumbComponent/GlowDot";
import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { VirtualizedList } from "@/components/sharedUI/functionalComponent/dataDisplay/VirtualizedList";
import { EmptyState } from "@/components/sharedUI/functionalComponent/feedback/EmptyState";
import { ErrorState } from "@/components/sharedUI/functionalComponent/feedback/ErrorState";
import { PanelSkeleton } from "@/components/sharedUI/functionalComponent/feedback/PanelSkeleton";
import { formatRelativeTime } from "@/lib/formatters";
import { buildRoute } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";

import { useActiveMissions } from "../../hooks/use-active-missions";
import { useMissionCommandStore } from "../../store/mission-command-store";
import type { Mission, MissionStatus } from "../../types/mission.types";

const ESTIMATED_ROW_HEIGHT = 74;

const STATUS_TONE: Record<MissionStatus, GlowDotTone> = {
  alert: "red",
  active: "teal",
  monitoring: "blue",
  archived: "neutral",
};

const STATUS_CHIP_TONE: Record<MissionStatus, ChipTone> = {
  alert: "red",
  active: "teal",
  monitoring: "blue",
  archived: "neutral",
};

interface ActiveMissionsListProps {
  onLocateMission: (mission: Mission) => void;
  isExpanded: boolean;
  onToggleExpanded: () => void;
}

export function ActiveMissionsList({
  onLocateMission,
  isExpanded,
  onToggleExpanded,
}: ActiveMissionsListProps) {
  const { missions, totalCount, isLoading, isFetchingNextPage, fetchNextPage, error, refetch } =
    useActiveMissions();

  const focusedMissionId = useMissionCommandStore((state) => state.focusedMissionId);

  const renderMission = useCallback(
    (mission: Mission) => (
      <MissionRow
        mission={mission}
        isFocused={mission.id === focusedMissionId}
        onSelect={onLocateMission}
      />
    ),
    [focusedMissionId, onLocateMission],
  );

  return (
    <section
      className={cn(
        "flex flex-col border-t border-border-soft pt-2",
        // Same rule as the catalogue: claim flex space only while showing content. The previous fixed
        // 38% basis combined with the catalogue's flex-1 could exceed the panel height, which is what
        // made the sections render on top of each other.
        isExpanded ? "min-h-0 flex-1" : "shrink-0",
      )}
    >
      <SectionHeader
        title="Missions"
        isExpanded={isExpanded}
        onToggle={onToggleExpanded}
        trailing={
          totalCount !== null ? (
            <span className="font-mono text-[10px] text-muted-foreground">{totalCount}</span>
          ) : null
        }
      />

      {!isExpanded ? null : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : isLoading ? (
        <PanelSkeleton rowCount={3} rowHeight={ESTIMATED_ROW_HEIGHT - 8} />
      ) : missions.length === 0 ? (
        <EmptyState
          icon={Radar}
          title="No missions yet"
          description="Save an investigation as a mission to monitor an area continuously."
        />
      ) : (
        <VirtualizedList
          items={missions}
          estimateItemHeight={ESTIMATED_ROW_HEIGHT}
          getItemKey={(mission) => mission.id}
          renderItem={renderMission}
          onEndReached={fetchNextPage}
          className="pt-1"
          footer={
            isFetchingNextPage ? (
              <div className="flex items-center justify-center py-2">
                <LoaderCircle className="size-3 animate-spin text-aeris-teal" aria-hidden="true" />
              </div>
            ) : null
          }
        />
      )}
    </section>
  );
}

interface MissionRowProps {
  mission: Mission;
  isFocused: boolean;
  onSelect: (mission: Mission) => void;
}

const MissionRow = memo(function MissionRow({ mission, isFocused, onSelect }: MissionRowProps) {
  return (
    <div className="px-2 pb-1.5 group">
      <div
        role="button"
        tabIndex={0}
        onClick={() => onSelect(mission)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect(mission);
          }
        }}
        aria-pressed={isFocused}
        className={cn(
          "relative w-full rounded-md border px-2.5 py-2 text-left transition-colors duration-fast cursor-default",
          isFocused
            ? "border-aeris-teal/55 bg-aeris-teal/[0.08]"
            : "border-border-soft bg-surface-2/40 hover:border-border hover:bg-surface-3/50",
        )}
      >
        <div className="flex items-center gap-2 pr-6">
          <GlowDot tone={STATUS_TONE[mission.status]} isPulsing={mission.status === "alert"} />
          <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-foreground">
            {mission.name}
          </span>
          {mission.openAlertCount > 0 ? (
            <Chip tone="red">{mission.openAlertCount} alert</Chip>
          ) : null}
        </div>

        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          <Chip tone={STATUS_CHIP_TONE[mission.status]}>{mission.status}</Chip>
          {mission.confidence !== null ? (
            <Chip title="Confidence of the most recent run">
              {Math.round(mission.confidence * 100)}%
            </Chip>
          ) : null}
          <Chip>{mission.sceneCount} scenes</Chip>
        </div>

        <div className="mt-1 flex items-center justify-between">
          <p className="truncate font-mono text-[9px] tracking-wide text-muted-foreground/75 uppercase">
            {mission.nextRunAt
              ? `Next run ${formatRelativeTime(mission.nextRunAt)}`
              : mission.lastRunAt
                ? `Last run ${formatRelativeTime(mission.lastRunAt)}`
                : "Not yet run"}
          </p>
          
          <Link
            href={buildRoute.evidenceAudit(mission.name)}
            onClick={(e) => e.stopPropagation()}
            title="Audit this mission's evidence"
            className="flex items-center gap-1.5 rounded-sm px-1.5 py-0.5 opacity-0 transition-opacity hover:bg-surface-4 focus-visible:opacity-100 group-hover:opacity-100"
          >
            <span className="font-mono text-[9px] uppercase tracking-wide text-aeris-teal">Audit</span>
            <FileSearch className="size-3 text-aeris-teal" />
          </Link>
        </div>
      </div>
    </div>
  );
});

"use client";

import { AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { useActiveMissions } from "../../hooks/use-active-missions";
import type { Mission } from "../../types/mission.types";

export function AlertsStrip() {
  const { missions, isLoading } = useActiveMissions();
  const [isExpanded, setIsExpanded] = useState(true);

  // We only show missions that are in 'alert' status
  const alerts = missions.filter((mission: Mission) => mission.status === "alert") || [];

  if (isLoading || alerts.length === 0) {
    return null; // Hide the strip if there are no alerts or still loading
  }

  return (
    <div className="flex shrink-0 flex-col border-t border-border-soft bg-destructive/10">
      <button
        type="button"
        className="flex items-center gap-2 px-3 py-2 text-xs font-semibold text-destructive transition-colors hover:bg-destructive/20 focus-visible:bg-destructive/20 focus-visible:outline-none"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <span className="flex flex-1 items-center gap-1.5 text-left">
          <AlertTriangle className="size-4" />
          Alerts ({alerts.length})
        </span>
        <span className="text-destructive/80 transition-transform">
          {isExpanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        </span>
      </button>

      {isExpanded ? (
        <div className="flex max-h-32 flex-col gap-1 overflow-y-auto px-3 pb-3">
          {alerts.map((mission) => (
            <div
              key={mission.id}
              className="flex items-start gap-2 rounded-sm px-2 py-1.5 bg-destructive/5 text-destructive"
            >
              <div className="flex flex-col min-w-0">
                <span className="truncate text-xs font-medium">
                  {mission.name}
                </span>
                <span className="truncate text-[10px] opacity-80">
                  {mission.summary}
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

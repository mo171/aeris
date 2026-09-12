import { History } from "lucide-react";
import { format } from "date-fns";
import type { InvestigationEvent } from "../../types/history.types";
import { formatRelativeTime } from "@/lib/formatters";
import { EmptyState } from "@/components/sharedUI/functionalComponent/feedback/EmptyState";

interface HistoryListProps {
  events: InvestigationEvent[];
}

export function HistoryList({ events }: HistoryListProps) {
  if (events.length === 0) {
    return <EmptyState icon={History} title="No history yet" description="Commands you run will appear here." />;
  }

  // Group events by day
  const grouped = events.reduce((acc, event) => {
    const day = format(new Date(event.at), "MMM d, yyyy");
    if (!acc[day]) acc[day] = [];
    acc[day].push(event);
    return acc;
  }, {} as Record<string, InvestigationEvent[]>);

  return (
    <div className="flex flex-col gap-4">
      {Object.entries(grouped).map(([day, dayEvents]) => (
        <div key={day} className="flex flex-col gap-1.5">
          <h3 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider px-1">
            {day}
          </h3>
          <ul className="flex flex-col gap-0.5">
            {dayEvents.map((event) => (
              <li key={event.id} className="flex flex-col rounded-sm px-2 py-1.5 hover:bg-muted/50 transition-colors">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-foreground">{event.summary}</span>
                  <span className="text-[9px] font-mono text-muted-foreground/60">{formatRelativeTime(event.at)}</span>
                </div>
                <div className="text-[10px] text-muted-foreground mt-0.5 font-mono truncate">
                  {event.actor} · {event.commandId.split(".").pop()}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

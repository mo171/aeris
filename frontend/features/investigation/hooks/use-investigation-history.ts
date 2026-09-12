"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { subscribeToDispatches } from "@/lib/command-bus";
import { getRegisteredCommands } from "@/lib/command-bus";
import type { InvestigationEvent } from "../types/history.types";
import { format } from "date-fns";

const HISTORY_STORAGE_PREFIX = "aeris.history";

// A mock backend fetch for the history
async function fetchHistory(investigationId: string): Promise<InvestigationEvent[]> {
  const stored = sessionStorage.getItem(`${HISTORY_STORAGE_PREFIX}.${investigationId}`);
  if (stored) {
    try {
      return JSON.parse(stored) as InvestigationEvent[];
    } catch {
      return [];
    }
  }
  return [];
}

async function appendHistory(event: InvestigationEvent): Promise<void> {
  const existing = await fetchHistory(event.investigationId);
  const updated = [event, ...existing];
  sessionStorage.setItem(`${HISTORY_STORAGE_PREFIX}.${event.investigationId}`, JSON.stringify(updated));
}

// Generate a summary based on the command and params
function summarizeCommand(commandId: string, params: unknown): string {
  const command = getRegisteredCommands().find((c) => c.id === commandId);
  if (!command) return "Unknown action";
  
  // Basic formatting based on common commands
  if (commandId === "investigation.rerunStep") {
    return "Re-ran analysis step with new parameters";
  }
  if (commandId === "investigation.ask") {
    const q = (params as any)?.query;
    return `Asked: "${q}"`;
  }
  if (commandId === "investigation.runOperation") {
    const op = (params as any)?.operationId;
    return `Ran analysis: ${op}`;
  }
  if (commandId === "investigation.saveVersion") {
    const label = (params as any)?.label;
    return `Saved version "${label}"`;
  }
  if (commandId === "investigation.scrubTo" || commandId === "investigation.stepAcquisition") {
    return "Changed temporal comparison date";
  }
  if (commandId === "investigation.setCloudCeiling") {
    const pct = (params as any)?.percentage;
    return `Set cloud ceiling to ${pct}%`;
  }
  if (commandId === "investigation.completeDraw") {
    return "Drawn area of interest created";
  }
  
  return command.title;
}

export function useInvestigationHistory(investigationId: string) {
  const queryClient = useQueryClient();
  const queryKey = ["investigations", investigationId, "history"];

  const { data: history = [] } = useQuery({
    queryKey,
    queryFn: () => fetchHistory(investigationId),
  });

  const appendMutation = useMutation({
    mutationFn: appendHistory,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
    },
  });

  useEffect(() => {
    const unsubscribe = subscribeToDispatches((commandId, params) => {
      const command = getRegisteredCommands().find((c) => c.id === commandId);
      if (command?.recordsHistory) {
        const event: InvestigationEvent = {
          id: crypto.randomUUID(),
          investigationId,
          at: new Date().toISOString(),
          actor: "operator", // Could be agent if we knew who dispatched it
          commandId,
          summary: summarizeCommand(commandId, params),
          params,
        };
        appendMutation.mutate(event);
      }
    });

    return () => unsubscribe();
  }, [investigationId, appendMutation]);

  return { history };
}

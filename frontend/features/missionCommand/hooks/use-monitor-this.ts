"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Radar } from "lucide-react";
import { useCallback, useMemo } from "react";
import { z } from "zod";

import type { Investigation } from "@/features/investigation/types/investigation.types";
import { defineCommand, useRegisterCommands } from "@/lib/command-bus";
import { COMMAND_IDS } from "@/lib/constants/commands";
import { QUERY_KEYS } from "@/lib/constants/query-keys";

import { createMission } from "../services/mission.service";
import type { Mission } from "../types/mission.types";

interface MonitorThisControls {
  save: (name: string, cadence: string, templateVersionId: string) => void;
  isSaving: boolean;
  savedMission: Mission | null;
}

export function useMonitorThis(investigation: Investigation | undefined): MonitorThisControls {
  const queryClient = useQueryClient();

  const { mutate, isPending, data } = useMutation({
    mutationFn: (request: { projectId: string; name: string; cadence: string; templateVersionId: string }) =>
      createMission(request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.missions.all });
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.globe.markers() });
    },
  });

  const save = useCallback(
    (name: string, cadence: string, templateVersionId: string) => {
      if (!investigation) {
        return;
      }
      mutate({ projectId: investigation.projectId, name, cadence, templateVersionId });
    },
    [investigation, mutate],
  );

  const commands = useMemo(
    () => [
      defineCommand({
        id: COMMAND_IDS.investigation.saveAsMission, // Keeping same ID to avoid breaking registry
        title: "Monitor this investigation",
        description: "Set a standing order to monitor this project on a cadence.",
        group: "investigation",
        keywords: ["mission", "monitor", "save", "watch", "recurring"],
        icon: Radar,
        paramsSchema: z.object({ 
          name: z.string().min(1), 
          cadence: z.string().min(1),
          templateVersionId: z.string().min(1) 
        }),
        handler: ({ name, cadence, templateVersionId }) => save(name, cadence, templateVersionId),
      }),
    ],
    [save],
  );

  useRegisterCommands(investigation ? commands : []);

  return { save, isSaving: isPending, savedMission: data ?? null };
}

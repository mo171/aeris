// features/missionCommand/hooks/use-save-as-mission.ts — promoting an investigation into a saved mission.
//
// what  : Saves the open investigation as a mission over the same area, and registers
//         `investigation.saveAsMission` so the agent and the command palette can do the same.
// where : Called by InvestigationScreen; the control sits in the investigation header.
// how   : Lives in the missionCommand feature rather than the investigation one because the work is
//         mission-domain — only its trigger belongs to the workspace. That is the mirror of
//         use-investigation-launch.ts, which lives in the investigation feature and is triggered from
//         Mission Command.
//
//         SAVING A MISSION IS A VERB ON AN INVESTIGATION, NOT A DESTINATION. There is no Mission Library
//         surface: Mission Command already lists missions and draws their globe markers, and the
//         investigation index is the shelf. See lib/constants/navigation.ts for what that entry failed on.
//
//         The analysis kind is derived from the investigation's own mode rather than asked for. An
//         operator saving a cross-modal investigation means to keep monitoring it cross-modally; making
//         them restate that in a dialog is a question with one right answer.

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
import type { Mission, MissionAnalysisKind } from "../types/mission.types";

interface SaveAsMissionControls {
  save: (name?: string) => void;
  isSaving: boolean;
  /** The mission this investigation was saved as, once it has been. Null until then. */
  savedMission: Mission | null;
}

export function useSaveAsMission(investigation: Investigation | undefined): SaveAsMissionControls {
  const queryClient = useQueryClient();

  const { mutate, isPending, data } = useMutation({
    mutationFn: (request: { investigationId: string; name: string }) =>
      createMission({
        ...request,
        analysisKind: analysisKindFor(investigation),
      }),
    // The new mission has to appear in the lists that already exist — the Mission Command panel and the
    // globe markers both read from these keys.
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.missions.all });
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.globe.markers() });
    },
  });

  const save = useCallback(
    (name?: string) => {
      if (!investigation) {
        return;
      }
      mutate({ investigationId: investigation.id, name: name ?? investigation.name });
    },
    [investigation, mutate],
  );

  const commands = useMemo(
    () => [
      defineCommand({
        id: COMMAND_IDS.investigation.saveAsMission,
        title: "Save this investigation as a mission",
        description:
          "Keep the open investigation as a re-runnable mission over the same area, so it appears on Mission Command and on the globe. Pass a name to override the investigation's own.",
        group: "investigation",
        keywords: ["mission", "monitor", "save", "watch", "recurring"],
        icon: Radar,
        paramsSchema: z.object({ name: z.string().min(1).optional() }),
        handler: ({ name }) => save(name),
      }),
    ],
    [save],
  );

  useRegisterCommands(investigation ? commands : []);

  return { save, isSaving: isPending, savedMission: data ?? null };
}

/**
 * What kind of analysis the mission should keep running.
 *
 * A cross-modal investigation stays cross-modal; everything else monitors change, which is the analysis
 * the temporal comparator already performs on every pair.
 */
function analysisKindFor(investigation: Investigation | undefined): MissionAnalysisKind {
  return investigation?.mode === "crossModal" ? "cross-modal" : "change-detection";
}

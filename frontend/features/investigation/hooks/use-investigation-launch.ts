// features/investigation/hooks/use-investigation-launch.ts — starting an investigation, and the descent.
//
// what  : Creates an investigation from selected scenes, starts the camera flying to its area of
//         interest, and routes to the workspace. Registers `investigation.create` and `investigation.open`.
// where : Called by MissionCommandScreen. It lives in the investigation feature rather than in Mission
//         Command because the action is investigation-domain work; only its trigger belongs to page 1.
// how   : The navigation is deliberately NOT awaited behind the camera flight. The sequence is: create,
//         start flying, route immediately. Because the viewer belongs to the route group layout rather
//         than to either page, the workspace mounts around a camera that is already in motion — so the
//         operator sees one continuous descent from orbit to the ground, and the network work for the
//         scene hides inside it.
//
//         Waiting for the flight to finish before routing produces a dead pause at exactly the moment the
//         transition is supposed to feel seamless, which is why the order here matters more than it looks.
//
//         Both entry points converge on one code path, so a click, a command and a future voice intent
//         cannot behave differently.

"use client";

import { useMutation } from "@tanstack/react-query";
import { ScanSearch } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useMemo } from "react";

import { defineCommand, useRegisterCommands } from "@/lib/command-bus";
import { COMMAND_IDS } from "@/lib/constants/commands";
import { INVESTIGATION_CAMERA } from "@/lib/constants/investigation";
import { buildRoute } from "@/lib/constants/routes";
import { useGeoStageStore } from "@/store/geo-stage-store";
import { z } from "zod";


import { createInvestigation } from "../services/investigation.service";
import type { InvestigationCreateRequest } from "../types/investigation.types";

interface InvestigationLaunchControls {
  launch: (request: InvestigationCreateRequest) => void;
  isLaunching: boolean;
}

export function useInvestigationLaunch(): InvestigationLaunchControls {
  const router = useRouter();

  const { mutate, isPending } = useMutation({
    mutationFn: (request: InvestigationCreateRequest) => createInvestigation(request),
    onSuccess: (response) => {
      const { handle, beginDescent } = useGeoStageStore.getState();

      const target = {
        latitude: response.cameraTarget.latitude,
        longitude: response.cameraTarget.longitude,
        altitudeMeters: response.cameraTarget.altitudeMeters,
        durationMs: INVESTIGATION_CAMERA.descentDurationSeconds * 1000,
        pitchDegrees: INVESTIGATION_CAMERA.restingPitchDegrees,
      };

      // Recorded before the flight starts so the workspace can tell, on mount, that a descent is already
      // under way and must not be restarted.
      beginDescent({
        investigationId: response.investigationId,
        target,
        bounds: response.areaOfInterest,
        startedAt: Date.now(),
      });

      handle?.camera.flyTo(target);
      router.push(buildRoute.investigationDetail(response.investigationId));
    },
  });

  const launch = useCallback(
    (request: InvestigationCreateRequest) => mutate(request),
    [mutate],
  );

  const commands = useMemo(
    () => [
      defineCommand({
        id: COMMAND_IDS.investigation.create,
        title: "Investigate selected imagery",
        description:
          "Create an investigation from the selected scenes and fly the camera down to the area of interest.",
        group: "investigation",
        keywords: ["analyse", "analyze", "workspace", "change detection"],
        icon: ScanSearch,
        paramsSchema: z.object({
          sceneIds: z.array(z.string().min(1)).min(1),
          seedQuery: z.string().nullable().default(null),
          missionId: z.string().nullable().default(null),
        }),
        handler: (parameters) => launch(parameters),
        // Hidden from the palette because it takes parameters a palette cannot collect. It stays fully
        // agent-invocable, which is the point of keeping the two concerns separate.
        isPaletteVisible: false,
      }),

      defineCommand({
        id: COMMAND_IDS.investigation.open,
        title: "Open an investigation",
        description: "Navigate to an existing investigation workspace by id.",
        group: "investigation",
        icon: ScanSearch,
        paramsSchema: z.object({ investigationId: z.string().min(1) }),
        handler: ({ investigationId }) => {
          router.push(buildRoute.investigationDetail(investigationId));
        },
        isPaletteVisible: false,
      }),
    ],
    [launch, router],
  );

  useRegisterCommands(commands);

  return { launch, isLaunching: isPending };
}

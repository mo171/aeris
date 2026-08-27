// features/investigation/hooks/use-autonomous-investigation.ts — the multi-step drill-down macro.
//
// what  : Fetches the plan AERIS intends to run, exposes it for editing, and executes the approved steps.
// where : Consumed by the Investigate action in the answer panel and by the investigation.runAutonomous
//         command.
// how   : The plan is fetched BEFORE anything executes and is editable. That is what separates an
//         instrument from a scripted demo: a rehearsed sequence cannot let a judge strike out a step and
//         still work, and this one can.
//
//         Execution is not a special code path. It dispatches the same run the operator would trigger by
//         typing, with the approved plan id attached, so the autonomous mode and the manual mode cannot
//         drift apart — there is only one mode.

"use client";

import { useMutation } from "@tanstack/react-query";
import { useCallback } from "react";

import { fetchAnalysisPlan } from "../services/analysis.service";
import { useInvestigationStore } from "../store/investigation-store";

interface AutonomousInvestigationControls {
  isPreparing: boolean;
  /** Fetches and opens the plan sheet for review. Nothing runs until the operator approves it. */
  prepare: (fromClaimId: string) => void;
  /** Runs the enabled steps of the plan currently on screen. */
  execute: () => void;
  dismiss: () => void;
}

interface AutonomousInvestigationOptions {
  investigationId: string;
  ask: (query: string, options?: { planId?: string }) => void;
}

export function useAutonomousInvestigation({
  investigationId,
  ask,
}: AutonomousInvestigationOptions): AutonomousInvestigationControls {
  const setActivePlan = useInvestigationStore((state) => state.setActivePlan);

  const { mutate, isPending } = useMutation({
    mutationFn: (fromClaimId: string) => fetchAnalysisPlan(investigationId, fromClaimId),
    onSuccess: (plan) => setActivePlan(plan),
  });

  const execute = useCallback(() => {
    const { activePlan } = useInvestigationStore.getState();
    if (!activePlan) {
      return;
    }

    const enabledSteps = activePlan.steps.filter((step) => step.isEnabled);
    if (enabledSteps.length === 0) {
      return;
    }

    setActivePlan(null);
    // The plan summary is the question. The backend already knows the step list from the plan id, so
    // sending it again would be two sources of truth for the same decision.
    ask(activePlan.summary, { planId: activePlan.id });
  }, [ask, setActivePlan]);

  return {
    isPreparing: isPending,
    prepare: useCallback((fromClaimId: string) => mutate(fromClaimId), [mutate]),
    execute,
    dismiss: useCallback(() => setActivePlan(null), [setActivePlan]),
  };
}

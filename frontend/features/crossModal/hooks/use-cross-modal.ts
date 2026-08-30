// features/crossModal/hooks/use-cross-modal.ts — the cross-modal reading of the open investigation.
//
// what  : Fetches the two-sensor verdict for the investigation currently open in the workspace, derives
//         the ledger counts, and exposes the lens's view state — which sensor is soloed, which agreement
//         row is selected, which polarisation radar is showing.
// where : Called once by InvestigationScreen, alongside the workspace's own hooks.
// how   : Read-only against an EXISTING investigation. This never creates one, never mutates the evidence
//         graph and never dispatches a run — both sensor analyses are complete before the lens opens. That
//         is what makes it a LENS: a second way of reading evidence the workspace already holds.
//
//         THE QUERY IS GATED ON THE LENS. Every investigation would otherwise fetch a cross-modal verdict
//         it may never show, and the ones with no radar would fetch a result that cannot exist. Closing
//         the lens leaves the cached result in place, so re-opening it is instant and reads the same
//         numbers — reopening a reading must never be able to produce a different answer.
//
//         SELECTION LIVES IN THE STORE, not here. Three separate subtrees act on it: the left panel's
//         sensor cards, the right panel's ledger, and the stage binding that composes the layer stack. It
//         is also reachable from the command bus, and commands dispatch into stores rather than into a
//         component's useState.

"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";

import { AGREEMENT, type AgreementState, type Polarisation } from "@/lib/constants/cross-modal";
import { QUERY_KEYS } from "@/lib/constants/query-keys";
import { useInvestigationStore } from "@/features/investigation/store/investigation-store";

import { fetchCrossModalResult } from "../services/cross-modal.service";
import type { AgreementRow, CrossModalResult, SensorId } from "../types/cross-modal.types";

export interface CrossModalView {
  /** Whether the operator has the lens open. Everything below is inert when false. */
  isActive: boolean;
  result: CrossModalResult | undefined;
  isLoading: boolean;
  error: Error | null;

  /** Ledger rows, already ordered worst-first by the generator. */
  rows: readonly AgreementRow[];
  /** How many rows sit in each state, for the verdict summary. */
  counts: Readonly<Record<AgreementState, number>>;

  selectedRowId: string | null;
  selectRow: (rowId: string | null) => void;
  selectedRow: AgreementRow | null;

  /**
   * Which sensor the stage is showing alone, or null for the split.
   *
   * Soloing is how an operator checks one sensor's claim without the other in the way. It never changes
   * what was analysed — both runs are complete before the lens opens.
   */
  soloSensor: SensorId | null;
  setSoloSensor: (sensor: SensorId | null) => void;

  polarisation: Polarisation;
  setPolarisation: (polarisation: Polarisation) => void;
}

const NO_ROWS: readonly AgreementRow[] = [];

export function useCrossModal(investigationId: string): CrossModalView {
  const lens = useInvestigationStore((state) => state.crossModalLens);
  const setSoloSensor = useInvestigationStore((state) => state.setCrossModalSoloSensor);
  const selectAgreementRow = useInvestigationStore((state) => state.selectAgreementRow);
  const setPolarisation = useInvestigationStore((state) => state.setCrossModalPolarisation);

  const { data, isLoading, error } = useQuery({
    queryKey: QUERY_KEYS.investigations.crossModal(investigationId),
    queryFn: ({ signal }) => fetchCrossModalResult(investigationId, signal),
    enabled: lens.isActive,
  });

  const rows = useMemo(() => data?.verdict?.rows ?? NO_ROWS, [data]);

  const counts = useMemo(() => {
    const tally = { conflict: 0, corroborated: 0, "optical-only": 0, "radar-only": 0 };
    for (const row of rows) {
      tally[row.state] += 1;
    }
    return tally as Record<AgreementState, number>;
  }, [rows]);

  const selectedRow = useMemo(
    () => rows.find((row) => row.id === lens.selectedRowId) ?? null,
    [rows, lens.selectedRowId],
  );

  const selectRow = useCallback(
    (rowId: string | null) => selectAgreementRow(rowId),
    [selectAgreementRow],
  );

  return {
    isActive: lens.isActive,
    result: data,
    isLoading,
    error: error as Error | null,
    rows,
    counts,
    selectedRowId: lens.selectedRowId,
    selectRow,
    selectedRow,
    soloSensor: lens.soloSensor,
    setSoloSensor,
    polarisation: lens.polarisation,
    setPolarisation,
  };
}

/** Ordering helper shared by the ledger and the verdict summary. Conflict always leads. */
export function byAgreementPriority(left: AgreementRow, right: AgreementRow): number {
  return AGREEMENT[left.state].priority - AGREEMENT[right.state].priority;
}

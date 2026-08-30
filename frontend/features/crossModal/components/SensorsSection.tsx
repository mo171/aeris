// features/crossModal/components/SensorsSection.tsx — the two sensors, as a section of the left panel.
//
// what  : A collapsible section holding both sensor cards, the pair advisory saying how far apart the two
//         acquisitions are, and a control to close the lens.
// where : Passed to InputsPanel as `sensorsSection` by InvestigationScreen while the lens is open. It sits
//         above Inputs, Findings, Masks and Reference.
// how   : Composed here rather than inside InputsPanel so the dependency stays one-way — the workspace
//         composes the lens, the lens knows nothing about the panel it lands in.
//
//         THE OFFSET IS THE FIRST THING SHOWN. Sentinel-2 passes roughly every five days and Sentinel-1
//         every six to twelve, so a cross-modal pair is ALWAYS offset and the honest thing is to say by
//         how much before anything below is read. It used to be in the Lab's own header; with the Lab
//         dissolved into the workspace, the fact belongs next to the sensors it qualifies.
//
//         THE CLOSE CONTROL LIVES HERE because this is where the lens is most visible. An operator who
//         opened a reading from the Toolbox should not have to remember which row they pressed to get out
//         of it.

"use client";

import { X } from "lucide-react";

import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { CrossModalResult, ModalityAdvisory, SensorId } from "../types/cross-modal.types";
import { RadarControls } from "./RadarControls";
import { SensorCard } from "./SensorCard";

interface SensorsSectionProps {
  result: CrossModalResult | undefined;
  isLoading: boolean;
  error: Error | null;
  soloSensor: SensorId | null;
  onToggleSolo: (sensor: SensorId) => void;
  polarisation: React.ComponentProps<typeof RadarControls>["polarisation"];
  onPolarisationChange: React.ComponentProps<typeof RadarControls>["onPolarisationChange"];
  isExpanded: boolean;
  onToggleExpanded: () => void;
  onClose: () => void;
}

export function SensorsSection({
  result,
  isLoading,
  error,
  soloSensor,
  onToggleSolo,
  polarisation,
  onPolarisationChange,
  isExpanded,
  onToggleExpanded,
  onClose,
}: SensorsSectionProps) {
  const opticalFindings =
    result?.optical.layers.reduce((total, layer) => total + layer.features.length, 0) ?? 0;
  const radarFindings =
    result?.radar?.layers.reduce((total, layer) => total + layer.features.length, 0) ?? 0;

  return (
    <section
      className={cn(
        "flex flex-col border-b border-aeris-teal/25 bg-aeris-teal/5",
        isExpanded ? "min-h-0 flex-1" : "shrink-0",
      )}
    >
      <SectionHeader
        title="Sensors"
        isExpanded={isExpanded}
        onToggle={onToggleExpanded}
        trailing={
          <>
            {result ? <PairAdvisory advisory={result.advisory} /> : null}
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              onClick={onClose}
              aria-label="Close the cross-modal reading"
            >
              <X />
            </Button>
          </>
        }
      />

      {isExpanded ? (
        <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto px-2 pb-2">
          {result ? (
            <>
              <SensorCard
                sensor="optical"
                run={result.optical}
                findingCount={opticalFindings}
                isSoloed={soloSensor === "optical"}
                onToggleSolo={() => onToggleSolo("optical")}
              />

              <SensorCard
                sensor="radar"
                run={result.radar}
                findingCount={radarFindings}
                isSoloed={soloSensor === "radar"}
                onToggleSolo={() => onToggleSolo("radar")}
              >
                {result.radar ? (
                  <RadarControls
                    run={result.radar}
                    polarisation={polarisation}
                    onPolarisationChange={onPolarisationChange}
                  />
                ) : null}
              </SensorCard>
            </>
          ) : (
            <div className="px-1 py-2">
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                {isLoading
                  ? "Reading both sensors…"
                  : "No cross-modal result for this area of interest."}
              </p>
              {/*
                The reason, not just the absence. A contract violation and a genuinely empty area look
                identical from the operator's side, and only one of them is their problem.
              */}
              {error ? (
                <p className="mt-1 font-mono text-[10px] leading-relaxed text-aeris-amber/80">
                  {error.message}
                </p>
              ) : null}
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}

/** How far apart the pair is, and whether that is fair. Shown in the header so it survives collapse. */
function PairAdvisory({ advisory }: { advisory: ModalityAdvisory }) {
  return (
    <span
      className={cn(
        "rounded-[2px] border px-1 py-0.5 font-mono text-[9px] tracking-wide uppercase",
        advisory.verdict === "fair"
          ? "border-aeris-green/35 bg-aeris-green/10 text-aeris-green"
          : "border-aeris-amber/40 bg-aeris-amber/10 text-aeris-amber",
      )}
      title={advisory.notes.join(" ")}
    >
      {advisory.offsetDays}d · {advisory.verdict}
    </span>
  );
}

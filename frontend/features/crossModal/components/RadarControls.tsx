// features/crossModal/components/RadarControls.tsx — polarisation, and where the radar was looking from.
//
// what  : The VV / VH / ratio selector and a readout of the sensor's look azimuth and incidence angle.
// where : Slotted into the radar SensorCard. Optical has no equivalent, which is the one asymmetry the
//         Lab allows — because it reflects a real difference between the instruments, not a design choice.
// how   : POLARISATION IS NOT A DISPLAY PREFERENCE. VV responds to surface roughness and water; VH to
//         volume scattering — vegetation and structural complexity. They answer different questions, and
//         offering only one throws away half of what Sentinel-1 actually recorded. The ratio composite is
//         standard practice for separating built-up from vegetation, which is exactly the distinction a
//         cross-modal comparison usually turns on.
//
//         THE LOOK DIRECTION IS THE POINT OF THIS COMPONENT. Layover and shadow are predictable from
//         geometry: terrain tilted toward the sensor folds into one range bin, terrain behind it returns
//         nothing. An operator who can see the azimuth can anticipate where radar is blind BEFORE reading
//         a finding, instead of discovering it inside a wrong answer. Stating it costs one line and
//         turns the radar masks from arbitrary shapes into consequences of a known geometry.

"use client";

import { POLARISATION_DETAIL, POLARISATIONS, type Polarisation } from "@/lib/constants/cross-modal";
import { cn } from "@/lib/utils";

import type { SensorRun } from "../types/cross-modal.types";

interface RadarControlsProps {
  run: SensorRun;
  polarisation: Polarisation;
  onPolarisationChange: (polarisation: Polarisation) => void;
}

export function RadarControls({ run, polarisation, onPolarisationChange }: RadarControlsProps) {
  const detail = POLARISATION_DETAIL[polarisation];

  return (
    <div className="mt-2 border-t border-border-soft pt-1.5">
      <div className="flex items-center gap-1">
        <span className="font-mono text-[9px] tracking-wide text-muted-foreground/50 uppercase">
          pol
        </span>
        {POLARISATIONS.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={polarisation === option}
            onClick={() => onPolarisationChange(option)}
            title={POLARISATION_DETAIL[option].sensitiveTo}
            className={cn(
              "rounded-[2px] border px-1 font-mono text-[9px] tracking-wide transition-colors duration-fast",
              polarisation === option
                ? "border-[#C3CAD6]/60 bg-[#C3CAD6]/15 text-[#C3CAD6]"
                : "border-border-soft/60 text-muted-foreground hover:text-foreground",
            )}
          >
            {POLARISATION_DETAIL[option].label}
          </button>
        ))}
      </div>

      <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground/70">
        {detail.sensitiveTo}
      </p>

      {/* Geometry, stated so blindness is predictable rather than discovered. */}
      {run.lookAzimuthDegrees !== null ? (
        <div className="mt-1.5 flex items-center gap-1.5">
          <span
            className="inline-block size-3 shrink-0 text-[#C3CAD6]"
            style={{ transform: `rotate(${run.lookAzimuthDegrees}deg)` }}
            aria-hidden="true"
          >
            <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4">
              <path d="M6 10.5V1.5M6 1.5L3 4.5M6 1.5L9 4.5" strokeLinecap="round" />
            </svg>
          </span>
          <span className="font-mono text-[9px] text-muted-foreground">
            looking {compassPoint(run.lookAzimuthDegrees)} · {run.lookAzimuthDegrees.toFixed(0)}°
            {run.incidenceAngleDegrees !== null
              ? ` · ${run.incidenceAngleDegrees.toFixed(0)}° incidence`
              : ""}
          </span>
        </div>
      ) : null}
    </div>
  );
}

/** Azimuth as a compass point, because "looking east" is read faster than "78°". */
function compassPoint(azimuthDegrees: number): string {
  const points = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  return points[Math.round(azimuthDegrees / 45) % 8];
}

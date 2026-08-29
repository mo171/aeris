// features/investigation/components/viewer/CameraControls.tsx — aiming the camera, and giving the scene height.
//
// what  : Orbit left and right, a tilt control that steps through nadir to oblique, and the toggle that
//         puts building massing on the scene.
// where : The centre column of InvestigationScreen, beside the projection toggle — both answer "how am I
//         looking at this", as opposed to the tool cluster, which answers "what am I doing to it".
// how   : These exist because the workspace camera could not previously be aimed at all. Cesium's own
//         tilt is a middle-mouse drag, which does not exist on a trackpad, so an operator had no way to
//         leave nadir — and a scene that can only be viewed straight down cannot show relief no matter how
//         good the terrain under it is. Tilt is therefore a labelled control, not a gesture.
//
//         Tilt cycles through presets rather than offering a continuous dial. The three angles that matter
//         are distinct tasks: straight down for digitising and measuring, a working oblique for reading
//         change, and a low angle for seeing how tall something is. A slider would ask the operator to
//         hunt for those three.
//
//         Buildings are separated from terrain deliberately. In a city almost none of the vertical
//         information is in the ground — relief across a four-kilometre area is tens of metres — so the
//         massing toggle, not the terrain, is what decides whether the scene reads as a place.

"use client";

import {
  Building2,
  Images,
  RotateCcwSquare,
  RotateCwSquare,
  Slash,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { dispatchCommand } from "@/lib/command-bus";
import { COMMAND_IDS } from "@/lib/constants/commands";
import { INVESTIGATION_CAMERA } from "@/lib/constants/investigation";
import { BUILDING_STYLE_OPTIONS } from "@/lib/constants/overlays";
import { cn } from "@/lib/utils";
import { useGeoStageStore } from "@/store/geo-stage-store";

import type {
  StageBuildingCoverage,
  StageBuildingMode,
} from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";

import { useInvestigationStore } from "../../store/investigation-store";

/**
 * What the massing toggle can honestly claim, per coverage state.
 *
 * OpenStreetMap building footprints are dense in cities and effectively absent over farmland and desert.
 * Saying so is the difference between the operator learning something true about the data and concluding
 * the button is broken.
 */
const COVERAGE_COPY: Record<StageBuildingCoverage, string> = {
  unavailable: "Building massing needs a Cesium Ion token",
  loading: "Loading building footprints…",
  present: "3D building footprints, extruded to real heights",
  none: "OpenStreetMap has no building footprints over this area",
};

/**
 * The three ways the built environment can render, and the honest trade for each.
 *
 * Photorealistic is not simply "better massing". It replaces the ground rather than sitting on it, which
 * suspends the operator's own imagery and the before/after split — so the control says that outright
 * instead of letting an analyst discover their scene has gone.
 */
const BUILDING_MODES: readonly {
  id: StageBuildingMode;
  label: string;
  icon: typeof Building2;
  hint: string;
}[] = [
  { id: "none", label: "Flat", icon: Slash, hint: "No buildings — imagery draped on terrain only" },
  {
    id: "massing",
    label: "Massing",
    icon: Building2,
    hint: "OpenStreetMap footprints extruded to real heights. Free, and your imagery stays visible underneath.",
  },
  {
    id: "photorealistic",
    label: "Photoreal",
    icon: Images,
    hint: "Google photogrammetry — textured 3D. Metered per tile, and it replaces the ground: scene imagery and the before/after split are suspended while it is on.",
  },
];

/** What each preset is actually for, so the tooltip explains the angle rather than naming it. */
const PITCH_COPY: Record<number, { label: string; hint: string }> = {
  [-90]: { label: "NADIR", hint: "Straight down — for digitising and measuring" },
  [-62]: { label: "OBLIQUE", hint: "Working angle — relief and change together" },
  [-35]: { label: "LOW", hint: "Low angle — for reading how tall things are" },
};

export function CameraControls() {
  const stage = useGeoStageStore((state) => state.handle);
  const buildingMode = useInvestigationStore((state) => state.buildingMode);
  const buildingStyleId = useInvestigationStore((state) => state.buildingStyleId);
  const setBuildingStyle = useInvestigationStore((state) => state.setBuildingStyle);

  // Pitch is the one value here that is NOT stored: it changes continuously as the operator drags, so it
  // is read from the stage rather than mirrored. Buildings are a discrete choice and live in the store,
  // where a command and this button cannot end up disagreeing about what is on screen.
  const [pitchDegrees, setPitchDegrees] = useState<number>(
    INVESTIGATION_CAMERA.pitchPresetsDegrees[1],
  );
  const [coverage, setCoverage] = useState<StageBuildingCoverage>("loading");

  useEffect(() => {
    if (!stage) {
      return;
    }
    return stage.camera.subscribeState((state) => setPitchDegrees(state.pitchDegrees));
  }, [stage]);

  useEffect(() => {
    if (!stage) {
      return;
    }
    return stage.appearance.subscribeBuildingCoverage(setCoverage);
  }, [stage]);

  if (!stage) {
    return null;
  }

  /** The preset the camera currently sits nearest, so one press always moves somewhere different. */
  const nearestPresetIndex = INVESTIGATION_CAMERA.pitchPresetsDegrees.reduce(
    (closest, candidate, index, all) =>
      Math.abs(candidate - pitchDegrees) < Math.abs(all[closest] - pitchDegrees) ? index : closest,
    0,
  );
  const activePreset = INVESTIGATION_CAMERA.pitchPresetsDegrees[nearestPresetIndex];
  const copy = PITCH_COPY[activePreset] ?? { label: "TILT", hint: "Change the viewing angle" };

  const cycleTilt = () => {
    const next =
      INVESTIGATION_CAMERA.pitchPresetsDegrees[
        (nearestPresetIndex + 1) % INVESTIGATION_CAMERA.pitchPresetsDegrees.length
      ];
    void dispatchCommand(COMMAND_IDS.investigation.setTilt, { pitchDegrees: next });
  };

  const selectBuildingMode = (mode: StageBuildingMode) =>
    void dispatchCommand(COMMAND_IDS.investigation.setBuildingMode, { mode });

  return (
    <div className="pointer-events-auto flex items-center gap-1 rounded-md border border-border bg-surface-2/80 p-1 backdrop-blur-md">
      <IconControl
        label="Orbit left"
        onClick={() =>
          void dispatchCommand(COMMAND_IDS.investigation.orbit, {
            deltaDegrees: -INVESTIGATION_CAMERA.orbitStepDegrees,
          })
        }
      >
        <RotateCcwSquare />
      </IconControl>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={cycleTilt}
            className="h-7 gap-1.5 px-2 font-mono text-[10px] tracking-wide text-muted-foreground"
          >
            <TiltGlyph pitchDegrees={pitchDegrees} />
            {copy.label}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="top">{copy.hint}</TooltipContent>
      </Tooltip>

      <IconControl
        label="Orbit right"
        onClick={() =>
          void dispatchCommand(COMMAND_IDS.investigation.orbit, {
            deltaDegrees: INVESTIGATION_CAMERA.orbitStepDegrees,
          })
        }
      >
        <RotateCwSquare />
      </IconControl>

      <span className="mx-0.5 h-4 w-px bg-border" aria-hidden="true" />

      {/*
        Massing reports coverage rather than pretending every place has buildings. Over farmland or desert
        it dims and says why — a control that silently does nothing teaches the operator that the feature
        is broken instead of that the data is absent.
      */}
      {BUILDING_MODES.map(({ id, label, icon: Icon, hint }) => {
        const isMassingUnavailable =
          id === "massing" && (coverage === "none" || coverage === "unavailable");
        const isPhotorealUnavailable =
          id === "photorealistic" && !stage.appearance.isPhotorealisticAvailable();
        const unavailableReason = isMassingUnavailable
          ? COVERAGE_COPY[coverage]
          : isPhotorealUnavailable
            ? "Set NEXT_PUBLIC_GOOGLE_MAPS_API_KEY to enable photorealistic tiles"
            : null;

        return (
          <Tooltip key={id}>
            <TooltipTrigger asChild>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                aria-label={`${label} buildings`}
                aria-pressed={buildingMode === id}
                disabled={isPhotorealUnavailable}
                onClick={() => selectBuildingMode(id)}
                className={cn(
                  "h-7 gap-1 px-1.5 font-mono text-[10px] tracking-wide",
                  buildingMode === id ? "text-aeris-teal" : "text-muted-foreground",
                  ((isMassingUnavailable && buildingMode !== id) || isPhotorealUnavailable) &&
                    "text-muted-foreground/35",
                )}
              >
                <Icon className="size-3" />
                {label}
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-64">
              {unavailableReason ?? hint}
            </TooltipContent>
          </Tooltip>
        );
      })}

      {/*
        What the massing's colour ENCODES, which is a different question from whether buildings are drawn.
        Only offered while massing is on: photorealistic tiles carry their own texture and cannot be
        restyled, and there is nothing to colour when buildings are off.
      */}
      {buildingMode === "massing" ? (
        <>
          <span className="mx-0.5 h-4 w-px bg-border" aria-hidden="true" />
          {BUILDING_STYLE_OPTIONS.map((option) => (
            <Tooltip key={option.id}>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  aria-label={`Colour buildings ${option.label.toLowerCase()}`}
                  aria-pressed={buildingStyleId === option.id}
                  onClick={() => setBuildingStyle(option.id)}
                  className={cn(
                    "h-7 px-1.5 font-mono text-[10px] tracking-wide",
                    buildingStyleId === option.id ? "text-aeris-teal" : "text-muted-foreground",
                  )}
                >
                  {option.label}
                </Button>
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-64">
                {option.hint}
              </TooltipContent>
            </Tooltip>
          ))}
        </>
      ) : null}
    </div>
  );
}

/**
 * A horizon line that rotates with the camera pitch.
 *
 * The angle is the thing being controlled, so the control shows the angle. A generic icon would leave the
 * operator reading a word where a picture of the geometry is available for nothing.
 */
function TiltGlyph({ pitchDegrees }: { pitchDegrees: number }) {
  // -90 (nadir) reads as flat; -35 (low) tips toward the horizon.
  const tilt = Math.max(0, Math.min(55, -(pitchDegrees + 90)));

  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" className="shrink-0">
      <g transform={`rotate(${-tilt} 6 6)`}>
        <line x1="1" y1="7.5" x2="11" y2="7.5" stroke="currentColor" strokeWidth="1.4" />
        <line x1="3" y1="4.5" x2="9" y2="4.5" stroke="currentColor" strokeWidth="1" opacity="0.45" />
      </g>
    </svg>
  );
}

function IconControl({
  label,
  hint,
  onClick,
  isActive,
  isMuted,
  children,
}: {
  label: string;
  /** Shown in the tooltip when it differs from the accessible label. */
  hint?: string;
  onClick: () => void;
  isActive?: boolean;
  isMuted?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          aria-label={label}
          aria-pressed={isActive}
          onClick={onClick}
          className={cn(isActive && "text-aeris-teal", isMuted && "text-muted-foreground/35")}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="top">{hint ?? label}</TooltipContent>
    </Tooltip>
  );
}

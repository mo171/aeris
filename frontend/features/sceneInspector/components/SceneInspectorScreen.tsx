// features/sceneInspector/components/SceneInspectorScreen.tsx — one scene, in its own window.
//
// what  : A standalone view of a single acquisition: quicklook, acquisition metadata, band table, and the
//         action that binds it into the investigation as T0, T1 or the SAR reference.
// where : Rendered by app/scene/[sceneId]/page.tsx, opened as a detached browser window from the
//         workspace and from Mission Command.
// how   : A separate window rather than a modal, because that is what the work actually needs. Comparing
//         four candidate acquisitions means having four of them visible at once, on a second monitor if
//         there is one — a modal can show exactly one and blocks the map behind it while doing so.
//
//         It has no Cesium and is outside the geospatial route group on purpose: a window whose only job
//         is to show one picture must not boot a WebGL globe to do it.
//
//         Binding a scene into a role talks to the opener through postMessage. That is the only sanctioned
//         channel between the two windows, and the message is validated on arrival like any other input —
//         a window handle is not a reason to trust what comes through it.

"use client";

import { useQuery } from "@tanstack/react-query";
import { Radar, Satellite } from "lucide-react";

import { Chip } from "@/components/sharedUI/dumbComponent/Chip";
import { ErrorState } from "@/components/sharedUI/functionalComponent/feedback/ErrorState";
import { PanelSkeleton } from "@/components/sharedUI/functionalComponent/feedback/PanelSkeleton";
import { Button } from "@/components/ui/button";
import { QUERY_KEYS } from "@/lib/constants/query-keys";
import {
  formatAbsoluteDate,
  formatCoordinates,
  formatGroundSampleDistance,
} from "@/lib/formatters";
import { cn } from "@/lib/utils";

import { fetchSceneInspection } from "../services/scene-inspection.service";
import { SCENE_ROLE_ASSIGNMENT_MESSAGE, type SceneRoleAssignment } from "../scene-popout-messages";

const ASSIGNABLE_ROLES: readonly { role: SceneRoleAssignment["role"]; label: string }[] = [
  { role: "t0", label: "Use as T0" },
  { role: "t1", label: "Use as T1" },
  { role: "sar", label: "Use as SAR" },
];

interface SceneInspectorScreenProps {
  sceneId: string;
}

export function SceneInspectorScreen({ sceneId }: SceneInspectorScreenProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: QUERY_KEYS.imagery.detail(sceneId),
    queryFn: ({ signal }) => fetchSceneInspection(sceneId, signal),
  });

  if (error) {
    return (
      <main className="flex h-dvh items-center justify-center p-6">
        <ErrorState error={error as Error} />
      </main>
    );
  }

  if (isLoading || !data) {
    return (
      <main className="h-dvh p-4">
        <PanelSkeleton rowCount={4} rowHeight={72} />
      </main>
    );
  }

  const { acquisition, areaOfInterestName, areaOfInterest, bands, coordinateReferenceSystem } = data;
  const SensorIcon = acquisition.modality === "sar" ? Radar : Satellite;

  const assignRole = (role: SceneRoleAssignment["role"]) => {
    // The opener is the window that launched this one. If the inspector was opened directly by URL there
    // is nobody to tell, so the action simply is not offered rather than failing silently.
    window.opener?.postMessage(
      {
        type: SCENE_ROLE_ASSIGNMENT_MESSAGE,
        investigationId: data.investigationId,
        sceneId: acquisition.sceneId,
        role,
      } satisfies SceneRoleAssignment,
      window.location.origin,
    );
  };

  return (
    <main className="flex h-dvh flex-col overflow-hidden bg-background">
      <header className="flex shrink-0 items-start gap-3 border-b border-border px-4 py-3">
        <SensorIcon className="mt-0.5 size-4 shrink-0 text-aeris-teal" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-sm font-medium text-foreground">
            {areaOfInterestName} · {formatAbsoluteDate(acquisition.capturedAt)}
          </h1>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 font-mono text-[10px] text-muted-foreground">
            <span>{acquisition.sensorPlatform}</span>
            <span>·</span>
            <span>{formatGroundSampleDistance(acquisition.groundSampleDistanceMeters)}</span>
            <span>·</span>
            <span>{coordinateReferenceSystem}</span>
          </p>
        </div>
        <Chip tone={acquisition.modality === "sar" ? "blue" : "teal"}>{acquisition.modality}</Chip>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="relative aspect-square w-full bg-surface-2">
          {acquisition.quicklookUrl ? (
            // Deliberately a plain img rather than next/image: the quicklook comes from a tile service
            // whose host is not known at build time, and routing it through the optimiser would add a
            // hop for an image that is already exactly the size it is displayed at.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={acquisition.quicklookUrl}
              alt={`Quicklook of ${areaOfInterestName} captured ${formatAbsoluteDate(acquisition.capturedAt)}`}
              className="size-full object-cover"
            />
          ) : (
            <div className="flex size-full items-center justify-center">
              <span className="aeris-technical text-muted-foreground">No quicklook available</span>
            </div>
          )}

          {!acquisition.isAvailable ? (
            <div className="absolute inset-x-0 bottom-0 bg-aeris-amber/15 px-3 py-1.5 backdrop-blur-md">
              <p className="text-xs text-aeris-amber">
                Catalogued but not analysable — cloud cover exceeds the usable threshold.
              </p>
            </div>
          ) : null}
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 px-4 py-3">
          <MetadataRow label="Captured" value={formatAbsoluteDate(acquisition.capturedAt)} />
          <MetadataRow
            label="Cloud cover"
            value={
              acquisition.cloudCoverPercentage === null
                ? "n/a — radar"
                : `${Math.round(acquisition.cloudCoverPercentage)}%`
            }
          />
          <MetadataRow
            label="Centre"
            value={formatCoordinates(
              (areaOfInterest.north + areaOfInterest.south) / 2,
              (areaOfInterest.east + areaOfInterest.west) / 2,
            )}
          />
          <MetadataRow label="Scene id" value={acquisition.sceneId} />
        </dl>

        <section className="border-t border-border-soft px-4 py-3">
          <h2 className="aeris-technical">Bands</h2>
          <ul className="mt-2 flex flex-col gap-1">
            {bands.map((band) => (
              <li
                key={band.name}
                className="flex items-baseline gap-2 font-mono text-[11px] text-muted-foreground"
              >
                <span className="w-12 shrink-0 text-foreground">{band.name}</span>
                <span className="w-16 shrink-0 tabular-nums">
                  {band.wavelengthNanometres === null ? "—" : `${band.wavelengthNanometres} nm`}
                </span>
                <span className="min-w-0 truncate">{band.description}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {window.opener ? (
        <footer className="flex shrink-0 items-center gap-1.5 border-t border-border px-4 py-3">
          {ASSIGNABLE_ROLES.map(({ role, label }) => (
            <Button
              key={role}
              type="button"
              size="sm"
              variant="outline"
              disabled={!acquisition.isAvailable}
              onClick={() => assignRole(role)}
              className={cn("flex-1")}
            >
              {label}
            </Button>
          ))}
        </footer>
      ) : null}
    </main>
  );
}

function MetadataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="aeris-technical">{label}</dt>
      <dd className="truncate font-mono text-[11px] text-foreground">{value}</dd>
    </div>
  );
}

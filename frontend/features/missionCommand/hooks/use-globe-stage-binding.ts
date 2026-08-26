// features/missionCommand/hooks/use-globe-stage-binding.ts — connects Mission Command to the shared 3D stage.
//
// what  : Puts the stage into globe mode, feeds it the marker and satellite-track data, routes marker
//         clicks back into the feature, and publishes the GlobeViewerHandle the rest of this surface uses.
// where : Called once by MissionCommandScreen. Nothing else in this feature touches the stage directly.
// how   : This hook is the adapter that keeps the renderer swap cheap. Every consumer on this surface —
//         GlobeControls, the globe.* commands, the locate handlers — talks to GlobeViewerHandle, which
//         describes what a globe does rather than what Cesium does. The stage is reached in exactly one
//         place: here.
//
//         The handle is republished whenever the stage handle changes identity, which happens once on
//         mount and once on teardown. Marker and track data flow through separate effects because they
//         arrive asynchronously and change independently of the viewer's lifetime.
//
//         Marker clicks come back as an id rather than an object: the stage holds no feature types, by
//         design. Resolving the id against the current feed happens here, where those types live.

"use client";

import { useEffect, useRef } from "react";

import { GLOBE_CAMERA } from "@/lib/constants/globe";
import { useGeoStageStore } from "@/store/geo-stage-store";

import { useMissionCommandStore } from "../store/mission-command-store";
import type { GlobeMarker } from "../types/globe.types";
import { useGlobeLayers } from "./use-globe-layers";

/** The opening view. Declared once here so resetView and the initial camera can never drift apart. */
const GLOBE_HOME_TARGET = {
  latitude: GLOBE_CAMERA.home.latitude,
  longitude: GLOBE_CAMERA.home.longitude,
  altitudeMeters: GLOBE_CAMERA.home.altitudeMeters,
} as const;

interface GlobeStageBindingOptions {
  onMarkerSelect: (marker: GlobeMarker) => void;
}

export function useGlobeStageBinding({ onMarkerSelect }: GlobeStageBindingOptions): void {
  const stage = useGeoStageStore((state) => state.handle);
  const setGlobeViewer = useMissionCommandStore((state) => state.setGlobeViewer);
  const { markers, satelliteTracks } = useGlobeLayers();

  // Mirrored so the binding effect never re-runs when the feed or the callback changes identity —
  // re-registering the handle would churn every consumer that reads it.
  const markersRef = useRef(markers);
  const onMarkerSelectRef = useRef(onMarkerSelect);

  useEffect(() => {
    markersRef.current = markers;
    onMarkerSelectRef.current = onMarkerSelect;
  }, [markers, onMarkerSelect]);

  useEffect(() => {
    if (!stage) {
      setGlobeViewer(null);
      return;
    }

    stage.appearance.setMode("globe");

    stage.globeLayers.setMarkerClickHandler((markerId) => {
      const marker = markersRef.current.find((candidate) => candidate.id === markerId);
      if (marker) {
        onMarkerSelectRef.current(marker);
      }
    });

    setGlobeViewer({
      flyTo: (target) => stage.camera.flyTo(target),
      zoomByFactor: (factor) => stage.camera.zoomByFactor(factor),
      resetView: () => stage.camera.flyTo(GLOBE_HOME_TARGET),
      setAutoRotate: (isEnabled) => stage.camera.setAutoRotate(isEnabled),
      isAutoRotating: () => stage.camera.isAutoRotating(),
    });

    return () => {
      stage.globeLayers.setMarkerClickHandler(null);
      setGlobeViewer(null);
    };
  }, [setGlobeViewer, stage]);

  useEffect(() => {
    stage?.globeLayers.setMarkers(markers);
  }, [markers, stage]);

  useEffect(() => {
    stage?.globeLayers.setSatelliteTracks(satelliteTracks);
  }, [satelliteTracks, stage]);
}

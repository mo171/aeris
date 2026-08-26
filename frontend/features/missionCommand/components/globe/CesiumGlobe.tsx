// features/missionCommand/components/globe/CesiumGlobe.tsx — the CesiumJS viewer that renders the Earth.
//
// what  : Owns the Cesium Viewer lifecycle, configures the scene for the AERIS look, mounts the marker and
//         arc layers, wires picking and idle rotation, and publishes the GlobeViewerHandle.
// where : Loaded lazily by GlobeViewport; never server-rendered. This and its sibling layer modules are
//         the ONLY files in the application permitted to import `cesium`.
// how   : The viewer is created once in a mount effect and torn down completely on unmount — a leaked
//         Cesium Viewer keeps a WebGL context and a render loop alive, and browsers cap contexts, so a few
//         leaks and the globe stops rendering entirely.
//
//         Camera state never enters React state. It changes every frame, and a React render per frame
//         would destroy the frame budget; the camera is driven imperatively and exposed to the rest of the
//         application through GlobeViewerHandle instead.
//
//         Idle rotation distinguishes an operator preference from a temporary pause. Dragging suspends
//         rotation and it resumes a beat after release, but an explicit "stop rotating" stays off until
//         explicitly resumed. Conflating the two makes the globe feel like it ignores instructions.

"use client";

import {
  Cartesian3,
  Color,
  DynamicAtmosphereLightingType,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  Viewer,
  type Cartesian2,
} from "cesium";
import { useEffect, useRef } from "react";

import { GLOBE_APPEARANCE, GLOBE_CAMERA, GLOBE_MAX_RESOLUTION_SCALE } from "@/lib/constants/globe";
import { AERIS_COLOR_HEX } from "@/lib/constants/theme";

import { useGlobeLayers } from "../../hooks/use-globe-layers";
import { useMissionCommandStore } from "../../store/mission-command-store";
import type { GlobeFlyToTarget, GlobeMarker } from "../../types/globe.types";
import {
  createEllipsoidTerrain,
  createFallbackImageryLayer,
  hasIonAccess,
  upgradeToIonImageryAndTerrain,
} from "./cesium-runtime";
import { createMissionMarkerLayer, type MissionMarkerLayer } from "./mission-marker-layer";
import { createSatelliteArcLayer, type SatelliteArcLayer } from "./satellite-arc-layer";

import "cesium/Build/Cesium/Widgets/widgets.css";

interface CesiumGlobeProps {
  isMotionReduced: boolean;
  onMarkerSelect?: (marker: GlobeMarker) => void;
  onReady?: () => void;
}

export function CesiumGlobe({ isMotionReduced, onMarkerSelect, onReady }: CesiumGlobeProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const creditContainerRef = useRef<HTMLDivElement | null>(null);
  const markerLayerRef = useRef<MissionMarkerLayer | null>(null);
  const arcLayerRef = useRef<SatelliteArcLayer | null>(null);

  const setGlobeViewer = useMissionCommandStore((state) => state.setGlobeViewer);
  const { markers, satelliteTracks } = useGlobeLayers();

  // Mirrored so the mount effect never has to re-run when a callback identity or preference changes —
  // rebuilding the viewer would drop the WebGL context and restart the whole scene.
  const onMarkerSelectRef = useRef(onMarkerSelect);
  const onReadyRef = useRef(onReady);
  const isMotionReducedRef = useRef(isMotionReduced);

  useEffect(() => {
    onMarkerSelectRef.current = onMarkerSelect;
    onReadyRef.current = onReady;
    isMotionReducedRef.current = isMotionReduced;
  }, [isMotionReduced, onMarkerSelect, onReady]);

  useEffect(() => {
    const container = containerRef.current;
    const creditContainer = creditContainerRef.current;
    if (!container || !creditContainer) {
      return;
    }

    const viewer = new Viewer(container, {
      // Every stock widget is off: AERIS supplies its own controls so the interface stays one system.
      animation: false,
      timeline: false,
      baseLayerPicker: false,
      fullscreenButton: false,
      geocoder: false,
      homeButton: false,
      infoBox: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      selectionIndicator: false,
      creditContainer,
      baseLayer: createFallbackImageryLayer(),
      terrainProvider: createEllipsoidTerrain(),
    });

    const { scene, camera } = viewer;

    configureSceneAppearance(viewer);

    camera.setView({
      destination: Cartesian3.fromDegrees(
        GLOBE_CAMERA.home.longitude,
        GLOBE_CAMERA.home.latitude,
        GLOBE_CAMERA.home.altitudeMeters,
      ),
    });

    const cameraController = scene.screenSpaceCameraController;
    cameraController.minimumZoomDistance = GLOBE_CAMERA.minimumZoomAltitudeMeters;
    cameraController.maximumZoomDistance = GLOBE_CAMERA.maximumZoomAltitudeMeters;

    const markerLayer = createMissionMarkerLayer(scene);
    const arcLayer = createSatelliteArcLayer(scene);
    markerLayerRef.current = markerLayer;
    arcLayerRef.current = arcLayer;

    // ── Idle rotation state ────────────────────────────────────────────────────────────────────────
    let prefersAutoRotate = !isMotionReducedRef.current;
    let isInteracting = false;
    let isFlying = false;
    let resumeTimeoutId: number | null = null;
    let lastFrameMs = performance.now();

    const clearResumeTimer = () => {
      if (resumeTimeoutId !== null) {
        window.clearTimeout(resumeTimeoutId);
        resumeTimeoutId = null;
      }
    };

    const pauseRotation = () => {
      clearResumeTimer();
      isInteracting = true;
    };

    const scheduleRotationResume = () => {
      clearResumeTimer();
      resumeTimeoutId = window.setTimeout(() => {
        isInteracting = false;
        resumeTimeoutId = null;
      }, GLOBE_CAMERA.idleResumeDelayMs);
    };

    const onPreUpdate = () => {
      const now = performance.now();
      // Clamped so a backgrounded tab does not resume with one enormous rotation step.
      const deltaSeconds = Math.min((now - lastFrameMs) / 1000, 0.1);
      lastFrameMs = now;

      const elapsedSeconds = now / 1000;
      markerLayer.update(elapsedSeconds);
      arcLayer.update(elapsedSeconds);

      if (prefersAutoRotate && !isInteracting && !isFlying) {
        camera.rotate(
          Cartesian3.UNIT_Z,
          -GLOBE_CAMERA.idleRotationRadiansPerSecond * deltaSeconds,
        );
      }
    };
    scene.preUpdate.addEventListener(onPreUpdate);

    // ── Input ──────────────────────────────────────────────────────────────────────────────────────
    const inputHandler = new ScreenSpaceEventHandler(viewer.canvas);

    for (const downEvent of [
      ScreenSpaceEventType.LEFT_DOWN,
      ScreenSpaceEventType.MIDDLE_DOWN,
      ScreenSpaceEventType.RIGHT_DOWN,
      ScreenSpaceEventType.PINCH_START,
    ]) {
      inputHandler.setInputAction(pauseRotation, downEvent);
    }

    for (const upEvent of [
      ScreenSpaceEventType.LEFT_UP,
      ScreenSpaceEventType.MIDDLE_UP,
      ScreenSpaceEventType.RIGHT_UP,
      ScreenSpaceEventType.PINCH_END,
    ]) {
      inputHandler.setInputAction(scheduleRotationResume, upEvent);
    }

    inputHandler.setInputAction(() => {
      pauseRotation();
      scheduleRotationResume();
    }, ScreenSpaceEventType.WHEEL);

    inputHandler.setInputAction((movement: { position: Cartesian2 }) => {
      const marker = markerLayer.resolvePick(scene.pick(movement.position));
      if (marker) {
        onMarkerSelectRef.current?.(marker);
      }
    }, ScreenSpaceEventType.LEFT_CLICK);

    // ── Camera verbs published to the rest of the application ──────────────────────────────────────
    const flyToTarget = (target: GlobeFlyToTarget) => {
      if (viewer.isDestroyed()) {
        return;
      }

      const altitude = target.altitudeMeters ?? GLOBE_CAMERA.locateAltitudeMeters;
      const durationSeconds = isMotionReducedRef.current
        ? 0
        : (target.durationMs ?? GLOBE_CAMERA.flyDurationSeconds * 1000) / 1000;

      isFlying = true;
      camera.flyTo({
        destination: Cartesian3.fromDegrees(target.longitude, target.latitude, altitude),
        duration: durationSeconds,
        complete: () => {
          isFlying = false;
        },
        cancel: () => {
          isFlying = false;
        },
      });
    };

    const zoomByFactor = (factor: number) => {
      if (viewer.isDestroyed()) {
        return;
      }

      const current = camera.positionCartographic;
      const nextHeight = Math.max(
        GLOBE_CAMERA.minimumZoomAltitudeMeters,
        Math.min(GLOBE_CAMERA.maximumZoomAltitudeMeters, current.height * factor),
      );

      isFlying = true;
      camera.flyTo({
        // Straight up or down over the point the camera already sits above, so zooming never
        // relocates the operator.
        destination: Cartesian3.fromRadians(current.longitude, current.latitude, nextHeight),
        duration: isMotionReducedRef.current ? 0 : GLOBE_CAMERA.zoomDurationSeconds,
        complete: () => {
          isFlying = false;
        },
        cancel: () => {
          isFlying = false;
        },
      });
    };

    setGlobeViewer({
      flyTo: flyToTarget,
      zoomByFactor,
      resetView: () =>
        flyToTarget({
          latitude: GLOBE_CAMERA.home.latitude,
          longitude: GLOBE_CAMERA.home.longitude,
          altitudeMeters: GLOBE_CAMERA.home.altitudeMeters,
        }),
      setAutoRotate: (isEnabled: boolean) => {
        prefersAutoRotate = isEnabled;
        if (isEnabled) {
          clearResumeTimer();
          isInteracting = false;
        }
      },
      isAutoRotating: () => prefersAutoRotate,
    });

    // Ion imagery and terrain arrive after the globe is already drawing, so the operator never waits on
    // a network round trip to see an Earth.
    if (hasIonAccess()) {
      void upgradeToIonImageryAndTerrain(viewer);
    }

    // Report readiness only once the globe has actually painted a frame.
    const onFirstRender = () => {
      scene.postRender.removeEventListener(onFirstRender);
      onReadyRef.current?.();
    };
    scene.postRender.addEventListener(onFirstRender);

    return () => {
      clearResumeTimer();
      inputHandler.destroy();
      markerLayer.destroy();
      arcLayer.destroy();
      markerLayerRef.current = null;
      arcLayerRef.current = null;
      setGlobeViewer(null);

      if (!viewer.isDestroyed()) {
        scene.preUpdate.removeEventListener(onPreUpdate);
        viewer.destroy();
      }
    };
  }, [setGlobeViewer]);

  // Marker and arc data arrive asynchronously and change independently of the viewer's lifetime.
  useEffect(() => {
    markerLayerRef.current?.setMarkers(markers);
  }, [markers]);

  useEffect(() => {
    arcLayerRef.current?.setTracks(
      satelliteTracks.map((track) => ({
        id: track.id,
        origin: track.origin,
        destination: track.destination,
        // The feed's phase doubles as the pulse offset, so no two arcs fire in unison.
        phase: track.phase,
      })),
    );
  }, [satelliteTracks]);

  return (
    <>
      <div ref={containerRef} className="absolute inset-0" />
      <div
        ref={creditContainerRef}
        // Attribution is a licensing requirement for every basemap in use, so it is styled to fit rather
        // than hidden.
        className="pointer-events-none absolute right-2 bottom-1 z-10 font-mono text-[9px] text-muted-foreground/50 [&_a]:pointer-events-auto [&_a]:text-muted-foreground/60"
      />
    </>
  );
}

/** Applies the AERIS look to a freshly created viewer. */
function configureSceneAppearance(viewer: Viewer): void {
  const { scene } = viewer;

  scene.globe.baseColor = Color.fromCssColorString(AERIS_COLOR_HEX.black);
  scene.globe.enableLighting = GLOBE_APPEARANCE.enableSunLighting;
  scene.globe.showGroundAtmosphere = GLOBE_APPEARANCE.showGroundAtmosphere;
  // Without this, markers on the far side of the planet draw straight through it.
  scene.globe.depthTestAgainstTerrain = true;

  if (scene.skyAtmosphere) {
    scene.skyAtmosphere.show = GLOBE_APPEARANCE.showSkyAtmosphere;
  }

  // A slight cool shift ties the atmosphere to the AERIS palette without tinting the landmass itself.
  scene.atmosphere.hueShift = GLOBE_APPEARANCE.atmosphereHueShift;
  scene.atmosphere.saturationShift = GLOBE_APPEARANCE.atmosphereSaturationShift;
  scene.atmosphere.brightnessShift = GLOBE_APPEARANCE.atmosphereBrightnessShift;
  // Lets the atmosphere respond to the sun position instead of glowing uniformly all the way round.
  scene.atmosphere.dynamicLighting = DynamicAtmosphereLightingType.SUNLIGHT;

  scene.backgroundColor = Color.fromCssColorString(AERIS_COLOR_HEX.void);
  scene.fog.enabled = true;
  scene.highDynamicRange = false;

  // Uncapped device pixel ratio on a high-density display is the most common cause of an otherwise
  // healthy globe running at thirty frames per second.
  viewer.resolutionScale = Math.min(window.devicePixelRatio, GLOBE_MAX_RESOLUTION_SCALE);

  // A little tilt tolerance keeps the horizon from clipping awkwardly when the operator drags near a pole.
  viewer.camera.constrainedAxis = Cartesian3.UNIT_Z;
  scene.screenSpaceCameraController.enableCollisionDetection = true;
  scene.screenSpaceCameraController.inertiaSpin = 0.85;
  scene.screenSpaceCameraController.inertiaZoom = 0.8;
  scene.screenSpaceCameraController.inertiaTranslate = 0.85;

  // Cesium defaults to a very fast rotate; slow it so the globe feels weighty rather than twitchy.
  scene.screenSpaceCameraController.maximumMovementRatio = 0.35;
}

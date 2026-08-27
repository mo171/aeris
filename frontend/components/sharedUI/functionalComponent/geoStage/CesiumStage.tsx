// components/sharedUI/functionalComponent/geoStage/CesiumStage.tsx — the one Cesium viewer the whole application shares.
//
// what  : Owns the Viewer lifecycle, assembles every layer set, runs the single per-frame update loop,
//         handles input, and publishes the GeoStageHandle that both Mission Command and the Investigation
//         Workspace drive the Earth through.
// where : Mounted once by app/(geospatial)/layout.tsx, above every page in that route group. This file and
//         its siblings in this folder are the ONLY files in the application permitted to import `cesium`.
// how   : One viewer, for the lifetime of the route group. That is the entire reason this file exists.
//         Next.js unmounts a page's tree on navigation, so a viewer owned by a feature would be destroyed
//         mid-flight and the globe-to-AOI descent would degrade into freeze, boot a second WebGL context,
//         cross-fade. Owning it in the layout keeps the camera moving across the route change, so the
//         descent is one continuous move rather than a simulation of one.
//
//         The stage has two modes because it is two instruments. In `globe` mode it is orbital: markers,
//         satellite arcs, idle rotation, orbital zoom limits. In `scene` mode it is close-range: operator
//         imagery, evidence geometry, the comparator, tight zoom limits and a recessed basemap. Switching
//         modes is a method call, not a remount, so nothing about the transition touches WebGL.
//
//         Camera state never enters React. It changes every frame, and a render per frame would spend the
//         budget this page exists to showcase. Everything outside reaches the camera imperatively through
//         the published handle.
//
//         `requestRenderMode` is deliberately left off. The scene always has something animating — pulsing
//         arcs on the globe, revealing evidence and a moving comparator in the workspace — so render-on-
//         demand would require calling requestRender every frame anyway, which is strictly worse than not
//         enabling it.

"use client";

import {
  BoundingSphere,
  Cartesian3,
  Cartographic,
  Color,
  DynamicAtmosphereLightingType,
  Ellipsoid,
  HeadingPitchRange,
  Math as CesiumMath,
  Rectangle,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  Viewer,
  type Cartesian2,
} from "cesium";
import { useEffect, useRef } from "react";

import {
  GLOBE_APPEARANCE,
  GLOBE_CAMERA,
  GLOBE_HIDDEN_TAB_RENDER_INTERVAL_MS,
  GLOBE_MAX_RESOLUTION_SCALE,
  GLOBE_PROJECTION_MORPH_SECONDS,
} from "@/lib/constants/globe";
import { INVESTIGATION_CAMERA } from "@/lib/constants/investigation";
import { LAYER_RENDERING } from "@/lib/constants/layers";
import { AERIS_COLOR_HEX } from "@/lib/constants/theme";
import { useGeoStageStore } from "@/store/geo-stage-store";

import {
  createEllipsoidTerrain,
  createFallbackImageryLayer,
  hasIonAccess,
  upgradeToIonImageryAndTerrain,
} from "./cesium-runtime";
import type {
  GeoStageHandle,
  StageBoundingBox,
  StageCameraBookmark,
  StageFlyToTarget,
  StageFrameOptions,
  StageLayerRenderMode,
  StageMode,
  StageProjection,
} from "./geo-stage.types";
import { createAreaOfInterestOutlineLayer } from "./layers/aoi-outline-layer";
import { createEvidenceVectorLayerSet } from "./layers/evidence-vector-layer";
import { createMissionMarkerLayer } from "./layers/mission-marker-layer";
import { createSatelliteArcLayer } from "./layers/satellite-arc-layer";
import { createSceneImageryLayerSet } from "./layers/scene-imagery-layer";
import { createDrawController } from "./region-draw";
import { createSplitComparator } from "./split-comparator";

import "cesium/Build/Cesium/Widgets/widgets.css";

interface CesiumStageProps {
  isMotionReduced: boolean;
  onReady?: () => void;
}

export function CesiumStage({ isMotionReduced, onReady }: CesiumStageProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const creditContainerRef = useRef<HTMLDivElement | null>(null);

  // Mirrored so the mount effect never re-runs on a prop change — rebuilding the viewer would drop the
  // WebGL context, and browsers cap how many of those a page may hold.
  const isMotionReducedRef = useRef(isMotionReduced);
  const onReadyRef = useRef(onReady);

  useEffect(() => {
    isMotionReducedRef.current = isMotionReduced;
    onReadyRef.current = onReady;
  }, [isMotionReduced, onReady]);

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
    const basemapLayer = viewer.imageryLayers.get(0);

    configureSceneAppearance(viewer);

    camera.setView({
      destination: Cartesian3.fromDegrees(
        GLOBE_CAMERA.home.longitude,
        GLOBE_CAMERA.home.latitude,
        GLOBE_CAMERA.home.altitudeMeters,
      ),
    });

    // ── Layer sets ─────────────────────────────────────────────────────────────────────────────────
    const markerLayer = createMissionMarkerLayer(scene);
    const arcLayer = createSatelliteArcLayer(scene);
    const sceneImagery = createSceneImageryLayerSet(scene);
    const evidenceVectors = createEvidenceVectorLayerSet(viewer);
    const aoiOutline = createAreaOfInterestOutlineLayer(viewer);
    const comparator = createSplitComparator(scene);
    const draw = createDrawController(viewer);

    // ── Stage state ────────────────────────────────────────────────────────────────────────────────
    let mode: StageMode = "globe";
    let renderMode: StageLayerRenderMode = "draped";
    let prefersAutoRotate = !isMotionReducedRef.current;
    let isInteracting = false;
    let isFlying = false;
    let resumeTimeoutId: number | null = null;
    let lastFrameMs = performance.now();
    let orbitAxis = Cartesian3.clone(Cartesian3.UNIT_Z);
    let basemapBrightness: number = GLOBE_APPEARANCE.imageryBrightness;
    let projection: StageProjection = "3D";
    let onMarkerClick: ((markerId: string) => void) | null = null;
    let onFeatureClick: ((featureId: string, layerId: string) => void) | null = null;

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

    const applyZoomLimits = (minimumMeters: number, maximumMeters: number) => {
      scene.screenSpaceCameraController.minimumZoomDistance = minimumMeters;
      scene.screenSpaceCameraController.maximumZoomDistance = maximumMeters;
    };

    applyZoomLimits(
      GLOBE_CAMERA.minimumZoomAltitudeMeters,
      GLOBE_CAMERA.maximumZoomAltitudeMeters,
    );

    // ── The single per-frame update loop ───────────────────────────────────────────────────────────
    const onPreUpdate = () => {
      const now = performance.now();
      // Clamped so a backgrounded tab does not resume with one enormous rotation step.
      const deltaSeconds = Math.min((now - lastFrameMs) / 1000, 0.1);
      lastFrameMs = now;
      const elapsedSeconds = now / 1000;

      markerLayer.update(elapsedSeconds);
      arcLayer.update(elapsedSeconds);
      sceneImagery.update(now);
      evidenceVectors.update(now);
      aoiOutline.update(now);
      comparator.update(now);

      if (prefersAutoRotate && !isInteracting && !isFlying) {
        const rate =
          mode === "globe"
            ? GLOBE_CAMERA.idleRotationRadiansPerSecond
            : INVESTIGATION_CAMERA.presentOrbitRadiansPerSecond;
        camera.rotate(orbitAxis, -rate * deltaSeconds);
      }
    };
    scene.preUpdate.addEventListener(onPreUpdate);

    // ── Reaching first paint in a background tab ───────────────────────────────────────────────────
    // requestAnimationFrame is starved in a hidden tab, so Cesium's own loop never runs and the scene
    // never paints. A workspace opened in a background tab would then still be showing its loading state
    // when the operator finally switches to it, because readiness is reported from postRender.
    //
    // Timers keep firing when hidden, so the loop is handed to one — but ONLY until a frame has actually
    // been painted. Past that point a hidden tab has nothing to show anyone, and continuing to render a
    // full globe on a timer would burn a laptop battery to keep an invisible surface up to date.
    let hiddenRenderTimerId: number | null = null;
    let hasPaintedOnce = false;

    const stopHiddenRenderLoop = () => {
      if (hiddenRenderTimerId !== null) {
        window.clearInterval(hiddenRenderTimerId);
        hiddenRenderTimerId = null;
      }
    };

    const syncRenderLoopToVisibility = () => {
      if (viewer.isDestroyed()) {
        return;
      }

      const shouldDriveManually = document.visibilityState === "hidden" && !hasPaintedOnce;

      if (shouldDriveManually && hiddenRenderTimerId === null) {
        // Cesium's own loop is switched off first, so the two never drive the scene at once.
        viewer.useDefaultRenderLoop = false;
        hiddenRenderTimerId = window.setInterval(() => {
          if (viewer.isDestroyed()) {
            stopHiddenRenderLoop();
            return;
          }
          try {
            viewer.render();
          } catch {
            // A render that throws while hidden must not leave a timer hammering a broken scene.
            stopHiddenRenderLoop();
          }
        }, GLOBE_HIDDEN_TAB_RENDER_INTERVAL_MS);
        return;
      }

      if (!shouldDriveManually && hiddenRenderTimerId !== null) {
        stopHiddenRenderLoop();
        viewer.useDefaultRenderLoop = true;
      }
    };

    document.addEventListener("visibilitychange", syncRenderLoopToVisibility);
    syncRenderLoopToVisibility();

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
      // A drawing tool owns the pointer while it is armed; a click through to a marker would be noise.
      if (draw.activeTool() !== null) {
        return;
      }

      const picked = scene.pick(movement.position);
      if (!picked) {
        return;
      }

      if (mode === "globe") {
        const marker = markerLayer.resolvePick(picked);
        if (marker) {
          onMarkerClick?.(marker.id);
        }
        return;
      }

      const feature = evidenceVectors.resolvePick(picked);
      if (feature) {
        onFeatureClick?.(feature.featureId, feature.layerId);
      }
    }, ScreenSpaceEventType.LEFT_CLICK);

    // ── Camera ─────────────────────────────────────────────────────────────────────────────────────
    const defaultAltitudeForMode = () =>
      mode === "globe" ? GLOBE_CAMERA.locateAltitudeMeters : INVESTIGATION_CAMERA.aoiAltitudeMeters;

    const defaultFlightMs = () =>
      (mode === "globe"
        ? GLOBE_CAMERA.flyDurationSeconds
        : INVESTIGATION_CAMERA.localFlightDurationSeconds) * 1000;

    const markFlightStart = () => {
      isFlying = true;
    };
    const markFlightEnd = () => {
      isFlying = false;
    };

    const flyTo = (target: StageFlyToTarget) => {
      if (viewer.isDestroyed()) {
        return;
      }

      const altitude = target.altitudeMeters ?? defaultAltitudeForMode();
      const durationSeconds = isMotionReducedRef.current
        ? 0
        : (target.durationMs ?? defaultFlightMs()) / 1000;

      markFlightStart();
      camera.flyTo({
        destination: Cartesian3.fromDegrees(target.longitude, target.latitude, altitude),
        orientation:
          target.pitchDegrees === undefined && target.headingDegrees === undefined
            ? undefined
            : {
                heading: CesiumMath.toRadians(target.headingDegrees ?? 0),
                pitch: CesiumMath.toRadians(target.pitchDegrees ?? -90),
                roll: 0,
              },
        duration: durationSeconds,
        complete: markFlightEnd,
        cancel: markFlightEnd,
      });
    };

    const flyToBoundingBox = (bounds: StageBoundingBox, options?: StageFrameOptions) => {
      if (viewer.isDestroyed()) {
        return;
      }

      const margin = options?.marginRatio ?? INVESTIGATION_CAMERA.frameMarginRatio;
      const width = Math.abs(bounds.east - bounds.west);
      const height = Math.abs(bounds.north - bounds.south);
      const rectangle = Rectangle.fromDegrees(
        bounds.west - width * margin,
        bounds.south - height * margin,
        bounds.east + width * margin,
        bounds.north + height * margin,
      );

      const durationSeconds = isMotionReducedRef.current
        ? 0
        : (options?.durationMs ?? defaultFlightMs()) / 1000;

      markFlightStart();
      // A bounding sphere with a range of zero lets Cesium compute the distance that fits the whole
      // extent, which is exactly right and avoids hand-rolling a field-of-view calculation.
      camera.flyToBoundingSphere(BoundingSphere.fromRectangle3D(rectangle), {
        offset: new HeadingPitchRange(
          0,
          CesiumMath.toRadians(options?.pitchDegrees ?? INVESTIGATION_CAMERA.restingPitchDegrees),
          0,
        ),
        duration: durationSeconds,
        complete: markFlightEnd,
        cancel: markFlightEnd,
      });
    };

    const zoomByFactor = (factor: number) => {
      if (viewer.isDestroyed()) {
        return;
      }

      const current = camera.positionCartographic;
      const limits =
        mode === "globe"
          ? {
              minimum: GLOBE_CAMERA.minimumZoomAltitudeMeters,
              maximum: GLOBE_CAMERA.maximumZoomAltitudeMeters,
            }
          : {
              minimum: INVESTIGATION_CAMERA.minimumZoomAltitudeMeters,
              maximum: INVESTIGATION_CAMERA.maximumZoomAltitudeMeters,
            };

      const nextHeight = Math.max(
        limits.minimum,
        Math.min(limits.maximum, current.height * factor),
      );

      markFlightStart();
      camera.flyTo({
        // Straight up or down over the point already beneath the camera, so zooming never relocates
        // the operator.
        destination: Cartesian3.fromRadians(current.longitude, current.latitude, nextHeight),
        duration: isMotionReducedRef.current
          ? 0
          : mode === "globe"
            ? GLOBE_CAMERA.zoomDurationSeconds
            : INVESTIGATION_CAMERA.zoomDurationSeconds,
        complete: markFlightEnd,
        cancel: markFlightEnd,
      });
    };

    const getBookmark = (): StageCameraBookmark | null => {
      if (viewer.isDestroyed()) {
        return null;
      }
      const position = camera.positionCartographic;
      return {
        latitude: CesiumMath.toDegrees(position.latitude),
        longitude: CesiumMath.toDegrees(position.longitude),
        altitudeMeters: position.height,
        headingDegrees: CesiumMath.toDegrees(camera.heading),
        pitchDegrees: CesiumMath.toDegrees(camera.pitch),
      };
    };

    const applyBookmark = (bookmark: StageCameraBookmark, durationMs?: number) => {
      flyTo({
        latitude: bookmark.latitude,
        longitude: bookmark.longitude,
        altitudeMeters: bookmark.altitudeMeters,
        headingDegrees: bookmark.headingDegrees,
        pitchDegrees: bookmark.pitchDegrees,
        durationMs,
      });
    };

    /** Orbiting in scene mode must spin around the area of interest, not around the planet's poles. */
    const setOrbitCentre = (bounds: StageBoundingBox | null) => {
      if (!bounds) {
        orbitAxis = Cartesian3.clone(Cartesian3.UNIT_Z);
        return;
      }
      const centre = Cartographic.fromDegrees(
        (bounds.west + bounds.east) / 2,
        (bounds.south + bounds.north) / 2,
      );
      // The axis runs from the Earth's centre through the AOI, so rotating about it carries the camera
      // around that point rather than around the pole.
      orbitAxis = Ellipsoid.WGS84.geodeticSurfaceNormalCartographic(centre);
    };

    // ── The published handle ───────────────────────────────────────────────────────────────────────
    const handle: GeoStageHandle = {
      camera: {
        flyTo,
        flyToBoundingBox,
        zoomByFactor,
        getBookmark,
        applyBookmark,
        setAutoRotate: (isEnabled) => {
          prefersAutoRotate = isEnabled;
          if (isEnabled) {
            clearResumeTimer();
            isInteracting = false;
          }
        },
        isAutoRotating: () => prefersAutoRotate,
        setZoomLimits: applyZoomLimits,
        isFlying: () => isFlying,
      },

      globeLayers: {
        setMarkers: (markers) => markerLayer.setMarkers(markers),
        setSatelliteTracks: (tracks) => arcLayer.setTracks(tracks),
        setMarkerClickHandler: (handler) => {
          onMarkerClick = handler;
        },
        clear: () => {
          markerLayer.setMarkers([]);
          arcLayer.setTracks([]);
        },
      },

      sceneLayers: {
        setLayers: (layers) => {
          sceneImagery.sync(layers);
          evidenceVectors.sync(layers, renderMode);
        },
        setLayerVisibility: (layerId, isVisible) => {
          sceneImagery.setVisibility(layerId, isVisible);
          evidenceVectors.setVisibility(layerId, isVisible);
        },
        setLayerOpacity: (layerId, opacity) => {
          sceneImagery.setOpacity(layerId, opacity);
          evidenceVectors.setOpacity(layerId, opacity);
        },
        setRenderMode: (nextRenderMode) => {
          renderMode = nextRenderMode;
          evidenceVectors.setRenderMode(nextRenderMode);
        },
        setSpotlight: (featureIds) => {
          evidenceVectors.setSpotlight(featureIds);
          // The scene recedes so the evidence does not have to shout. Dimming the imagery is cheaper and
          // cleaner than masking geometry, and it reads as a spotlight rather than as a filter.
          const isSpotlightActive = featureIds !== null;
          sceneImagery.setGlobalDim(
            isSpotlightActive ? LAYER_RENDERING.spotlightSceneDimRatio : 1,
          );
          basemapLayer.brightness = isSpotlightActive
            ? basemapBrightness * LAYER_RENDERING.spotlightDimBrightness
            : basemapBrightness;
        },
        setFeatureClickHandler: (handler) => {
          onFeatureClick = handler;
        },
        setAreaOfInterestOutline: (bounds) => {
          aoiOutline.set(bounds);
          setOrbitCentre(bounds);
        },
        clear: () => {
          sceneImagery.clear();
          evidenceVectors.clear();
          aoiOutline.set(null);
          comparator.reset();
          draw.clearAll();
          basemapLayer.brightness = basemapBrightness;
        },
      },

      comparator: {
        bind: (leftLayerId, rightLayerId) => sceneImagery.bindComparator(leftLayerId, rightLayerId),
        setPosition: comparator.setPosition,
        getPosition: comparator.getPosition,
        sweep: comparator.sweep,
        setPlayback: comparator.setPlayback,
        isPlaying: comparator.isPlaying,
        subscribe: comparator.subscribe,
      },

      draw: {
        begin: draw.begin,
        complete: draw.complete,
        undoVertex: draw.undoVertex,
        cancel: draw.cancel,
        isDrawing: draw.isDrawing,
        activeTool: draw.activeTool,
        clearAll: draw.clearAll,
        removeRegion: draw.removeRegion,
        subscribeRegions: draw.subscribeRegions,
        subscribeLive: draw.subscribeLive,
      },

      appearance: {
        setMode: (nextMode) => {
          if (nextMode === mode) {
            return;
          }
          mode = nextMode;

          if (nextMode === "globe") {
            handle.sceneLayers.clear();
            applyZoomLimits(
              GLOBE_CAMERA.minimumZoomAltitudeMeters,
              GLOBE_CAMERA.maximumZoomAltitudeMeters,
            );
            orbitAxis = Cartesian3.clone(Cartesian3.UNIT_Z);
            basemapBrightness = GLOBE_APPEARANCE.imageryBrightness;
            prefersAutoRotate = !isMotionReducedRef.current;
          } else {
            handle.globeLayers.clear();
            applyZoomLimits(
              INVESTIGATION_CAMERA.minimumZoomAltitudeMeters,
              INVESTIGATION_CAMERA.maximumZoomAltitudeMeters,
            );
            // The operator's own imagery is the subject in scene mode; the basemap is context and steps
            // back so it never competes with what the sensor actually saw.
            basemapBrightness = 0.62;
            prefersAutoRotate = false;
          }

          basemapLayer.brightness = basemapBrightness;
        },
        getMode: () => mode,

        setProjection: (nextProjection) => {
          if (nextProjection === projection || viewer.isDestroyed()) {
            return;
          }
          projection = nextProjection;

          // Morphing rather than cutting, because the transition is itself informative: watching the
          // globe flatten tells the operator these are the same pixels seen a different way, which a
          // hard switch between two views does not.
          const durationSeconds = isMotionReducedRef.current
            ? 0
            : GLOBE_PROJECTION_MORPH_SECONDS;

          if (nextProjection === "2D") {
            scene.morphTo2D(durationSeconds);
          } else if (nextProjection === "columbus") {
            scene.morphToColumbusView(durationSeconds);
          } else {
            scene.morphTo3D(durationSeconds);
          }
        },
        getProjection: () => projection,

        setBasemapBrightness: (brightness) => {
          basemapBrightness = brightness;
          basemapLayer.brightness = brightness;
        },
        setMotionReduced: (isReduced) => {
          isMotionReducedRef.current = isReduced;
          if (isReduced) {
            prefersAutoRotate = false;
          }
        },
      },
    };

    const { setHandle, setReady } = useGeoStageStore.getState();
    setHandle(handle);

    // Ion imagery and terrain arrive after the globe is already drawing, so the operator never waits on
    // a network round trip to see an Earth.
    if (hasIonAccess()) {
      void upgradeToIonImageryAndTerrain(viewer);
    }

    // Readiness is reported only once a frame has actually been painted, never on construction.
    const onFirstRender = () => {
      scene.postRender.removeEventListener(onFirstRender);
      // The manual loop existed only to reach this moment; from here the browser's own loop is enough.
      hasPaintedOnce = true;
      syncRenderLoopToVisibility();
      setReady(true);
      onReadyRef.current?.();
    };
    scene.postRender.addEventListener(onFirstRender);

    return () => {
      clearResumeTimer();
      stopHiddenRenderLoop();
      document.removeEventListener("visibilitychange", syncRenderLoopToVisibility);
      inputHandler.destroy();
      draw.destroy();
      markerLayer.destroy();
      arcLayer.destroy();
      sceneImagery.destroy();
      evidenceVectors.clear();
      aoiOutline.destroy();

      const store = useGeoStageStore.getState();
      store.setHandle(null);
      store.setReady(false);

      if (!viewer.isDestroyed()) {
        scene.preUpdate.removeEventListener(onPreUpdate);
        viewer.destroy();
      }
    };
  }, []);

  return (
    <>
      <div ref={containerRef} className="absolute inset-0" />
      <div
        ref={creditContainerRef}
        // Attribution is a licensing requirement for every basemap and tile source in use, so it is
        // styled to fit rather than hidden.
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
  // healthy scene running at thirty frames per second.
  viewer.resolutionScale = Math.min(window.devicePixelRatio, GLOBE_MAX_RESOLUTION_SCALE);

  viewer.camera.constrainedAxis = Cartesian3.UNIT_Z;
  scene.screenSpaceCameraController.enableCollisionDetection = true;
  scene.screenSpaceCameraController.inertiaSpin = 0.85;
  scene.screenSpaceCameraController.inertiaZoom = 0.8;
  scene.screenSpaceCameraController.inertiaTranslate = 0.85;

  // Cesium defaults to a very fast rotate; slow it so the Earth feels weighty rather than twitchy.
  scene.screenSpaceCameraController.maximumMovementRatio = 0.35;
}

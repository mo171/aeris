// features/missionCommand/components/globe/GlobeCameraRig.tsx — orbit control, idle rotation and fly-to.
//
// what  : Owns the camera. Provides damped orbiting, idle auto-rotation that yields to the operator, and
//         an eased fly-to animation. Publishes the GlobeViewerHandle that the rest of the app drives.
// where : Rendered inside GlobeScene; the handle it publishes is consumed by the globe commands.
// how   : This is the component that makes the renderer swappable. Everything outside the globe folder
//         interacts with the camera through GlobeViewerHandle — flyTo, resetView, setAutoRotate — and
//         never touches three.js. Replacing this rig with a CesiumJS equivalent means satisfying the same
//         four methods; no command, hook or component above it changes.
//
//         Auto-rotation distinguishes an operator preference from a temporary pause. Dragging the globe
//         suspends rotation and it resumes a beat after release, but an explicit "stop rotating" command
//         stays off until explicitly turned back on. Conflating the two makes the globe feel like it is
//         ignoring instructions.

"use client";

import { useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { useCallback, useEffect, useRef, useState, type ComponentRef } from "react";
import { Vector3 } from "three";

import { GLOBE_CAMERA, GLOBE_RADIUS } from "@/lib/constants/globe";
import type { GlobeFlyToTarget } from "@/features/missionCommand/types/globe.types";

import { useMissionCommandStore } from "../../store/mission-command-store";
import { geographicToCartesian } from "./globe-geometry";

const DEFAULT_FLY_DURATION_MS = 1_400;
const FLY_TO_DISTANCE = 1.85;

interface GlobeCameraRigProps {
  isMotionReduced: boolean;
  onReady?: () => void;
}

interface FlightState {
  from: Vector3;
  to: Vector3;
  startedAt: number;
  durationSeconds: number;
}

export function GlobeCameraRig({ isMotionReduced, onReady }: GlobeCameraRigProps) {
  const setGlobeViewer = useMissionCommandStore((state) => state.setGlobeViewer);
  // The control implementation type is read from the drei component itself, avoiding a direct
  // dependency on three-stdlib for a single type.
  const controlsRef = useRef<ComponentRef<typeof OrbitControls> | null>(null);
  const flightRef = useRef<FlightState | null>(null);
  const resumeTimeoutRef = useRef<number | null>(null);

  const [prefersAutoRotate, setPrefersAutoRotate] = useState(!isMotionReduced);
  const [isInteracting, setIsInteracting] = useState(false);
  const [isFlying, setIsFlying] = useState(false);

  const { camera, clock } = useThree();

  const startFlight = useCallback(
    (target: GlobeFlyToTarget) => {
      const direction = geographicToCartesian(target.latitude, target.longitude, GLOBE_RADIUS);
      const distance = clampDistance(target.distance ?? FLY_TO_DISTANCE);
      const destination = new Vector3(direction.x, direction.y, direction.z)
        .normalize()
        .multiplyScalar(distance);

      const durationSeconds = isMotionReduced
        ? 0
        : (target.durationMs ?? DEFAULT_FLY_DURATION_MS) / 1000;

      if (durationSeconds === 0) {
        camera.position.copy(destination);
        controlsRef.current?.update();
        return;
      }

      flightRef.current = {
        from: camera.position.clone(),
        to: destination,
        startedAt: clock.elapsedTime,
        durationSeconds,
      };
      setIsFlying(true);
    },
    [camera, clock, isMotionReduced],
  );

  const resetView = useCallback(() => {
    startFlight({ latitude: 20, longitude: 78, distance: GLOBE_CAMERA.initialDistance });
  }, [startFlight]);

  /**
   * Zoom keeps the camera on its current view axis and only changes its distance from the globe, so the
   * operator never loses the region they were looking at. Animating it through the same flight mechanism
   * means zoom shares the easing curve of every other camera move.
   */
  const zoomBy = useCallback(
    (distanceDelta: number) => {
      const currentDistance = camera.position.length();
      const targetDistance = clampDistance(currentDistance + distanceDelta);
      const destination = camera.position.clone().normalize().multiplyScalar(targetDistance);

      if (isMotionReduced) {
        camera.position.copy(destination);
        controlsRef.current?.update();
        return;
      }

      flightRef.current = {
        from: camera.position.clone(),
        to: destination,
        startedAt: clock.elapsedTime,
        durationSeconds: 0.4,
      };
      setIsFlying(true);
    },
    [camera, clock, isMotionReduced],
  );

  // Publish the imperative handle. Everything outside this folder drives the camera through it.
  useEffect(() => {
    setGlobeViewer({
      flyTo: startFlight,
      zoomBy,
      resetView,
      setAutoRotate: (isEnabled: boolean) => setPrefersAutoRotate(isEnabled),
      isAutoRotating: () => prefersAutoRotate,
    });

    return () => {
      setGlobeViewer(null);
    };
  }, [prefersAutoRotate, resetView, setGlobeViewer, startFlight, zoomBy]);

  useEffect(() => {
    onReady?.();
  }, [onReady]);

  useEffect(() => {
    return () => {
      if (resumeTimeoutRef.current !== null) {
        window.clearTimeout(resumeTimeoutRef.current);
      }
    };
  }, []);

  const handleInteractionStart = useCallback(() => {
    if (resumeTimeoutRef.current !== null) {
      window.clearTimeout(resumeTimeoutRef.current);
      resumeTimeoutRef.current = null;
    }
    setIsInteracting(true);
  }, []);

  const handleInteractionEnd = useCallback(() => {
    resumeTimeoutRef.current = window.setTimeout(() => {
      setIsInteracting(false);
      resumeTimeoutRef.current = null;
    }, GLOBE_CAMERA.idleResumeDelayMs);
  }, []);

  useFrame(() => {
    const flight = flightRef.current;
    if (!flight) {
      return;
    }

    const elapsed = clock.elapsedTime - flight.startedAt;
    const progress = Math.min(1, elapsed / flight.durationSeconds);
    camera.position.lerpVectors(flight.from, flight.to, easeOutExpo(progress));
    controlsRef.current?.update();

    if (progress >= 1) {
      flightRef.current = null;
      setIsFlying(false);
    }
  });

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enablePan={false}
      enableDamping
      dampingFactor={GLOBE_CAMERA.dampingFactor}
      rotateSpeed={0.42}
      zoomSpeed={0.6}
      minDistance={GLOBE_CAMERA.minDistance}
      maxDistance={GLOBE_CAMERA.maxDistance}
      autoRotate={prefersAutoRotate && !isInteracting && !isFlying}
      autoRotateSpeed={GLOBE_CAMERA.idleRotationSpeed * 10}
      onStart={handleInteractionStart}
      onEnd={handleInteractionEnd}
    />
  );
}

function clampDistance(distance: number): number {
  return Math.max(GLOBE_CAMERA.minDistance, Math.min(GLOBE_CAMERA.maxDistance, distance));
}

/** Matches the --ease-expo curve used across the interface, so 3D and DOM motion feel like one system. */
function easeOutExpo(progress: number): number {
  return progress >= 1 ? 1 : 1 - Math.pow(2, -10 * progress);
}

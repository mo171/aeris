// components/sharedUI/functionalComponent/geoStage/region-draw.ts — drawing an area of interest on the scene.
//
// what  : Captures a rectangle dragged on the globe, renders a live preview while the operator drags, and
//         emits real-world bounds plus the screen anchor the follow-up prompt attaches to.
// where : Owned by CesiumStage.tsx; driven by the Investigation Workspace's "ask this region" tool.
// how   : Camera input is disabled for the duration of a draw. Without that, dragging to define a box
//         also rotates the Earth underneath it, which makes the tool unusable — the single most important
//         detail in this file.
//
//         The preview rectangle is a CallbackProperty over a mutable pair of corners, so dragging never
//         rebuilds an entity. The screen anchor is captured at release rather than recomputed later: the
//         prompt should stay attached to where the operator finished, and a camera that keeps moving
//         would otherwise drag the popover around with it.
//
//         Coordinates come from `globe.pick` against the camera ray rather than from `scene.pickPosition`,
//         because pickPosition depends on a depth buffer that is not guaranteed over terrain-free areas.

import {
  CallbackProperty,
  Cartesian2,
  Cartographic,
  Color,
  CustomDataSource,
  Entity,
  Math as CesiumMath,
  Rectangle,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  type Viewer,
} from "cesium";

import { AERIS_COLOR_HEX } from "@/lib/constants/theme";

import type { StageBoundingBox, StageDrawnRegion, StageRegionDrawMode } from "./geo-stage.types";

type RegionListener = (region: StageDrawnRegion | null) => void;

export interface RegionDrawController {
  begin: (mode: StageRegionDrawMode) => void;
  cancel: () => void;
  isDrawing: () => boolean;
  clearRegion: () => void;
  subscribe: (listener: RegionListener) => () => void;
  destroy: () => void;
}

/** Below this the operator almost certainly clicked rather than dragged, and an empty box is meaningless. */
const MINIMUM_DRAG_PIXELS = 8;

export function createRegionDrawController(viewer: Viewer): RegionDrawController {
  const listeners = new Set<RegionListener>();
  const dataSource = new CustomDataSource("aeris-region-draw");
  void viewer.dataSources.add(dataSource);

  const handler = new ScreenSpaceEventHandler(viewer.canvas);
  const fillColor = Color.fromCssColorString(AERIS_COLOR_HEX.teal).withAlpha(0.12);
  const outlineColor = Color.fromCssColorString(AERIS_COLOR_HEX.teal).withAlpha(0.9);

  let isArmed = false;
  let isDragging = false;
  let startCartographic: Cartographic | null = null;
  let currentCartographic: Cartographic | null = null;
  let startScreen: Cartesian2 | null = null;
  let previewEntity: Entity | null = null;
  let committedEntity: Entity | null = null;

  function toCartographic(screenPosition: Cartesian2): Cartographic | null {
    const ray = viewer.camera.getPickRay(screenPosition);
    if (!ray) {
      return null;
    }
    const intersection = viewer.scene.globe.pick(ray, viewer.scene);
    return intersection ? Cartographic.fromCartesian(intersection) : null;
  }

  function currentRectangle(): Rectangle {
    if (!startCartographic || !currentCartographic) {
      return Rectangle.MAX_VALUE;
    }
    return Rectangle.fromCartographicArray([startCartographic, currentCartographic]);
  }

  function toBoundingBox(rectangle: Rectangle): StageBoundingBox {
    return {
      west: CesiumMath.toDegrees(rectangle.west),
      south: CesiumMath.toDegrees(rectangle.south),
      east: CesiumMath.toDegrees(rectangle.east),
      north: CesiumMath.toDegrees(rectangle.north),
    };
  }

  function ensurePreviewEntity(): void {
    if (previewEntity) {
      return;
    }
    previewEntity = new Entity({
      rectangle: {
        coordinates: new CallbackProperty(() => currentRectangle(), false),
        material: fillColor,
        outline: true,
        outlineColor,
        outlineWidth: 2,
        height: 0,
      },
    });
    dataSource.entities.add(previewEntity);
  }

  function removePreviewEntity(): void {
    if (previewEntity) {
      dataSource.entities.remove(previewEntity);
      previewEntity = null;
    }
  }

  function notify(region: StageDrawnRegion | null): void {
    for (const listener of listeners) {
      listener(region);
    }
  }

  function setCameraInputEnabled(isEnabled: boolean): void {
    viewer.scene.screenSpaceCameraController.enableInputs = isEnabled;
  }

  function finishDrag(endScreen: Cartesian2): void {
    const draggedFarEnough =
      startScreen !== null &&
      Cartesian2.distance(startScreen, endScreen) >= MINIMUM_DRAG_PIXELS;

    isDragging = false;
    isArmed = false;
    setCameraInputEnabled(true);

    if (!draggedFarEnough || !startCartographic || !currentCartographic) {
      removePreviewEntity();
      notify(null);
      return;
    }

    const rectangle = currentRectangle();
    const bounds = toBoundingBox(rectangle);

    removePreviewEntity();
    if (committedEntity) {
      dataSource.entities.remove(committedEntity);
    }
    committedEntity = new Entity({
      rectangle: {
        coordinates: rectangle,
        material: fillColor,
        outline: true,
        outlineColor,
        outlineWidth: 2,
        height: 0,
      },
    });
    dataSource.entities.add(committedEntity);

    notify({
      bounds,
      ring: [
        { longitude: bounds.west, latitude: bounds.south },
        { longitude: bounds.east, latitude: bounds.south },
        { longitude: bounds.east, latitude: bounds.north },
        { longitude: bounds.west, latitude: bounds.north },
      ],
      screenAnchor: { x: endScreen.x, y: endScreen.y },
    });
  }

  handler.setInputAction((movement: { position: Cartesian2 }) => {
    if (!isArmed) {
      return;
    }
    const picked = toCartographic(movement.position);
    if (!picked) {
      return;
    }

    isDragging = true;
    startCartographic = picked;
    currentCartographic = picked;
    startScreen = Cartesian2.clone(movement.position);
    ensurePreviewEntity();
  }, ScreenSpaceEventType.LEFT_DOWN);

  handler.setInputAction((movement: { endPosition: Cartesian2 }) => {
    if (!isDragging) {
      return;
    }
    const picked = toCartographic(movement.endPosition);
    if (picked) {
      currentCartographic = picked;
    }
  }, ScreenSpaceEventType.MOUSE_MOVE);

  handler.setInputAction((movement: { position: Cartesian2 }) => {
    if (!isDragging) {
      return;
    }
    finishDrag(movement.position);
  }, ScreenSpaceEventType.LEFT_UP);

  function begin(): void {
    isArmed = true;
    isDragging = false;
    setCameraInputEnabled(false);
  }

  function cancel(): void {
    isArmed = false;
    isDragging = false;
    setCameraInputEnabled(true);
    removePreviewEntity();
    notify(null);
  }

  function clearRegion(): void {
    if (committedEntity) {
      dataSource.entities.remove(committedEntity);
      committedEntity = null;
    }
    notify(null);
  }

  return {
    begin,
    cancel,
    isDrawing: () => isArmed || isDragging,
    clearRegion,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    destroy: () => {
      handler.destroy();
      listeners.clear();
      if (!viewer.isDestroyed()) {
        setCameraInputEnabled(true);
        viewer.dataSources.remove(dataSource, true);
      }
    },
  };
}

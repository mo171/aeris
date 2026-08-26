// components/sharedUI/functionalComponent/geoStage/layers/aoi-outline-layer.ts — the area-of-interest boundary.
//
// what  : Draws a thin, ground-clamped outline around the investigation's area of interest and fades it in.
// where : Owned by CesiumStage.tsx, set by the Investigation Workspace once the descent target is known.
// how   : It is a boundary, not a fill. Filling the AOI would tint the imagery the operator is there to
//         read; an outline states the extent of the analysis without competing with its subject.
//
//         Clamped to ground rather than drawn at a fixed height, so it follows terrain instead of floating
//         over valleys and sinking into ridges.

import {
  CallbackProperty,
  Cartesian3,
  Color,
  ColorMaterialProperty,
  CustomDataSource,
  Entity,
  type Viewer,
} from "cesium";

import { AERIS_COLOR_HEX } from "@/lib/constants/theme";

import type { StageBoundingBox } from "../geo-stage.types";

const FADE_IN_MS = 700;

export interface AreaOfInterestOutlineLayer {
  set: (bounds: StageBoundingBox | null) => void;
  update: (nowMs: number) => void;
  destroy: () => void;
}

export function createAreaOfInterestOutlineLayer(viewer: Viewer): AreaOfInterestOutlineLayer {
  const dataSource = new CustomDataSource("aeris-aoi-outline");
  void viewer.dataSources.add(dataSource);

  const baseColor = Color.fromCssColorString(AERIS_COLOR_HEX.teal);
  let entity: Entity | null = null;
  let alpha = 0;
  let startedAt = 0;

  function set(bounds: StageBoundingBox | null): void {
    dataSource.entities.removeAll();
    entity = null;
    alpha = 0;

    if (!bounds) {
      return;
    }

    const corners = [
      [bounds.west, bounds.south],
      [bounds.east, bounds.south],
      [bounds.east, bounds.north],
      [bounds.west, bounds.north],
      [bounds.west, bounds.south],
    ];

    startedAt = performance.now();
    entity = new Entity({
      polyline: {
        positions: corners.map(([longitude, latitude]) =>
          Cartesian3.fromDegrees(longitude, latitude),
        ),
        width: 1.5,
        clampToGround: true,
        material: new ColorMaterialProperty(
          new CallbackProperty(() => baseColor.withAlpha(alpha * 0.75), false),
        ),
      },
    });
    dataSource.entities.add(entity);
  }

  function update(nowMs: number): void {
    if (!entity || alpha >= 1) {
      return;
    }
    alpha = Math.min(1, (nowMs - startedAt) / FADE_IN_MS);
  }

  return {
    set,
    update,
    destroy: () => {
      if (!viewer.isDestroyed()) {
        viewer.dataSources.remove(dataSource, true);
      }
    },
  };
}

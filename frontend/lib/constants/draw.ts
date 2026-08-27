// lib/constants/draw.ts — tuning for the on-scene drawing and measurement tools.
//
// what  : Vertex density, stroke weights, fill opacity and the label face used by the draw controller.
// where : Read by components/sharedUI/functionalComponent/geoStage/region-draw.ts and by the draw toolbar.
// how   : Kept out of the controller so the feel of the tools can be tuned without touching the geometry
//         code that computes what the backend will crop against.
//
//         `freehandMinimumSpacingMeters` is the one that matters. A freehand trace records a point per
//         pointer move, which at screen rate produces thousands of near-identical vertices — a polygon
//         that is expensive to send, expensive to crop against, and no more accurate than one sampled at
//         a sensible ground spacing.

export const DRAW_TOOLS = {
  /** Vertices used to approximate a circle on the ellipsoid. */
  circleVertexCount: 64,
  /** Minimum ground distance between recorded freehand vertices. */
  freehandMinimumSpacingMeters: 25,
  /** Two clicks closer together than this are treated as one — what a double-click leaves behind. */
  duplicateVertexMeters: 8,
  outlineWidthPixels: 2,
  fillAlpha: 0.16,
  labelFont: "12px 'JetBrains Mono', monospace",
} as const;

/** Copy for the toolbar, so the tool list and its help text stay in one place. */
export const DRAW_TOOL_COPY = {
  rectangle: { label: "Rectangle", hint: "Drag to define a box" },
  polygon: { label: "Polygon", hint: "Click each corner, double-click or Enter to close" },
  freehand: { label: "Freehand", hint: "Drag to trace a boundary" },
  circle: { label: "Circle", hint: "Drag out from the centre" },
  distance: { label: "Distance", hint: "Click along a path, Enter to finish" },
  area: { label: "Area", hint: "Click a boundary, Enter to finish" },
  bearing: { label: "Bearing", hint: "Click a start and an end point" },
} as const;

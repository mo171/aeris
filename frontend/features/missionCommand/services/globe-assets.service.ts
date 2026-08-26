// features/missionCommand/services/globe-assets.service.ts — loads the static land geometry for the globe.
//
// what  : Fetches the TopoJSON land outline from /public and converts it to a GeoJSON feature collection.
// where : Called by use-land-dots.ts, which turns the result into the globe's point cloud.
// how   : This deliberately uses plain fetch rather than the shared axios client. The land outline is a
//         same-origin static asset shipped with the application, not an AERIS API resource — routing it
//         through the API client would give it the wrong base URL, the wrong auth headers, and would make
//         the Phase 1 mock adapter try to answer for it.
//
//         It is served from /public rather than imported so the payload stays out of the JavaScript bundle
//         and is fetched lazily, only once the globe actually mounts.

import { feature } from "topojson-client";
import type { Topology } from "topojson-specification";
import type { GeoPermissibleObjects } from "d3-geo";

import { LAND_DOT_SAMPLING } from "@/lib/constants/globe";

const LAND_OBJECT_KEY = "land";

export async function fetchLandGeometry(signal?: AbortSignal): Promise<GeoPermissibleObjects> {
  const response = await fetch(LAND_DOT_SAMPLING.geometryUrl, { signal });

  if (!response.ok) {
    throw new Error(`Land geometry request failed with status ${response.status}`);
  }

  const topology = (await response.json()) as Topology;

  if (!topology.objects?.[LAND_OBJECT_KEY]) {
    throw new Error("Land geometry file does not contain a 'land' object.");
  }

  return feature(topology, LAND_OBJECT_KEY) as unknown as GeoPermissibleObjects;
}

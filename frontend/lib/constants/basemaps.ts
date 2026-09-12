// lib/constants/basemaps.ts — the catalogue of available basemap tile sources.
//
// what  : Declarative entries for every basemap the investigation workspace can show beneath evidence
//         layers — satellite imagery, street maps, topographic, dark, and a plain background.
// where : Read by the LayersPanel basemap switcher; the active basemap id is stored in the investigation
//         store as view state (it does not survive reload, which is correct: a shared link should not
//         force the recipient's base layer preference).
// how   : A closed set because every entry needs a tile URL template, an attribution string, and the
//         zoom constraints the tiler actually supports. Adding an entry here is the ONLY change needed
//         to make it available in the switcher — no component modification required.

export interface BasemapDefinition {
  id: string;
  label: string;
  /** Short description shown in the switcher tooltip. */
  description: string;
  /** XYZ tile URL template with {z}, {x}, {y} placeholders. */
  tileUrlTemplate: string;
  attribution: string;
  minZoom: number;
  maxZoom: number;
  /** Whether this is a dark-themed basemap (affects label contrast). */
  isDark: boolean;
}

export const BASEMAPS: readonly BasemapDefinition[] = [
  {
    id: "satellite",
    label: "Satellite",
    description: "High-resolution satellite imagery",
    tileUrlTemplate: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Esri, Maxar, Earthstar Geographics",
    minZoom: 0,
    maxZoom: 19,
    isDark: true,
  },
  {
    id: "streets",
    label: "Streets",
    description: "Standard street map with labels",
    tileUrlTemplate: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "© OpenStreetMap contributors",
    minZoom: 0,
    maxZoom: 19,
    isDark: false,
  },
  {
    id: "topographic",
    label: "Topographic",
    description: "Terrain contours with hillshading",
    tileUrlTemplate: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
    attribution: "Esri, USGS, NOAA",
    minZoom: 0,
    maxZoom: 19,
    isDark: false,
  },
  {
    id: "dark",
    label: "Dark",
    description: "Dark canvas for high-contrast evidence overlay",
    tileUrlTemplate: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    attribution: "Esri, HERE, Garmin",
    minZoom: 0,
    maxZoom: 16,
    isDark: true,
  },
  {
    id: "none",
    label: "None",
    description: "No basemap — evidence layers only",
    tileUrlTemplate: "",
    attribution: "",
    minZoom: 0,
    maxZoom: 22,
    isDark: true,
  },
] as const;

export const DEFAULT_BASEMAP_ID = "satellite";

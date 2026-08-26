// mock/data/geography.ts — real place names and coordinates so the mock globe looks plausible.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : A list of real areas of interest with genuine latitude/longitude, plus sensor platform names.
// where : Used by the imagery, mission and marker generators.
// how   : Markers scattered at uniformly random coordinates fall mostly in the ocean and immediately look
//         fake. Seeding from real land-based AOIs — and jittering around them — produces a globe whose
//         clustering resembles the real thing, which is what makes performance testing meaningful too.

export interface MockArea {
  name: string;
  latitude: number;
  longitude: number;
  country: string;
}

export const MOCK_AREAS: readonly MockArea[] = [
  { name: "Mumbai Coastal Belt", latitude: 19.076, longitude: 72.8777, country: "India" },
  { name: "Sundarbans Delta", latitude: 21.9497, longitude: 89.1833, country: "India" },
  { name: "Chennai Metropolitan", latitude: 13.0827, longitude: 80.2707, country: "India" },
  { name: "Bengaluru Urban Fringe", latitude: 12.9716, longitude: 77.5946, country: "India" },
  { name: "Kutch Salt Flats", latitude: 23.7337, longitude: 69.8597, country: "India" },
  { name: "Brahmaputra Floodplain", latitude: 26.1445, longitude: 91.7362, country: "India" },
  { name: "Western Ghats Corridor", latitude: 15.3173, longitude: 75.7139, country: "India" },
  { name: "Amazon Basin — Rondonia", latitude: -10.83, longitude: -63.34, country: "Brazil" },
  { name: "Cerrado Agricultural Front", latitude: -15.6, longitude: -47.8, country: "Brazil" },
  { name: "Sao Paulo Industrial Ring", latitude: -23.5505, longitude: -46.6333, country: "Brazil" },
  { name: "Nile Delta", latitude: 31.0409, longitude: 31.3785, country: "Egypt" },
  { name: "Lake Chad Basin", latitude: 13.0, longitude: 14.0, country: "Chad" },
  { name: "Okavango Delta", latitude: -19.28, longitude: 22.85, country: "Botswana" },
  { name: "Congo Rainforest Margin", latitude: -0.7, longitude: 23.65, country: "DR Congo" },
  { name: "Sahel Transition Zone", latitude: 15.35, longitude: -0.9, country: "Mali" },
  { name: "Rotterdam Port Complex", latitude: 51.9244, longitude: 4.4777, country: "Netherlands" },
  { name: "Po Valley", latitude: 45.07, longitude: 9.68, country: "Italy" },
  { name: "Andalusian Olive Belt", latitude: 37.5443, longitude: -4.7278, country: "Spain" },
  { name: "Danube Floodplain", latitude: 44.43, longitude: 26.1, country: "Romania" },
  { name: "Norwegian Fjords", latitude: 61.47, longitude: 6.5, country: "Norway" },
  { name: "Ukrainian Grain Belt", latitude: 48.5, longitude: 34.0, country: "Ukraine" },
  { name: "Aral Sea Remnant", latitude: 45.0, longitude: 60.0, country: "Kazakhstan" },
  { name: "Mekong Delta", latitude: 10.03, longitude: 105.78, country: "Vietnam" },
  { name: "Yangtze Industrial Corridor", latitude: 31.23, longitude: 121.47, country: "China" },
  { name: "Gobi Desert Margin", latitude: 42.5, longitude: 105.0, country: "Mongolia" },
  { name: "Java Volcanic Belt", latitude: -7.25, longitude: 110.0, country: "Indonesia" },
  { name: "Borneo Palm Frontier", latitude: 0.96, longitude: 114.55, country: "Indonesia" },
  { name: "Tokyo Bay", latitude: 35.6762, longitude: 139.6503, country: "Japan" },
  { name: "Great Barrier Reef Shelf", latitude: -18.29, longitude: 147.7, country: "Australia" },
  { name: "Murray-Darling Basin", latitude: -34.0, longitude: 142.0, country: "Australia" },
  { name: "Canterbury Plains", latitude: -43.6, longitude: 172.0, country: "New Zealand" },
  { name: "California Central Valley", latitude: 36.75, longitude: -119.77, country: "United States" },
  { name: "Gulf Coast Refineries", latitude: 29.76, longitude: -95.37, country: "United States" },
  { name: "Mississippi Floodplain", latitude: 32.3, longitude: -90.9, country: "United States" },
  { name: "Alberta Oil Sands", latitude: 57.02, longitude: -111.47, country: "Canada" },
  { name: "Hudson Bay Lowlands", latitude: 55.0, longitude: -85.0, country: "Canada" },
  { name: "Atacama Lithium Flats", latitude: -23.5, longitude: -68.2, country: "Chile" },
  { name: "Patagonian Ice Field", latitude: -49.3, longitude: -73.0, country: "Argentina" },
  { name: "Andean Mining Belt", latitude: -12.05, longitude: -75.2, country: "Peru" },
  { name: "Persian Gulf Coast", latitude: 26.2, longitude: 50.6, country: "Bahrain" },
  { name: "Tigris-Euphrates Marshes", latitude: 31.0, longitude: 47.0, country: "Iraq" },
  { name: "Anatolian Plateau", latitude: 39.0, longitude: 35.0, country: "Turkey" },
  { name: "Siberian Taiga Edge", latitude: 60.0, longitude: 90.0, country: "Russia" },
  { name: "Kamchatka Volcanic Zone", latitude: 55.0, longitude: 159.0, country: "Russia" },
  { name: "Iceland Glacial Outwash", latitude: 64.0, longitude: -19.0, country: "Iceland" },
  { name: "Scottish Highlands", latitude: 57.12, longitude: -4.71, country: "United Kingdom" },
  { name: "Rhine Industrial Corridor", latitude: 51.22, longitude: 6.78, country: "Germany" },
  { name: "Casablanca Coastal Strip", latitude: 33.57, longitude: -7.59, country: "Morocco" },
  { name: "Ethiopian Highlands", latitude: 9.15, longitude: 39.0, country: "Ethiopia" },
  { name: "Kenyan Rift Lakes", latitude: -0.5, longitude: 36.1, country: "Kenya" },
];

export const MOCK_SENSOR_PLATFORMS = [
  "Sentinel-2A",
  "Sentinel-2B",
  "Sentinel-1A",
  "Sentinel-1B",
  "Landsat-8 OLI",
  "Landsat-9 OLI-2",
  "PlanetScope",
  "WorldView-3",
  "RISAT-2B",
  "Cartosat-3",
  "EOS-04",
  "TerraSAR-X",
] as const;

/** Projected CRS codes plausible for the sample areas. */
export const MOCK_COORDINATE_SYSTEMS = [
  "EPSG:32643",
  "EPSG:32644",
  "EPSG:32633",
  "EPSG:32610",
  "EPSG:32723",
  "EPSG:4326",
] as const;

// scripts/copy-cesium-assets.mjs — puts Cesium's runtime assets where the browser can fetch them.
//
// what  : Copies Cesium's Workers, Assets, ThirdParty and Widgets folders into public/cesium.
// where : Runs automatically on postinstall; also runnable with `pnpm cesium:assets`.
// how   : Cesium loads roughly 8 MB of web workers, glTF assets and imagery at runtime rather than
//         through the bundler. Turbopack cannot resolve those, so they are served as static files and
//         Cesium is pointed at them via window.CESIUM_BASE_URL (see lib/constants/globe.ts).
//         Bundling them instead would balloon the JavaScript payload with files most sessions never touch.
//
//         This runs on every install because public/cesium is gitignored — a fresh clone must be able to
//         produce it without anyone remembering a manual step.

import { cp, mkdir, rm, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDirectory, "..");

const CESIUM_BUILD_DIRECTORY = path.join(
  projectRoot,
  "node_modules",
  "cesium",
  "Build",
  "Cesium",
);
const PUBLIC_CESIUM_DIRECTORY = path.join(projectRoot, "public", "cesium");

/** Only these four are needed at runtime; the built Cesium.js bundle is not, because we import from source. */
const REQUIRED_ASSET_FOLDERS = ["Assets", "ThirdParty", "Widgets", "Workers"];

async function directoryExists(directoryPath) {
  try {
    const stats = await stat(directoryPath);
    return stats.isDirectory();
  } catch {
    return false;
  }
}

async function copyCesiumAssets() {
  if (!(await directoryExists(CESIUM_BUILD_DIRECTORY))) {
    // Not an error: postinstall can run before or without the cesium package in some CI layouts.
    console.warn("[cesium] Build directory not found, skipping asset copy.");
    return;
  }

  await rm(PUBLIC_CESIUM_DIRECTORY, { recursive: true, force: true });
  await mkdir(PUBLIC_CESIUM_DIRECTORY, { recursive: true });

  for (const folderName of REQUIRED_ASSET_FOLDERS) {
    const source = path.join(CESIUM_BUILD_DIRECTORY, folderName);
    if (!(await directoryExists(source))) {
      console.warn(`[cesium] Expected folder missing, skipping: ${folderName}`);
      continue;
    }
    await cp(source, path.join(PUBLIC_CESIUM_DIRECTORY, folderName), { recursive: true });
  }

  console.log("[cesium] Runtime assets copied to public/cesium");
}

await copyCesiumAssets();

// Copies MapLibre's web worker (and the shared chunk it imports) into
// public/maplibre so the browser can load it; Next's bundler doesn't emit
// it. Runs on postinstall so it always matches the installed version.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "node_modules", "maplibre-gl", "dist");
const dest = join(root, "public", "maplibre");
mkdirSync(dest, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(join(src, file), join(dest, file));
}
console.log("maplibre worker copied to public/maplibre");

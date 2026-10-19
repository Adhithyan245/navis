/**
 * MapLibre GL, configured for this app. Import maps from here, not from
 * "maplibre-gl" directly: v6 loads its web worker from a separate module
 * file, which scripts/copy-maplibre-worker.mjs serves from /maplibre/.
 */
import * as maplibregl from "maplibre-gl";

maplibregl.setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

export { maplibregl };

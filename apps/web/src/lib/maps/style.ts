/**
 * MapTiler vector styles for MapLibre GL: crisp labels at every zoom,
 * POIs, 3D buildings when tilted, and satellite/dark variants.
 */
export type MapStyleKey = "streets" | "satellite" | "dark" | "outdoor";

export const MAP_STYLES: ReadonlyArray<{ key: MapStyleKey; label: string; path: string }> = [
  { key: "streets", label: "Map", path: "streets-v2" },
  { key: "satellite", label: "Satellite", path: "hybrid" },
  { key: "outdoor", label: "Terrain", path: "outdoor-v2" },
  { key: "dark", label: "Dark", path: "streets-v2-dark" },
];

export function styleUrl(key: MapStyleKey, maptilerKey: string): string {
  const path = MAP_STYLES.find((s) => s.key === key)?.path ?? "streets-v2";
  return `https://api.maptiler.com/maps/${path}/style.json?key=${encodeURIComponent(maptilerKey)}`;
}

/** Route line colour per travel mode. */
export const MODE_COLORS: Record<string, string> = {
  drive: "#4f46e5",
  walk: "#0ea5e9",
  bike: "#10b981",
  transit: "#d946ef",
};

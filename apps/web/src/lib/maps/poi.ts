/**
 * Shops, restaurants and landmarks on the base map itself (no API calls):
 * the MapTiler styles carry every OpenStreetMap POI but fade most of them
 * out until zoom 17. This shows them from street level, colour-coded by
 * kind like Google Maps, and turns a tapped POI into a place.
 */
import type { maplibregl } from "@/lib/maps/maplibre";

type Map = maplibregl.Map;

/** Style POI layer id → when it appears and its colour. */
const GROUPS: Record<string, { minzoom: number; color: string }> = {
  tourism: { minzoom: 12.5, color: "#0f9d8a" },
  culture: { minzoom: 12.5, color: "#0f9d8a" },
  park: { minzoom: 12.5, color: "#188038" },
  station: { minzoom: 12, color: "#1a73e8" },
  food: { minzoom: 14.5, color: "#e8710a" },
  shopping: { minzoom: 14.5, color: "#1a73e8" },
  healthcare: { minzoom: 14, color: "#d93025" },
  education: { minzoom: 15, color: "#7b5e3f" },
  transport: { minzoom: 15, color: "#1a73e8" },
  sport: { minzoom: 15.5, color: "#188038" },
  public: { minzoom: 15.5, color: "#5f6368" },
};
const LANDMARK_GROUPS = new Set(["tourism", "culture", "park"]);

function poiLayers(map: Map) {
  return (map.getStyle()?.layers ?? []).filter(
    (l) => l.type === "symbol" && "source-layer" in l && l["source-layer"] === "poi"
  );
}

export function poiLayerIds(map: Map): string[] {
  return poiLayers(map).map((l) => l.id);
}

/** Call on every style.load. */
export function enhancePoiLayers(map: Map, dark: boolean) {
  for (const layer of poiLayers(map)) {
    const group = GROUPS[layer.id.toLowerCase()];
    if (!group) continue;
    map.setLayerZoomRange(layer.id, group.minzoom, 24);
    // Let collision detection (sorted by rank) decide density instead of hard fades.
    map.setPaintProperty(layer.id, "icon-opacity", 1);
    map.setPaintProperty(layer.id, "text-opacity", 1);
    if (!dark) {
      map.setPaintProperty(layer.id, "icon-color", group.color);
      map.setPaintProperty(layer.id, "text-color", group.color);
    }
    if (LANDMARK_GROUPS.has(layer.id.toLowerCase())) {
      map.setLayoutProperty(layer.id, "text-font", ["Roboto Medium", "Noto Sans Bold"]);
      map.setLayoutProperty(layer.id, "text-size", ["interpolate", ["linear"], ["zoom"], 12, 11, 16, 13, 20, 15]);
      map.setLayoutProperty(layer.id, "icon-size", ["interpolate", ["linear"], ["zoom"], 12, 1, 16, 1.2]);
    }
  }
}

export interface TappedPoi {
  name: string;
  lat: number;
  lon: number;
  kind: string | null;
}

/** The labelled POI under a click, if any (small hit box for fingers). */
export function poiAt(map: Map, point: { x: number; y: number }): TappedPoi | null {
  const layers = poiLayerIds(map).filter((id) => map.getLayer(id));
  if (!layers.length) return null;
  const r = 8;
  const hits = map.queryRenderedFeatures(
    [[point.x - r, point.y - r], [point.x + r, point.y + r]],
    { layers }
  );
  for (const f of hits) {
    const p = f.properties ?? {};
    const name = (p["name:en"] as string) || (p.name as string) || (p["name:latin"] as string);
    if (!name || f.geometry.type !== "Point") continue;
    const [lon, lat] = f.geometry.coordinates as [number, number];
    const kind = ((p.subclass as string) || (p.class as string) || "").replace(/_/g, " ") || null;
    return { name, lat, lon, kind };
  }
  return null;
}

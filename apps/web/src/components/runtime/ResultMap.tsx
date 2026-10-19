"use client";
/**
 * ResultMap — real interactive map driven by the current runtime payload.
 *
 * Tech: MapLibre GL (open-source) with MapTiler vector styles (lib/maps/
 * style.ts): sharp labels and POIs at every zoom. The only key needed is
 * NEXT_PUBLIC_MAPTILER_API_KEY; nothing talks to Mapbox.
 *
 * Markers update progressively as useResultMarkers re-derives them from
 * useNavisQuery's partial/final state. On marker arrival we fitBounds so
 * the camera follows the result set without manual zoom.
 *
 * If MAPTILER_API_KEY is missing, the EnvDiagnosticsBanner already alerts
 * the user. This component renders an explicit configuration-needed
 * placeholder pointing at it.
 */
import "maplibre-gl/dist/maplibre-gl.css";

import { maplibregl } from "@/lib/maps/maplibre";
import { Map as MapIcon } from "lucide-react";
import { useEffect, useRef } from "react";

import type { MapMarker } from "@/hooks/useResultMarkers";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { styleUrl } from "@/lib/maps/style";
import { getRuntimeConfig } from "@/lib/runtime/config";
import { cn } from "@/lib/utils";


interface ResultMapProps {
  anchor: MapMarker | null;
  items: MapMarker[];
  hasMarkers: boolean;
  className?: string;
  /** The user's city; where the map starts before any results arrive. */
  home?: { lat: number; lon: number } | null;
}

// With no home city yet, start on a world view rather than any one country.
const WORLD_CENTER: [number, number] = [10, 20];
const WORLD_ZOOM = 1.3;
const HOME_ZOOM = 11;


export function ResultMap({ anchor, items, hasMarkers, className, home }: ResultMapProps) {
  const homeLat = home?.lat;
  const homeLon = home?.lon;
  const { maptilerKey } = getRuntimeConfig();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);

  // Initialize the map once on mount. Skip entirely if maptilerKey is missing.
  useEffect(() => {
    if (!maptilerKey || !containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: styleUrl("streets", maptilerKey),
      center:
        typeof homeLat === "number" && typeof homeLon === "number" ? [homeLon, homeLat] : WORLD_CENTER,
      zoom: typeof homeLat === "number" ? HOME_ZOOM : WORLD_ZOOM,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;

    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
    };
    // Initial center only; later home changes are handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [maptilerKey]);

  // Follow the user's city when it changes and no results are on the map.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || hasMarkers || typeof homeLat !== "number" || typeof homeLon !== "number") return;
    map.flyTo({ center: [homeLon, homeLat], zoom: HOME_ZOOM, duration: 600 });
  }, [homeLat, homeLon, hasMarkers]);

  // Sync markers whenever the runtime-derived set changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Clear previous markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    const points: MapMarker[] = [];
    if (anchor) points.push(anchor);
    points.push(...items);

    if (points.length === 0) return;

    for (const p of points) {
      const el = document.createElement("div");
      el.setAttribute("data-kind", p.kind);
      el.style.width = p.kind === "anchor" ? "16px" : "12px";
      el.style.height = p.kind === "anchor" ? "16px" : "12px";
      el.style.borderRadius = "9999px";
      el.style.boxShadow = "0 0 0 2px rgba(255,255,255,0.9), 0 1px 3px rgba(0,0,0,0.25)";
      el.style.background =
        p.kind === "anchor"
          ? "#6366f1" // indigo-500
          : p.kind === "event"
          ? "#a78bfa" // violet-400
          : "#10b981"; // emerald-500
      el.title = p.label;

      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([p.lon, p.lat])
        .addTo(map);
      markersRef.current.push(marker);
    }

    // Fit bounds to all points with breathing room.
    if (points.length === 1) {
      map.flyTo({ center: [points[0].lon, points[0].lat], zoom: 12, duration: 600 });
    } else {
      const bounds = new maplibregl.LngLatBounds();
      for (const p of points) bounds.extend([p.lon, p.lat]);
      map.fitBounds(bounds, { padding: 48, duration: 600, maxZoom: 14 });
    }
  }, [anchor, items]);

  if (!maptilerKey) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <MapIcon className="size-4 text-zinc-500" />
            Map view
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            The map is disabled because{" "}
            <span className="font-mono text-xs">NEXT_PUBLIC_MAPTILER_API_KEY</span>{" "}
            is not configured. Add it to{" "}
            <span className="font-mono text-xs">apps/web/.env.local</span> and
            restart the dev server.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm flex items-center gap-2">
          <MapIcon className="size-4 text-zinc-500" />
          Map view
          {hasMarkers && (
            <span className="ml-auto text-[10px] font-normal text-zinc-500">
              {items.length} result{items.length === 1 ? "" : "s"}
              {anchor && " near anchor"}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <div
        ref={containerRef}
        className="h-[400px] w-full"
        aria-label="Map showing query results"
      />
    </Card>
  );
}

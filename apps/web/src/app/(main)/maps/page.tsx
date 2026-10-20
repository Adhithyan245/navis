"use client";
/**
 * /maps — the full map: search any place, browse nearby categories, open a
 * place for details, and get directions (drive / walk / bike / transit)
 * drawn on the map with turn-by-turn steps. Shops, restaurants and
 * landmarks on the base map are tappable (lib/maps/poi.ts).
 *
 * MapLibre GL + MapTiler vector styles (lib/maps/style.ts). Deep links:
 *   /maps?lat=..&lon=..&name=..   focus a place
 *   /maps?category=hospitals      open a category around the user's city
 *   /maps?live=1                  start with live transit vehicles on
 *   /maps?track=<trip>&stop_id=..&stop_name=..&at=..&tlat=..&tlon=..
 *                                 follow one bus / train to the rider's stop
 */
import "maplibre-gl/dist/maplibre-gl.css";

import { maplibregl } from "@/lib/maps/maplibre";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Bike,
  Box,
  Bus,
  Car,
  Clock,
  ExternalLink,
  Footprints,
  Globe,
  Layers,
  Loader2,
  MapPin,
  Navigation,
  Phone,
  Radio,
  Search,
  Share2,
  X,
} from "lucide-react";

import { LocationSearch } from "@/components/runtime/LocationSearch";
import { LiveDepartures } from "@/components/transit/LiveDepartures";
import { TripTracker } from "@/components/transit/TripTracker";
import { enhancePoiLayers, poiAt, type TappedPoi } from "@/lib/maps/poi";
import { MAP_STYLES, MODE_COLORS, styleUrl, type MapStyleKey } from "@/lib/maps/style";
import {
  MAP_CATEGORIES,
  type MapCategory,
  type MapPoi,
  type RouteOption,
  type TravelMode,
} from "@/lib/maps/types";
import { googleMapsDirectionsUrl } from "@/lib/runtime/maps";
import { runtimeClient } from "@/lib/runtime/client";
import { getRuntimeConfig } from "@/lib/runtime/config";
import type { Location } from "@/lib/runtime/location";
import { useProfileContext } from "@/lib/profile/context";
import { isTransitPlace, positionAt, toTrack, type LiveTrip, type Track, type TrackTarget } from "@/lib/transit/live";
import { cn } from "@/lib/utils";

type Panel = "results" | "place" | "directions";
interface Pin extends MapPoi {
  label?: string;
}

const MODE_META: Record<TravelMode, { label: string; icon: typeof Car }> = {
  drive: { label: "Drive", icon: Car },
  transit: { label: "Transit", icon: Bus },
  walk: { label: "Walk", icon: Footprints },
  bike: { label: "Bike", icon: Bike },
};
const ROUTE_SOURCE = "navis-route";
const LIVE_SOURCE = "navis-live";
const LIVE_REFRESH_MS = 30_000;
const LIVE_MIN_ZOOM = 12.5;
const TRIP_SOURCE = "navis-trip";
const TRIP_REFRESH_MS = 20_000;

function fmtDuration(min: number): string {
  if (min < 60) return `${Math.max(1, Math.round(min))} min`;
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return m ? `${h} h ${m} min` : `${h} h`;
}

function fmtClock(iso: string | undefined | null, timeZone?: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", ...(timeZone ? { timeZone } : {}) });
  } catch {
    return "";
  }
}

function fmtDistance(m?: number): string {
  if (typeof m !== "number") return "";
  return m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(m < 10_000 ? 1 : 0)} km`;
}

function radiusForZoom(zoom: number): number {
  if (zoom >= 16) return 800;
  if (zoom >= 15) return 1500;
  if (zoom >= 13.5) return 3000;
  if (zoom >= 12) return 6000;
  return 12000;
}

export default function MapsPage() {
  return (
    <Suspense fallback={<div className="py-12 text-sm text-zinc-500">Loading map…</div>}>
      <MapsPageInner />
    </Suspense>
  );
}

function MapsPageInner() {
  const { maptilerKey } = getRuntimeConfig();
  const { ready, profile } = useProfileContext();
  const params = useSearchParams();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const selectedMarkerRef = useRef<maplibregl.Marker | null>(null);
  const routeRef = useRef<RouteOption | null>(null);
  const styleKeyRef = useRef<MapStyleKey>("streets");
  const onPoiRef = useRef<(poi: TappedPoi) => void>(() => {});
  const detailsAbort = useRef<AbortController | null>(null);

  const [styleKey, setStyleKey] = useState<MapStyleKey>("streets");
  const [stylesOpen, setStylesOpen] = useState(false);
  const [tilted, setTilted] = useState(false);
  const [category, setCategory] = useState<MapCategory | null>(
    () => (MAP_CATEGORIES.find((c) => c.key === params.get("category"))?.key ?? null) as MapCategory | null
  );
  const [results, setResults] = useState<Pin[]>([]);
  const [resultsNote, setResultsNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [moved, setMoved] = useState(false);
  // A place deep-linked as ?lat=&lon=&name= opens selected.
  const [selected, setSelected] = useState<Pin | null>(() => {
    const lat = Number(params.get("lat"));
    const lon = Number(params.get("lon"));
    return params.get("lat") !== null && Number.isFinite(lat) && Number.isFinite(lon)
      ? { name: params.get("name") || "Selected place", lat, lon }
      : null;
  });
  const [panel, setPanel] = useState<Panel>(() => (params.get("lat") !== null ? "place" : "results"));
  const [mapReady, setMapReady] = useState(false);
  const [routes, setRoutes] = useState<RouteOption[]>([]);
  const [mode, setMode] = useState<TravelMode>("drive");
  const [routeNote, setRouteNote] = useState<string | null>(null);
  const [routing, setRouting] = useState(false);
  const [origin, setOrigin] = useState<{ lat: number; lon: number; label: string } | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [live, setLive] = useState(() => params.get("live") === "1");
  const [liveNote, setLiveNote] = useState<string | null>(null);
  const [liveInfo, setLiveInfo] = useState<Track | null>(null);
  const tracksRef = useRef<Track[]>([]);
  const liveRef = useRef(live);
  // Following one vehicle (?track=… or "Track" on a departure / vehicle).
  const [track, setTrack] = useState<TrackTarget | null>(() => {
    const tripId = params.get("track");
    return tripId ? { tripId, stopId: params.get("stop_id"), stopName: params.get("stop_name"), at: params.get("at") } : null;
  });
  const [trip, setTrip] = useState<LiveTrip | null>(null);
  const [tripLoading, setTripLoading] = useState(false);
  const [tripError, setTripError] = useState(false);
  const [tick, setTick] = useState(() => Date.now());
  const tripRef = useRef<TripState | null>(null);

  const home = profile?.cityLocation ?? null;

  // ── map lifecycle ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!ready || !maptilerKey || !containerRef.current || mapRef.current) return;
    const focusLat = Number(params.get("lat"));
    const focusLon = Number(params.get("lon"));
    const hasFocus = Number.isFinite(focusLat) && Number.isFinite(focusLon) && params.get("lat") !== null;
    const trackLat = Number(params.get("tlat"));
    const trackLon = Number(params.get("tlon"));
    const hasTrackFocus = params.get("tlat") !== null && Number.isFinite(trackLat) && Number.isFinite(trackLon);
    const center: [number, number] = hasFocus
      ? [focusLon, focusLat]
      : hasTrackFocus
      ? [trackLon, trackLat]
      : home
      ? [home.lon, home.lat]
      : [10, 20];
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: styleUrl("streets", maptilerKey),
      center,
      zoom: hasFocus ? 16 : hasTrackFocus ? 14 : home ? 13 : 1.4,
      attributionControl: { compact: true },
      maxPitch: 75,
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    const geolocate = new maplibregl.GeolocateControl({
      positionOptions: { enableHighAccuracy: true },
      trackUserLocation: true,
    });
    geolocate.on("geolocate", (e) => {
      setOrigin({ lat: e.coords.latitude, lon: e.coords.longitude, label: "Your location" });
    });
    map.addControl(geolocate, "top-right");
    map.addControl(new maplibregl.FullscreenControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    // Only user gestures count (programmatic fitBounds/flyTo have no originalEvent).
    map.on("moveend", (e) => {
      if ((e as { originalEvent?: unknown }).originalEvent) setMoved(true);
    });
    // Re-draw the route after a style switch (setStyle drops custom layers).
    map.on("style.load", () => {
      enhancePoiLayers(map, styleKeyRef.current === "dark");
      drawRoute(map, routeRef.current);
      ensureLiveLayers(map);
      drawTrip(map, tripRef.current, Date.now());
    });
    // Tap a live vehicle, or a shop / restaurant / landmark on the base map.
    map.on("click", (e) => {
      if (liveRef.current && map.getLayer(`${LIVE_SOURCE}-dot`)) {
        const hit = map.queryRenderedFeatures(
          [[e.point.x - 10, e.point.y - 10], [e.point.x + 10, e.point.y + 10]],
          { layers: [`${LIVE_SOURCE}-dot`] }
        )[0];
        const id = hit?.properties?.id as string | undefined;
        const track = id ? tracksRef.current.find((t) => t.id === id) : undefined;
        if (track) {
          setLiveInfo(track);
          return;
        }
      }
      setLiveInfo(null);
      const poi = poiAt(map, e.point);
      if (poi) onPoiRef.current(poi);
    });
    map.on("mousemove", (e) => {
      map.getCanvas().style.cursor = poiAt(map, e.point) ? "pointer" : "";
    });
    map.once("load", () => setMapReady(true));
    mapRef.current = map;
    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
    };
    // Created once; params/home only seed the first view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, maptilerKey]);

  // Style switching
  useEffect(() => {
    const map = mapRef.current;
    styleKeyRef.current = styleKey;
    if (map && maptilerKey) map.setStyle(styleUrl(styleKey, maptilerKey));
  }, [styleKey, maptilerKey]);

  // Selected-place marker
  useEffect(() => {
    const map = mapRef.current;
    selectedMarkerRef.current?.remove();
    selectedMarkerRef.current = null;
    if (!map || !selected) return;
    selectedMarkerRef.current = new maplibregl.Marker({ color: "#e11d48" })
      .setLngLat([selected.lon, selected.lat])
      .addTo(map);
  }, [selected, mapReady]);

  // ── live transit vehicles ───────────────────────────────────────────────
  useEffect(() => {
    liveRef.current = live;
    const map = mapRef.current;
    if (!map || !mapReady) return;
    if (!live) {
      tracksRef.current = [];
      drawLive(map, []);
      return;
    }
    let controller: AbortController | null = null;
    const fetchVehicles = async () => {
      if (map.getZoom() < LIVE_MIN_ZOOM) {
        tracksRef.current = [];
        setLiveNote("Zoom in to see buses and trains moving live.");
        return;
      }
      controller?.abort();
      controller = new AbortController();
      const b = map.getBounds();
      try {
        const res = await runtimeClient.liveVehicles(
          { minLat: b.getSouth(), minLon: b.getWest(), maxLat: b.getNorth(), maxLon: b.getEast() },
          map.getZoom(),
          controller.signal
        );
        tracksRef.current = res.vehicles.map(toTrack);
        setLiveNote(res.message);
      } catch {
        if (!controller.signal.aborted) setLiveNote("Live vehicles aren't loading right now.");
      }
    };
    const render = () => {
      const now = Date.now();
      const features = [];
      for (const t of tracksRef.current) {
        const pos = positionAt(t, now);
        if (pos) features.push({ id: t.id, line: t.line, color: t.color, realtime: t.realtime, pos });
      }
      drawLive(map, features);
    };
    void fetchVehicles();
    const refresh = setInterval(() => void fetchVehicles(), LIVE_REFRESH_MS);
    const animate = setInterval(render, 1000);
    let moveTimer: ReturnType<typeof setTimeout> | undefined;
    const onMove = () => {
      clearTimeout(moveTimer);
      moveTimer = setTimeout(() => void fetchVehicles(), 600);
    };
    map.on("moveend", onMove);
    return () => {
      controller?.abort();
      clearInterval(refresh);
      clearInterval(animate);
      clearTimeout(moveTimer);
      map.off("moveend", onMove);
    };
  }, [live, mapReady]);

  // ── follow one vehicle ──────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    if (!track) {
      tripRef.current = null;
      drawTrip(map, null, Date.now());
      return;
    }
    let controller: AbortController | null = null;
    let framed = false;
    const load = async () => {
      controller?.abort();
      const mine = new AbortController();
      controller = mine;
      setTripLoading(true);
      try {
        const data = await runtimeClient.liveTrip(track, mine.signal);
        tripRef.current = tripState(data);
        setTrip(data);
        setTripError(false);
        drawTrip(map, tripRef.current, Date.now());
        // First load: frame the vehicle and the rider's stop.
        if (!framed) {
          framed = true;
          const here = tripPosition(tripRef.current, Date.now());
          const stop = data.stops.find((s) => s.yours);
          const pts = [here, stop ? ([stop.lon, stop.lat] as [number, number]) : null].filter(
            (p): p is [number, number] => p !== null
          );
          // Keep clear of the search bar and the tracker panel (bottom sheet on phones, left panel on desktop).
          const phone = window.innerWidth < 768;
          const padding = { top: 150, right: 60, bottom: phone ? Math.round(window.innerHeight * 0.5) + 20 : 60, left: phone ? 40 : 420 };
          if (pts.length === 2) {
            map.fitBounds(new maplibregl.LngLatBounds(pts[0], pts[0]).extend(pts[1]), { padding, maxZoom: 16, duration: 900 });
          } else if (pts.length === 1) {
            map.easeTo({ center: pts[0], zoom: Math.max(map.getZoom(), 15), padding, duration: 900 });
          }
        }
      } catch {
        if (!mine.signal.aborted) setTripError(true);
      } finally {
        if (!mine.signal.aborted) setTripLoading(false);
      }
    };
    void load();
    const refresh = setInterval(() => void load(), TRIP_REFRESH_MS);
    const animate = setInterval(() => {
      const now = Date.now();
      drawTrip(map, tripRef.current, now);
      setTick(now);
    }, 1000);
    return () => {
      controller?.abort();
      clearInterval(refresh);
      clearInterval(animate);
    };
  }, [track, mapReady]);

  const startTracking = useCallback((t: TrackTarget) => {
    setTrip(null);
    setTripError(false);
    setLiveInfo(null);
    setPanelOpen(true);
    setTrack(t);
  }, []);

  const stopTracking = useCallback(() => {
    setTrack(null);
    setTrip(null);
    tripRef.current = null;
    if (mapRef.current) drawTrip(mapRef.current, null, Date.now());
    const url = new URL(window.location.href);
    if (url.searchParams.has("track")) {
      ["track", "stop_id", "stop_name", "at", "tlat", "tlon"].forEach((k) => url.searchParams.delete(k));
      window.history.replaceState(null, "", url.toString());
    }
  }, []);

  // ── categories ──────────────────────────────────────────────────────────
  const selectPin = useCallback((pin: Pin, fly = true) => {
    setSelected(pin);
    setPanel("place");
    setPanelOpen(true);
    setRoutes([]);
    routeRef.current = null;
    if (mapRef.current) drawRoute(mapRef.current, null);
    if (fly) mapRef.current?.flyTo({ center: [pin.lon, pin.lat], zoom: Math.max(mapRef.current.getZoom(), 15.5), speed: 1.4 });
  }, []);

  // Fill in address, hours, phone, website and (for landmarks) a description
  // and photo for a place that only has a name and point so far.
  const enrich = useCallback(async (pin: Pin) => {
    detailsAbort.current?.abort();
    const controller = new AbortController();
    detailsAbort.current = controller;
    try {
      const { place } = await runtimeClient.mapsPlace(pin.lat, pin.lon, pin.name, controller.signal);
      setSelected((cur) =>
        cur && cur.lat === pin.lat && cur.lon === pin.lon
          ? { ...cur, ...place, lat: cur.lat, lon: cur.lon, categories: place.categories?.length ? place.categories : cur.categories }
          : cur
      );
    } catch {
      /* keep the basic pin */
    }
  }, []);

  useEffect(() => {
    onPoiRef.current = (poi) => {
      const pin: Pin = { name: poi.name, lat: poi.lat, lon: poi.lon, categories: poi.kind ? [poi.kind] : [] };
      selectPin(pin, false);
      void enrich(pin);
    };
  }, [selectPin, enrich]);

  const loadCategory = useCallback(async (key: MapCategory) => {
    const map = mapRef.current;
    if (!map) return;
    const c = map.getCenter();
    setLoading(true);
    setResultsNote(null);
    setPanel("results");
    setPanelOpen(true);
    try {
      const res = await runtimeClient.mapsNearby(c.lat, c.lng, key, radiusForZoom(map.getZoom()));
      setResults(res.items);
      setResultsNote(res.message);
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = res.items.slice(0, 40).map((p, i) => {
        const el = document.createElement("button");
        el.type = "button";
        el.className = "navis-pin";
        el.textContent = String(i + 1);
        el.setAttribute("aria-label", p.name);
        el.addEventListener("click", (ev) => {
          ev.stopPropagation();
          selectPin(p, false);
        });
        return new maplibregl.Marker({ element: el }).setLngLat([p.lon, p.lat]).addTo(map);
      });
      if (res.items.length > 1) {
        const bounds = new maplibregl.LngLatBounds();
        res.items.slice(0, 40).forEach((p) => bounds.extend([p.lon, p.lat]));
        map.fitBounds(bounds, { padding: { top: 80, bottom: 60, left: window.innerWidth >= 768 ? 400 : 40, right: 60 }, maxZoom: 16, duration: 700 });
      }
      setMoved(false);
    } catch {
      setResults([]);
      setResultsNote("Places aren't loading right now. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [selectPin]);

  // Initial category from the URL once the map exists
  const initialCategoryDone = useRef(false);
  useEffect(() => {
    if (initialCategoryDone.current || !mapRef.current || !category) return;
    initialCategoryDone.current = true;
    const map = mapRef.current;
    const run = () => void loadCategory(category);
    if (map.loaded()) run();
    else map.once("load", run);
  }, [category, loadCategory, mapReady]);

  const pickCategory = (key: MapCategory) => {
    if (category === key) {
      setCategory(null);
      setResults([]);
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      return;
    }
    setCategory(key);
    void loadCategory(key);
  };

  // ── search ──────────────────────────────────────────────────────────────
  const onSearchSelect = (loc: Location) => {
    const pin: Pin = { name: loc.name, label: loc.label, address: loc.label, lat: loc.lat, lon: loc.lon, categories: [loc.type] };
    selectPin(pin);
    // Businesses and landmarks get their details; plain addresses and areas don't need a lookup.
    if (loc.type === "landmark" || loc.type === "place" || loc.type === "unknown") {
      void enrich(pin);
    }
  };

  // ── directions ──────────────────────────────────────────────────────────
  const resolveOrigin = (): Promise<{ lat: number; lon: number; label: string } | null> =>
    new Promise((resolve) => {
      if (origin) return resolve(origin);
      const fallback = () => {
        const h = profile?.homeAreaLocation ?? profile?.cityLocation;
        resolve(h ? { lat: h.lat, lon: h.lon, label: h.name || "Home" } : null);
      };
      if (!("geolocation" in navigator)) return fallback();
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const o = { lat: pos.coords.latitude, lon: pos.coords.longitude, label: "Your location" };
          setOrigin(o);
          resolve(o);
        },
        fallback,
        { timeout: 8000, maximumAge: 120_000 }
      );
    });

  const startDirections = async () => {
    if (!selected) return;
    setPanel("directions");
    setRouting(true);
    setRouteNote(null);
    const from = await resolveOrigin();
    if (!from) {
      setRouting(false);
      setRouteNote("Allow location access, or set your home area in your profile, to get directions.");
      return;
    }
    try {
      const res = await runtimeClient.mapsRoute(from, selected);
      setRoutes(res.routes);
      setRouteNote(res.message);
      const best = res.routes.find((r) => r.mode === mode) ?? res.routes[0] ?? null;
      if (best) showRoute(best);
    } catch {
      setRoutes([]);
      setRouteNote("Directions aren't loading right now. Try again in a moment.");
    } finally {
      setRouting(false);
    }
  };

  const showRoute = (r: RouteOption) => {
    setMode(r.mode);
    routeRef.current = r;
    const map = mapRef.current;
    if (!map) return;
    drawRoute(map, r);
    if (r.geometry.length > 1) {
      const bounds = new maplibregl.LngLatBounds();
      r.geometry.forEach((c) => bounds.extend(c as [number, number]));
      map.fitBounds(bounds, { padding: { top: 80, bottom: 80, left: window.innerWidth >= 768 ? 400 : 40, right: 60 }, duration: 700 });
    }
  };

  const activeRoute = routes.find((r) => r.mode === mode) ?? null;

  if (!maptilerKey) {
    return <p className="py-12 text-sm text-zinc-500">The map needs a MapTiler key (NEXT_PUBLIC_MAPTILER_API_KEY).</p>;
  }

  return (
    <div className="relative -mx-4 -mt-6 h-[calc(100dvh-4rem)] overflow-hidden sm:-mx-6 md:-mt-10 md:mx-0 md:h-[calc(100dvh-9rem)] md:rounded-3xl md:border md:border-zinc-200/80 md:shadow-soft dark:md:border-white/[0.07]">
      {/* maplibre-gl.css sets position:relative on the container, so size it via a wrapper. */}
      <div className="absolute inset-0">
        <div ref={containerRef} className="h-full w-full" aria-label="Map" role="region" />
      </div>

      {/* Search + categories */}
      <div className="absolute inset-x-3 top-3 z-10 flex flex-col gap-2 md:right-auto md:w-[372px]">
        <div className="rounded-2xl bg-white/95 shadow-lg backdrop-blur dark:bg-zinc-900/95">
          <LocationSearch value="" onSelect={onSearchSelect} near={home} placeholder="Search places and addresses" />
        </div>
        <div className="no-scrollbar -mx-1 flex gap-1.5 overflow-x-auto px-1 md:w-[calc(100vw-500px)] md:max-w-[640px]">
          {MAP_CATEGORIES.map((c) => (
            <button
              key={c.key}
              type="button"
              onClick={() => pickCategory(c.key)}
              aria-pressed={category === c.key}
              className={cn(
                "shrink-0 rounded-full px-3 py-1.5 text-[13px] font-medium shadow-md transition-colors",
                category === c.key
                  ? "bg-indigo-600 text-white"
                  : "bg-white/95 text-zinc-700 hover:bg-white dark:bg-zinc-900/95 dark:text-zinc-200"
              )}
            >
              {c.label}
            </button>
          ))}
        </div>
        {category && moved && !loading && (
          <button
            type="button"
            onClick={() => void loadCategory(category)}
            className="mx-auto flex items-center gap-1.5 rounded-full bg-white px-3.5 py-1.5 text-[13px] font-medium text-indigo-700 shadow-lg md:mx-0 md:self-start dark:bg-zinc-900 dark:text-indigo-300"
          >
            <Search className="size-3.5" /> Search this area
          </button>
        )}
      </div>

      {/* Style + 3D */}
      <div className="absolute bottom-24 right-3 z-10 flex flex-col items-end gap-2 md:bottom-10">
        {stylesOpen && (
          <div className="flex flex-col overflow-hidden rounded-xl bg-white shadow-lg dark:bg-zinc-900">
            {MAP_STYLES.map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => {
                  setStyleKey(s.key);
                  setStylesOpen(false);
                }}
                className={cn(
                  "px-4 py-2 text-left text-[13px]",
                  styleKey === s.key ? "bg-indigo-50 font-semibold text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300" : "text-zinc-700 dark:text-zinc-200"
                )}
              >
                {s.label}
              </button>
            ))}
          </div>
        )}
        {live && liveNote && (
          <p className="max-w-[220px] rounded-xl bg-white/95 px-3 py-1.5 text-right text-[12px] text-zinc-600 shadow-lg dark:bg-zinc-900/95 dark:text-zinc-300">
            {liveNote}
          </p>
        )}
        <div className="flex gap-2">
          <button
            type="button"
            aria-label={live ? "Hide live transit" : "Show live transit"}
            aria-pressed={live}
            title="Live transit"
            onClick={() => {
              setLive((v) => !v);
              setLiveInfo(null);
            }}
            className={cn("flex size-10 items-center justify-center rounded-xl shadow-lg", live ? "bg-emerald-600 text-white" : "bg-white text-zinc-700 dark:bg-zinc-900 dark:text-zinc-200")}
          >
            <Radio className="size-5" />
          </button>
          <button
            type="button"
            aria-label={tilted ? "Flat view" : "3D view"}
            aria-pressed={tilted}
            onClick={() => {
              const next = !tilted;
              setTilted(next);
              mapRef.current?.easeTo({ pitch: next ? 60 : 0, bearing: next ? -20 : 0, duration: 800 });
            }}
            className={cn("flex size-10 items-center justify-center rounded-xl shadow-lg", tilted ? "bg-indigo-600 text-white" : "bg-white text-zinc-700 dark:bg-zinc-900 dark:text-zinc-200")}
          >
            <Box className="size-5" />
          </button>
          <button
            type="button"
            aria-label="Map style"
            aria-expanded={stylesOpen}
            onClick={() => setStylesOpen((v) => !v)}
            className="flex size-10 items-center justify-center rounded-xl bg-white text-zinc-700 shadow-lg dark:bg-zinc-900 dark:text-zinc-200"
          >
            <Layers className="size-5" />
          </button>
        </div>
      </div>

      {liveInfo && (
        <div className="absolute inset-x-3 top-[124px] z-20 mx-auto max-w-sm rounded-2xl bg-white/97 p-3 shadow-2xl backdrop-blur md:left-auto md:right-16 md:mx-0 dark:bg-zinc-900/97">
          <div className="flex items-start gap-3">
            <span className="rounded-md px-2 py-0.5 text-sm font-bold text-white" style={{ background: liveInfo.color }}>{liveInfo.line}</span>
            <div className="min-w-0 flex-1 text-[13px]">
              <p className="font-semibold text-zinc-900 dark:text-zinc-100">
                {liveInfo.mode.charAt(0).toUpperCase() + liveInfo.mode.slice(1)} {liveInfo.line}
                {liveInfo.to && <span className="font-normal text-zinc-500"> · next stop {liveInfo.to}</span>}
              </p>
              <p className="text-zinc-500">
                {liveInfo.realtime ? (
                  <span className="font-medium text-emerald-600 dark:text-emerald-400">Live position</span>
                ) : (
                  "Estimated from timetable"
                )}
                {liveInfo.delay_min !== null && liveInfo.delay_min >= 2 && <span className="text-amber-600"> · {liveInfo.delay_min} min late</span>}
                {liveInfo.from && <> · last stop {liveInfo.from}</>}
              </p>
            </div>
            <button type="button" onClick={() => setLiveInfo(null)} aria-label="Close" className="rounded-full p-1 text-zinc-400 hover:bg-zinc-100 dark:hover:bg-white/[0.06]">
              <X className="size-4" />
            </button>
          </div>
          <button
            type="button"
            onClick={() => startTracking({ tripId: liveInfo.id })}
            className="mt-2 w-full rounded-xl bg-indigo-600 py-2 text-sm font-semibold text-white hover:bg-indigo-500"
          >
            Track this {liveInfo.mode}
          </button>
        </div>
      )}

      {/* Side panel (desktop) / bottom sheet (mobile) */}
      {(track || selected || results.length > 0 || resultsNote || loading) && (
        <aside
          className={cn(
            "absolute z-20 flex flex-col overflow-hidden bg-white/97 shadow-2xl backdrop-blur dark:bg-zinc-900/97",
            "inset-x-0 bottom-0 rounded-t-3xl md:inset-x-auto md:bottom-3 md:left-3 md:top-[124px] md:w-[372px] md:rounded-2xl",
            panelOpen ? "max-h-[48dvh] md:max-h-none" : "max-h-14"
          )}
        >
          <button
            type="button"
            onClick={() => setPanelOpen((v) => !v)}
            className="mx-auto mt-2 h-1.5 w-10 shrink-0 rounded-full bg-zinc-300 md:hidden dark:bg-zinc-600"
            aria-label={panelOpen ? "Collapse panel" : "Expand panel"}
          />
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {track ? (
              <TripTracker trip={trip} loading={tripLoading} error={tripError} now={tick} onClose={stopTracking} />
            ) : (
            <>
            {panel === "results" && (
              <ResultsList
                loading={loading}
                items={results}
                note={resultsNote}
                title={MAP_CATEGORIES.find((c) => c.key === category)?.label ?? "Results"}
                onPick={(p) => selectPin(p)}
              />
            )}
            {panel === "place" && selected && (
              <PlaceDetail
                place={selected}
                canGoBack={results.length > 0}
                onBack={() => setPanel("results")}
                onClose={() => {
                  setSelected(null);
                  setPanel("results");
                }}
                onDirections={() => void startDirections()}
                onTrack={startTracking}
              />
            )}
            {panel === "directions" && selected && (
              <DirectionsPanel
                to={selected}
                from={origin?.label ?? "Your location"}
                routes={routes}
                active={activeRoute}
                loading={routing}
                note={routeNote}
                onMode={(r) => showRoute(r)}
                onBack={() => {
                  setPanel("place");
                  routeRef.current = null;
                  if (mapRef.current) drawRoute(mapRef.current, null);
                }}
              />
            )}
            </>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}

// ── map drawing ────────────────────────────────────────────────────────────

function drawRoute(map: maplibregl.Map, route: RouteOption | null) {
  if (!map.isStyleLoaded()) return;
  const data = {
    type: "Feature" as const,
    properties: {},
    geometry: { type: "LineString" as const, coordinates: route?.geometry ?? [] },
  };
  const source = map.getSource(ROUTE_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
  } else {
    map.addSource(ROUTE_SOURCE, { type: "geojson", data });
    map.addLayer({
      id: `${ROUTE_SOURCE}-casing`, type: "line", source: ROUTE_SOURCE,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#ffffff", "line-width": 9, "line-opacity": 0.9 },
    });
    map.addLayer({
      id: `${ROUTE_SOURCE}-line`, type: "line", source: ROUTE_SOURCE,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#4f46e5", "line-width": 5 },
    });
  }
  if (route && map.getLayer(`${ROUTE_SOURCE}-line`)) {
    map.setPaintProperty(`${ROUTE_SOURCE}-line`, "line-color", MODE_COLORS[route.mode] ?? "#4f46e5");
    map.setPaintProperty(`${ROUTE_SOURCE}-line`, "line-dasharray", route.mode === "walk" ? [0.5, 1.6] : [1, 0]);
  }
}

function ensureLiveLayers(map: maplibregl.Map) {
  if (!map.isStyleLoaded() || map.getSource(LIVE_SOURCE)) return;
  map.addSource(LIVE_SOURCE, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({
    id: `${LIVE_SOURCE}-dot`, type: "circle", source: LIVE_SOURCE,
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 4, 16, 8],
      "circle-color": ["get", "color"],
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 2,
      "circle-opacity": ["case", ["get", "realtime"], 1, 0.7],
    },
  });
  map.addLayer({
    id: `${LIVE_SOURCE}-label`, type: "symbol", source: LIVE_SOURCE, minzoom: 14,
    layout: {
      "text-field": ["get", "line"], "text-size": 11, "text-offset": [0, -1.3],
      "text-font": ["Roboto Medium", "Noto Sans Bold"], "text-allow-overlap": false,
    },
    paint: { "text-color": ["get", "color"], "text-halo-color": "#ffffff", "text-halo-width": 1.5 },
  });
}

function drawLive(
  map: maplibregl.Map,
  vehicles: Array<{ id: string; line: string; color: string; realtime: boolean; pos: [number, number] }>
) {
  ensureLiveLayers(map);
  const source = map.getSource(LIVE_SOURCE) as maplibregl.GeoJSONSource | undefined;
  source?.setData({
    type: "FeatureCollection",
    features: vehicles.map((v) => ({
      type: "Feature" as const,
      properties: { id: v.id, line: v.line, color: v.color, realtime: v.realtime },
      geometry: { type: "Point" as const, coordinates: v.pos },
    })),
  });
}

// ── tracked vehicle ────────────────────────────────────────────────────────

interface TripState {
  data: LiveTrip;
  seg: Track | null;
}

function tripState(data: LiveTrip): TripState {
  const v = data.vehicle;
  const seg =
    v && "path" in v && v.path.length >= 2
      ? toTrack({
          id: data.trip_id, line: data.line ?? "", mode: data.mode ?? "transit", color: data.color ?? "#4f46e5",
          headsign: data.headsign ?? null, from: v.from, to: v.to, departure: v.departure, arrival: v.arrival,
          delay_min: null, realtime: !!data.realtime, path: v.path,
        })
      : null;
  return { data, seg };
}

/** Where the tracked vehicle is now: along its moving segment, or waiting at a stop. */
function tripPosition(t: TripState | null, now: number): [number, number] | null {
  const v = t?.data.vehicle;
  if (!t || !v) return null;
  if ("position" in v) return v.position;
  if (!t.seg) return null;
  // Between refreshes the segment can end: hold at its last stop.
  return positionAt(t.seg, now) ?? (now > t.seg.t1 ? t.seg.path[t.seg.path.length - 1] : t.seg.path[0]);
}

function drawTrip(map: maplibregl.Map, t: TripState | null, now: number) {
  if (!map.isStyleLoaded()) return;
  const color = t?.data.color ?? "#4f46e5";
  const here = tripPosition(t, now);
  const features: GeoJSON.Feature[] = [];
  if (t && t.data.path.length >= 2) {
    features.push({ type: "Feature", properties: { kind: "route" }, geometry: { type: "LineString", coordinates: t.data.path } });
  }
  for (const s of t?.data.stops ?? []) {
    if (s.passed) continue;
    features.push({ type: "Feature", properties: { kind: s.yours ? "mine" : "stop", name: s.name }, geometry: { type: "Point", coordinates: [s.lon, s.lat] } });
  }
  if (here) features.push({ type: "Feature", properties: { kind: "vehicle" }, geometry: { type: "Point", coordinates: here } });
  const data: GeoJSON.FeatureCollection = { type: "FeatureCollection", features };
  const source = map.getSource(TRIP_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
  } else {
    map.addSource(TRIP_SOURCE, { type: "geojson", data });
    map.addLayer({
      id: `${TRIP_SOURCE}-route`, type: "line", source: TRIP_SOURCE, filter: ["==", ["get", "kind"], "route"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": color, "line-width": 5, "line-opacity": 0.85 },
    });
    map.addLayer({
      id: `${TRIP_SOURCE}-stops`, type: "circle", source: TRIP_SOURCE,
      filter: ["in", ["get", "kind"], ["literal", ["stop", "mine"]]],
      paint: {
        "circle-radius": ["case", ["==", ["get", "kind"], "mine"], 8, 4],
        "circle-color": "#ffffff",
        "circle-stroke-color": ["case", ["==", ["get", "kind"], "mine"], "#4f46e5", color],
        "circle-stroke-width": ["case", ["==", ["get", "kind"], "mine"], 4, 2.5],
      },
    });
    map.addLayer({
      id: `${TRIP_SOURCE}-stop-label`, type: "symbol", source: TRIP_SOURCE, minzoom: 13,
      filter: ["in", ["get", "kind"], ["literal", ["stop", "mine"]]],
      layout: {
        "text-field": ["get", "name"], "text-size": 11, "text-offset": [0, 1.2], "text-anchor": "top",
        "text-font": ["Roboto Medium", "Noto Sans Bold"],
      },
      paint: { "text-color": "#27272a", "text-halo-color": "#ffffff", "text-halo-width": 1.5 },
    });
    map.addLayer({
      id: `${TRIP_SOURCE}-halo`, type: "circle", source: TRIP_SOURCE, filter: ["==", ["get", "kind"], "vehicle"],
      paint: { "circle-radius": 20, "circle-color": color, "circle-opacity": 0.22 },
    });
    map.addLayer({
      id: `${TRIP_SOURCE}-vehicle`, type: "circle", source: TRIP_SOURCE, filter: ["==", ["get", "kind"], "vehicle"],
      paint: { "circle-radius": 10, "circle-color": color, "circle-stroke-color": "#ffffff", "circle-stroke-width": 3 },
    });
  }
  if (t && map.getLayer(`${TRIP_SOURCE}-route`)) {
    map.setPaintProperty(`${TRIP_SOURCE}-route`, "line-color", color);
    map.setPaintProperty(`${TRIP_SOURCE}-stops`, "circle-stroke-color", ["case", ["==", ["get", "kind"], "mine"], "#4f46e5", color]);
    map.setPaintProperty(`${TRIP_SOURCE}-halo`, "circle-color", color);
    map.setPaintProperty(`${TRIP_SOURCE}-vehicle`, "circle-color", color);
  }
}

// ── panels ─────────────────────────────────────────────────────────────────

function ResultsList({
  loading, items, note, title, onPick,
}: {
  loading: boolean;
  items: Pin[];
  note: string | null;
  title: string;
  onPick: (p: Pin) => void;
}) {
  if (loading) {
    return <p className="flex items-center gap-2 text-sm text-zinc-500"><Loader2 className="size-4 animate-spin" /> Finding places…</p>;
  }
  return (
    <div>
      <h2 className="mb-2 text-base font-semibold text-zinc-900 dark:text-zinc-50">
        {title} <span className="text-sm font-normal text-zinc-400">{items.length || ""}</span>
      </h2>
      {note && <p className="mb-2 text-[13px] text-zinc-500 dark:text-zinc-400">{note}</p>}
      <ol className="divide-y divide-zinc-100 dark:divide-white/[0.06]">
        {items.map((p, i) => (
          <li key={`${p.name}-${p.lat}-${i}`}>
            <button type="button" onClick={() => onPick(p)} className="flex w-full items-start gap-3 py-2.5 text-left">
              <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-semibold text-white">{i + 1}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">{p.name}</span>
                {p.address && <span className="block truncate text-xs text-zinc-500">{p.address}</span>}
                {p.opening_hours && <span className="block truncate text-xs text-emerald-700 dark:text-emerald-400">{p.opening_hours}</span>}
              </span>
              <span className="shrink-0 text-xs text-zinc-400">{fmtDistance(p.distance_m)}</span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}

function PlaceDetail({
  place, canGoBack, onBack, onClose, onDirections, onTrack,
}: {
  place: Pin;
  canGoBack: boolean;
  onBack: () => void;
  onClose: () => void;
  onDirections: () => void;
  onTrack: (t: TrackTarget) => void;
}) {
  const share = async () => {
    const url = `${window.location.origin}/maps?lat=${place.lat}&lon=${place.lon}&name=${encodeURIComponent(place.name)}`;
    try {
      if (navigator.share) await navigator.share({ title: place.name, url });
      else await navigator.clipboard.writeText(url);
    } catch {
      /* dismissed */
    }
  };
  const website = place.website && !/^https?:\/\//.test(place.website) ? `https://${place.website}` : place.website;
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-2">
        {canGoBack ? (
          <button type="button" onClick={onBack} className="flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
            <ArrowLeft className="size-3.5" /> Results
          </button>
        ) : <span />}
        <button type="button" onClick={onClose} aria-label="Close" className="rounded-full p-1 text-zinc-400 hover:bg-zinc-100 dark:hover:bg-white/[0.06]">
          <X className="size-4" />
        </button>
      </div>
      {place.about?.image && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={place.about.image} alt="" className="-mx-4 -mt-2 h-40 w-[calc(100%+2rem)] max-w-none object-cover" />
      )}
      <div>
        <h2 className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">{place.name}</h2>
        {place.address && <p className="mt-0.5 text-[13px] text-zinc-500">{place.address}</p>}
        {place.categories && place.categories.length > 0 && (
          <p className="mt-1 text-xs capitalize text-zinc-400">
            {place.categories.filter((c) => c.includes(".")).slice(-1)[0]?.split(".").pop()?.replace(/_/g, " ") ?? place.categories[0]}
          </p>
        )}
      </div>
      <div className="grid grid-cols-4 gap-2">
        <ActionButton icon={Navigation} label="Directions" primary onClick={onDirections} />
        {place.phone ? <ActionLink icon={Phone} label="Call" href={`tel:${place.phone.replace(/\s/g, "")}`} /> : <ActionButton icon={Phone} label="Call" disabled />}
        {website ? <ActionLink icon={Globe} label="Website" href={website} external /> : <ActionButton icon={Globe} label="Website" disabled />}
        <ActionButton icon={Share2} label="Share" onClick={() => void share()} />
      </div>
      {place.about?.extract && (
        <p className="text-[13px] leading-relaxed text-zinc-600 dark:text-zinc-300">
          {place.about.extract.length > 360 ? `${place.about.extract.slice(0, 357).trimEnd()}…` : place.about.extract}
          {place.about.url && (
            <a href={place.about.url} target="_blank" rel="noreferrer noopener" className="ml-1 text-indigo-600 hover:underline dark:text-indigo-400">
              Wikipedia
            </a>
          )}
        </p>
      )}
      {place.attributes && Object.keys(place.attributes).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(place.attributes).map(([k, v]) => {
            const text = attributeLabel(k, v);
            return text && text !== place.name ? (
              <span key={k} className="rounded-full bg-zinc-100 px-2.5 py-1 text-[11px] text-zinc-700 dark:bg-white/[0.06] dark:text-zinc-300">{text}</span>
            ) : null;
          })}
        </div>
      )}
      {isTransitPlace(place.categories, place.name) && (
        <div className="rounded-xl border border-zinc-200/80 p-3 dark:border-white/[0.07]">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Live departures</p>
          <LiveDepartures lat={place.lat} lon={place.lon} stops={2} compact onTrack={onTrack} />
        </div>
      )}
      <dl className="space-y-2 text-[13px]">
        {place.opening_hours && (
          <div className="flex gap-2"><Clock className="mt-0.5 size-4 shrink-0 text-zinc-400" /><span className="text-zinc-700 dark:text-zinc-300">{place.opening_hours}</span></div>
        )}
        {place.phone && (
          <div className="flex gap-2"><Phone className="mt-0.5 size-4 shrink-0 text-zinc-400" /><a href={`tel:${place.phone.replace(/\s/g, "")}`} className="text-indigo-600 hover:underline dark:text-indigo-400">{place.phone}</a></div>
        )}
        <div className="flex gap-2"><MapPin className="mt-0.5 size-4 shrink-0 text-zinc-400" /><span className="text-zinc-500">{place.lat.toFixed(5)}, {place.lon.toFixed(5)}</span></div>
      </dl>
      <a href={googleMapsDirectionsUrl(place.lat, place.lon)} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
        Open in Google Maps <ExternalLink className="size-3" />
      </a>
    </div>
  );
}

const YES_ATTRS: Record<string, string> = {
  outdoor_seating: "Outdoor seating",
  takeaway: "Takeaway",
  delivery: "Delivery",
  "diet:vegetarian": "Vegetarian options",
  "payment:credit_cards": "Cards accepted",
};

function attributeLabel(key: string, value: string): string | null {
  const v = value.trim();
  if (key in YES_ATTRS) return v === "yes" || v === "only" ? YES_ATTRS[key] : null;
  switch (key) {
    case "cuisine":
      return v.split(";").map((c) => c.replace(/_/g, " ")).slice(0, 3).join(", ").replace(/^./, (c) => c.toUpperCase());
    case "wheelchair":
      return v === "yes" ? "Wheelchair accessible" : v === "limited" ? "Limited wheelchair access" : null;
    case "internet_access":
      return v === "wlan" || v === "yes" ? "Wi-Fi" : null;
    case "brand":
    case "operator":
      return v;
    case "start_date":
      return /^\d{3,4}/.test(v) ? `Built ${v}` : null;
    case "denomination":
      return v.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
    case "fee":
      return v === "no" ? "Free entry" : v === "yes" ? "Entry fee" : null;
    default:
      return null;
  }
}

function DirectionsPanel({
  to, from, routes, active, loading, note, onMode, onBack,
}: {
  to: Pin;
  from: string;
  routes: RouteOption[];
  active: RouteOption | null;
  loading: boolean;
  note: string | null;
  onMode: (r: RouteOption) => void;
  onBack: () => void;
}) {
  const order: TravelMode[] = ["drive", "transit", "walk", "bike"];
  return (
    <div className="space-y-4">
      <button type="button" onClick={onBack} className="flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
        <ArrowLeft className="size-3.5" /> {to.name}
      </button>
      <div className="rounded-xl bg-zinc-50 p-3 text-[13px] dark:bg-white/[0.04]">
        <p className="flex items-center gap-2 text-zinc-600 dark:text-zinc-300"><span className="size-2 rounded-full bg-sky-500" /> {from}</p>
        <p className="mt-1.5 flex items-center gap-2 font-medium text-zinc-900 dark:text-zinc-100"><span className="size-2 rounded-full bg-rose-500" /> {to.name}</p>
      </div>
      {loading ? (
        <p className="flex items-center gap-2 text-sm text-zinc-500"><Loader2 className="size-4 animate-spin" /> Finding the best routes…</p>
      ) : (
        <>
          {note && <p className="text-[13px] text-zinc-500">{note}</p>}
          <div className="grid grid-cols-4 gap-1.5">
            {order.map((m) => {
              const r = routes.find((x) => x.mode === m);
              const Icon = MODE_META[m].icon;
              return (
                <button
                  key={m}
                  type="button"
                  disabled={!r}
                  onClick={() => r && onMode(r)}
                  className={cn(
                    "flex flex-col items-center gap-0.5 rounded-xl border px-1 py-2 text-[11px] transition-colors disabled:opacity-40",
                    active?.mode === m
                      ? "border-indigo-300 bg-indigo-50 text-indigo-800 dark:border-indigo-400/40 dark:bg-indigo-500/15 dark:text-indigo-200"
                      : "border-zinc-200 text-zinc-600 dark:border-white/10 dark:text-zinc-300"
                  )}
                >
                  <Icon className="size-4" />
                  <span className="font-semibold">{r ? fmtDuration(r.duration_min) : "—"}</span>
                  <span className="text-zinc-400">{MODE_META[m].label}</span>
                </button>
              );
            })}
          </div>
          {active && (
            <div>
              <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                {fmtDuration(active.duration_min)}{" "}
                {active.departure && active.arrival ? (
                  <span className="font-normal text-zinc-500">
                    · {fmtClock(active.departure, active.timezone)} – {fmtClock(active.arrival, active.timezone)}
                  </span>
                ) : (
                  active.distance_km > 0 && <span className="font-normal text-zinc-500">· {active.distance_km.toFixed(1)} km</span>
                )}
              </p>
              {active.lines && active.lines.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {active.lines.map((l, i) => (
                    <span key={`${l.name}-${i}`} className="flex items-center gap-1">
                      {i > 0 && <span className="text-zinc-300">›</span>}
                      <span
                        className="rounded-md px-1.5 py-0.5 text-[11px] font-semibold"
                        style={{ background: l.color ?? "#e4e4e7", color: l.text_color ?? (l.color ? "#fff" : "#18181b") }}
                        title={[l.agency, l.mode].filter(Boolean).join(" · ")}
                      >
                        {l.name}
                      </span>
                    </span>
                  ))}
                  {active.lines.some((l) => l.realtime) && (
                    <span className="ml-1 flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                      <span className="size-1.5 animate-pulse rounded-full bg-emerald-500" /> Live
                    </span>
                  )}
                </div>
              )}
              {active.alerts && active.alerts.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {active.alerts.map((a) => (
                    <li key={a} className="rounded-lg bg-amber-50 px-2.5 py-1.5 text-[12px] text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
                      {a}
                    </li>
                  ))}
                </ul>
              )}
              <ol className="mt-2 space-y-2 border-l-2 border-zinc-100 pl-3 dark:border-white/10">
                {active.steps.map((s, i) => (
                  <li key={i} className="text-[13px] text-zinc-700 dark:text-zinc-300">
                    {s.departure && (
                      <span className="mr-1.5 font-semibold text-zinc-900 dark:text-zinc-100">{fmtClock(s.departure, active.timezone)}</span>
                    )}
                    {s.instruction}
                    {typeof s.distance_m === "number" && s.distance_m > 0 && <span className="ml-1 text-xs text-zinc-400">{fmtDistance(s.distance_m)}</span>}
                  </li>
                ))}
              </ol>
              <a href={googleMapsDirectionsUrl(to.lat, to.lon)} target="_blank" rel="noreferrer noopener" className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                Navigate with voice guidance in Google Maps <ExternalLink className="size-3" />
              </a>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ActionButton({ icon: Icon, label, onClick, primary, disabled }: { icon: typeof Phone; label: string; onClick?: () => void; primary?: boolean; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex flex-col items-center gap-1 rounded-xl px-1 py-2 text-[11px] font-medium transition-colors disabled:opacity-35",
        primary ? "bg-indigo-600 text-white hover:bg-indigo-700" : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-white/[0.06] dark:text-zinc-200"
      )}
    >
      <Icon className="size-4" /> {label}
    </button>
  );
}

function ActionLink({ icon: Icon, label, href, external }: { icon: typeof Phone; label: string; href: string; external?: boolean }) {
  return (
    <a
      href={href}
      {...(external ? { target: "_blank", rel: "noreferrer noopener" } : {})}
      className="flex flex-col items-center gap-1 rounded-xl bg-zinc-100 px-1 py-2 text-[11px] font-medium text-zinc-700 hover:bg-zinc-200 dark:bg-white/[0.06] dark:text-zinc-200"
    >
      <Icon className="size-4" /> {label}
    </a>
  );
}

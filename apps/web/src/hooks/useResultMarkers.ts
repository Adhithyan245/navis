"use client";
/**
 * useResultMarkers — derive map markers from the current runtime payload.
 *
 * Input:  partials[] + final from useNavisQuery
 * Output: anchor (the geocoded query point) + items[] (one per ranked place
 *         that has a usable coordinate)
 *
 * Markers update progressively: when a partial arrives with ranked items,
 * we surface those immediately; the final payload replaces them once it
 * resolves. Composed (multi-workflow) finals contribute markers from every
 * section.
 */
import { useMemo } from "react";

import type {
  FinalResultPayload,
  PartialResultPayload,
  PlaceItem,
} from "@/lib/runtime/events";
import { isComposedFinal } from "@/lib/runtime/events";

export interface MapMarker {
  id: string;
  lat: number;
  lon: number;
  label: string;
  kind: "anchor" | "place" | "event";
}

export interface UseResultMarkersResult {
  anchor: MapMarker | null;
  items: MapMarker[];
  /** True when we have at least one renderable marker. */
  hasMarkers: boolean;
}

export interface UseResultMarkersInput {
  partials: PartialResultPayload[];
  final: FinalResultPayload | null;
}

export function useResultMarkers({
  partials,
  final,
}: UseResultMarkersInput): UseResultMarkersResult {
  return useMemo(() => {
    const anchor = extractAnchor(final);
    const items: MapMarker[] = [];

    if (final) {
      // Composed finals carry sections; single-workflow finals carry results.
      if (isComposedFinal(final)) {
        for (const section of final.sections) {
          const sectionItems = extractItemsFromSectionData(section.data);
          for (const it of sectionItems) {
            const m = itemToMarker(it, items.length);
            if (m) items.push(m);
          }
        }
      } else if (Array.isArray(final.results)) {
        for (const it of final.results) {
          const m = itemToMarker(it, items.length);
          if (m) items.push(m);
        }
      }
    } else if (partials.length > 0) {
      // Pre-final preview: use whatever the latest partial gives us.
      const latest = partials[partials.length - 1];
      if (Array.isArray(latest.results)) {
        for (const it of latest.results) {
          const m = itemToMarker(it, items.length);
          if (m) items.push(m);
        }
      }
    }

    return {
      anchor,
      items,
      hasMarkers: anchor !== null || items.length > 0,
    };
  }, [partials, final]);
}

// ── helpers ─────────────────────────────────────────────────────────────────

function extractAnchor(final: FinalResultPayload | null): MapMarker | null {
  if (!final) return null;
  // Composed payloads don't carry a top-level location; fall back to the
  // first section that has one.
  if (isComposedFinal(final)) {
    for (const section of final.sections) {
      const loc = (section.data as { location?: unknown })?.location;
      const marker = locationToAnchor(loc);
      if (marker) return marker;
    }
    return null;
  }
  return locationToAnchor(final.location);
}

function locationToAnchor(loc: unknown): MapMarker | null {
  if (!loc || typeof loc !== "object") return null;
  const o = loc as Record<string, unknown>;
  const lat = numericOrNull(o.lat);
  const lon = numericOrNull(o.lon ?? o.lng);
  if (lat === null || lon === null) return null;
  const name = typeof o.name === "string" ? o.name : "Anchor";
  return { id: "anchor", lat, lon, label: name, kind: "anchor" };
}

function extractItemsFromSectionData(data: unknown): PlaceItem[] {
  if (!data || typeof data !== "object") return [];
  const o = data as { results?: unknown };
  return Array.isArray(o.results) ? (o.results as PlaceItem[]) : [];
}

function itemToMarker(item: unknown, index: number): MapMarker | null {
  if (!item || typeof item !== "object") return null;
  const o = item as Record<string, unknown>;

  // Coordinates can live in any of three places depending on provider:
  //   * `location.{lat, lng|lon}`             — Navis canonical / test fixtures
  //   * `properties.{lat, lon}`               — Geoapify GeoJSON Feature
  //   * `_embedded.venues[0].location.{latitude, longitude}` — Ticketmaster
  //     (note: TM returns these as STRINGS; numericOrNull parses them)
  let lat: number | null = null;
  let lon: number | null = null;

  const loc = o.location as Record<string, unknown> | undefined;
  if (loc && typeof loc === "object") {
    lat = numericOrNull(loc.lat);
    lon = numericOrNull(loc.lng ?? loc.lon);
  }
  if ((lat === null || lon === null) && o.properties && typeof o.properties === "object") {
    const p = o.properties as Record<string, unknown>;
    if (lat === null) lat = numericOrNull(p.lat);
    if (lon === null) lon = numericOrNull(p.lon);
  }
  if (lat === null || lon === null) {
    const venues = (o._embedded as { venues?: unknown[] } | undefined)?.venues;
    if (Array.isArray(venues) && venues[0] && typeof venues[0] === "object") {
      const vloc = (venues[0] as { location?: Record<string, unknown> }).location;
      if (vloc) {
        if (lat === null) lat = numericOrNull(vloc.latitude ?? vloc.lat);
        if (lon === null) lon = numericOrNull(vloc.longitude ?? vloc.lon ?? vloc.lng);
      }
    }
  }
  if (lat === null || lon === null) return null;

  // Pick a label from any of the known title fields, in order of specificity.
  const props = o.properties as { name?: unknown; formatted?: unknown } | undefined;
  const name =
    (typeof o.title === "string" && o.title) ||
    (typeof o.name === "string" && o.name) ||
    (typeof props?.name === "string" && props.name) ||
    (typeof props?.formatted === "string" && props.formatted) ||
    `Item ${index + 1}`;

  // Distinguish event vs place by the same signals isEventItem uses.
  const isEvent =
    typeof o.title === "string" ||
    Array.isArray((o as { classifications?: unknown }).classifications) ||
    Array.isArray((o._embedded as { venues?: unknown[] } | undefined)?.venues);
  const kind: MapMarker["kind"] = isEvent ? "event" : "place";

  return {
    id: typeof o.id === "string" ? o.id : `${kind}-${index}`,
    lat,
    lon,
    label: name,
    kind,
  };
}

function numericOrNull(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim()) {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

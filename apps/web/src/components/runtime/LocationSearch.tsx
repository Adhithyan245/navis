"use client";
/**
 * LocationSearch — debounced, worldwide location autocomplete.
 *
 * Calls runtimeClient.geocodeSearch (Geoapify primary, Nominatim fallback)
 * and renders candidate Locations of any granularity: country, city,
 * district, suburb/neighborhood, street, postcode, landmark, exact address,
 * or a raw "lat,lon" coordinate. Emits the selected canonical Location.
 *
 * Controlled by `value` (the display string). Local typing drives the
 * debounced search; selecting a candidate calls `onSelect` and collapses the
 * dropdown.
 *
 * Pass `near` (the user's city) to rank nearby matches first and let the
 * backend expand local abbreviations ("NEU", "JP", "Kendall Sq").
 */
import { useEffect, useRef, useState } from "react";
import { Loader2, MapPin } from "lucide-react";

import { runtimeClient } from "@/lib/runtime/client";
import type { Location } from "@/lib/runtime/location";
import { cn } from "@/lib/utils";

const DEBOUNCE_MS = 300;
const MIN_CHARS = 2;

const TYPE_LABELS: Record<string, string> = {
  country: "Country",
  region: "Region",
  county: "County",
  city: "City",
  district: "District",
  suburb: "Neighborhood",
  neighborhood: "Neighborhood",
  street: "Street",
  postcode: "Postcode",
  landmark: "Landmark",
  address: "Address",
  coordinate: "Coordinate",
  unknown: "Place",
};

export function LocationSearch({
  value,
  onSelect,
  placeholder,
  autoFocus,
  className,
  near,
}: {
  value: string;
  onSelect: (location: Location) => void;
  placeholder?: string;
  autoFocus?: boolean;
  className?: string;
  near?: Location | null;
}) {
  // Primitive deps so a new-but-equal Location object doesn't re-search.
  const nearLat = near?.lat;
  const nearLon = near?.lon;
  const nearCity = near?.city || near?.name || null;
  const [query, setQuery] = useState(value);
  const [results, setResults] = useState<Location[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  // `committed` is the text we already resolved (external value or a picked
  // candidate). The debounce never re-searches it — that's what keeps a
  // selection from immediately firing another lookup.
  const [committed, setCommitted] = useState(value);
  // Derive local state from the external value when it changes (React's
  // set-during-render pattern — no effect, no refs).
  const [seed, setSeed] = useState(value);
  if (value !== seed) {
    setSeed(value);
    setQuery(value);
    setCommitted(value);
  }

  // Debounced search. All state writes live inside the timeout callback (not
  // the synchronous effect body) so they don't trigger cascading renders.
  useEffect(() => {
    const handle = setTimeout(() => {
      const text = query.trim();
      if (text.length < MIN_CHARS || text === committed.trim()) {
        setResults([]);
        setLoading(false);
        return;
      }
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setLoading(true);
      runtimeClient
        .geocodeSearch(text, {
          limit: 6,
          autocomplete: true,
          signal: controller.signal,
          near:
            typeof nearLat === "number" && typeof nearLon === "number"
              ? { lat: nearLat, lon: nearLon, city: nearCity }
              : null,
        })
        .then((locs) => {
          if (controller.signal.aborted) return;
          setResults(locs);
          setOpen(true);
        })
        .catch(() => {
          if (controller.signal.aborted) return;
          setResults([]);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, DEBOUNCE_MS);

    return () => clearTimeout(handle);
  }, [query, committed, nearLat, nearLon, nearCity]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const select = (loc: Location) => {
    setCommitted(loc.label);
    setQuery(loc.label);
    setResults([]);
    setOpen(false);
    onSelect(loc);
  };

  return (
    <div className={cn("relative", className)}>
      <div className="relative">
        <input
          autoFocus={autoFocus}
          type="text"
          value={query}
          placeholder={placeholder}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => {
            if (results.length > 0) setOpen(true);
          }}
          onBlur={() => {
            // Delay so an option's onMouseDown/click can fire first.
            window.setTimeout(() => setOpen(false), 150);
          }}
          className="w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 pr-9 text-sm outline-none placeholder:text-zinc-400 focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        />
        {loading && (
          <Loader2 className="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-zinc-400" />
        )}
      </div>

      {open && results.length > 0 && (
        <ul className="absolute z-50 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-zinc-200 bg-white py-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          {results.map((loc) => (
            <li key={loc.id}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => select(loc)}
                className="flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800"
              >
                <MapPin className="mt-0.5 size-3.5 shrink-0 text-zinc-400" />
                <span className="min-w-0">
                  <span className="block truncate font-medium text-zinc-900 dark:text-zinc-100">
                    {loc.name}
                  </span>
                  <span className="block truncate text-xs text-zinc-500 dark:text-zinc-400">
                    {TYPE_LABELS[loc.type] ?? "Place"} · {loc.label}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

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
 * backend expand local abbreviations ("NEU", "JP", "Kendall Sq"). Without
 * it, the visitor's approximate city (lib/runtime/approx-location) is used.
 *
 * The suggestion list is drawn on top of the page (a portal, fixed under
 * the input), so a dialog or card with overflow hidden can't clip it; it
 * grows to the space between the input and the bottom of the screen (above
 * the phone tab bar) and scrolls inside.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Loader2, MapPin } from "lucide-react";

import { approxLocation, type ApproxLocation } from "@/lib/runtime/approx-location";
import { runtimeClient } from "@/lib/runtime/client";
import type { Location } from "@/lib/runtime/location";
import { cn } from "@/lib/utils";

const DEBOUNCE_MS = 300;
const MIN_CHARS = 2;
const RESULTS = 10;
const MIN_LIST_PX = 220;
// Room kept free under the list: the floating tab bar on phones, a margin elsewhere.
const PHONE_BOTTOM_PX = 104;
const DESKTOP_BOTTOM_PX = 16;

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
  // No city given: rank near the visitor's approximate city instead.
  const [approx, setApprox] = useState<ApproxLocation | null>(null);
  useEffect(() => {
    if (near) return;
    let live = true;
    void approxLocation().then((loc) => {
      if (live) setApprox(loc);
    });
    return () => {
      live = false;
    };
  }, [near]);
  // Primitive deps so a new-but-equal Location object doesn't re-search.
  const nearLat = near?.lat ?? approx?.lat;
  const nearLon = near?.lon ?? approx?.lon;
  const nearCity = near ? near.city || near.name || null : approx?.city ?? null;
  const [query, setQuery] = useState(value);
  const [results, setResults] = useState<Location[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number; width: number; maxHeight: number } | null>(null);
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
          limit: RESULTS,
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

  // Size the list to the room below the input; with too little room (input
  // near the bottom), bring the input up first.
  const fit = useCallback((scroll: boolean) => {
    const box = boxRef.current;
    if (!box) return;
    // A dialog covers the tab bar, so only a margin is needed there.
    const inDialog = !!box.closest('[aria-modal="true"]');
    const bottomGap = window.innerWidth < 768 && !inDialog ? PHONE_BOTTOM_PX : DESKTOP_BOTTOM_PX;
    let rect = box.getBoundingClientRect();
    if (scroll && window.innerHeight - rect.bottom - bottomGap - 8 < MIN_LIST_PX) {
      box.scrollIntoView({ block: "start", behavior: "auto" });
      if (!inDialog) window.scrollBy(0, -80);       // clear the sticky header
      rect = box.getBoundingClientRect();
    }
    const room = window.innerHeight - rect.bottom - bottomGap - 8;
    setPos({ top: rect.bottom + 4, left: rect.left, width: rect.width, maxHeight: Math.max(MIN_LIST_PX, Math.floor(room)) });
  }, []);

  const showing = open && results.length > 0;
  useEffect(() => {
    if (!showing) return;
    fit(true);
    // Follow the input when the page, a dialog or the keyboard moves it.
    const follow = () => fit(false);
    window.addEventListener("resize", follow);
    window.addEventListener("scroll", follow, true);
    window.visualViewport?.addEventListener("resize", follow);
    return () => {
      window.removeEventListener("resize", follow);
      window.removeEventListener("scroll", follow, true);
      window.visualViewport?.removeEventListener("resize", follow);
    };
  }, [showing, fit]);

  const select = (loc: Location) => {
    setCommitted(loc.label);
    setQuery(loc.label);
    setResults([]);
    setOpen(false);
    onSelect(loc);
  };

  return (
    <div className={cn("relative", className)}>
      <div className="relative" ref={boxRef}>
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

      {showing && pos && createPortal(
        <ul
          role="listbox"
          style={{ top: pos.top, left: pos.left, width: pos.width, maxHeight: pos.maxHeight }}
          className="fixed z-[200] overflow-y-auto overscroll-contain rounded-lg border border-zinc-200 bg-white py-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
        >
          {results.map((loc) => (
            <li key={loc.id} role="option" aria-selected={false}>
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
        </ul>,
        document.body
      )}
    </div>
  );
}

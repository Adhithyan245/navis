"use client";
/**
 * /transit — live departures from the stops around you (or your home area)
 * and a shortcut to watch vehicles move on the map.
 */
import { useState } from "react";
import Link from "next/link";
import { LocateFixed, Map as MapIcon } from "lucide-react";

import { LiveDepartures } from "@/components/transit/LiveDepartures";
import { Button } from "@/components/ui/button";
import { useProfileContext } from "@/lib/profile/context";

export default function TransitPage() {
  const { ready, profile } = useProfileContext();
  const [here, setHere] = useState<{ lat: number; lon: number } | null>(null);
  const [locating, setLocating] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const home = profile?.homeAreaLocation ?? profile?.cityLocation ?? null;
  const point = here ?? (home ? { lat: home.lat, lon: home.lon } : null);

  const locate = () => {
    if (!("geolocation" in navigator)) {
      setNote("Location isn't available on this device.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setHere({ lat: pos.coords.latitude, lon: pos.coords.longitude });
        setLocating(false);
        setNote(null);
      },
      () => {
        setLocating(false);
        setNote("We couldn't get your location. Showing stops near your home area instead.");
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 }
    );
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Live transit</h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            {here ? "Departures from the stops around you." : home ? `Departures near ${home.name || "your area"}.` : "Departures from stops near you."}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={locate} disabled={locating}>
            <LocateFixed /> {locating ? "Locating…" : "Near me"}
          </Button>
          <Button size="sm" nativeButton={false} render={<Link href={point ? `/maps?live=1&lat=${point.lat}&lon=${point.lon}&name=Live%20transit` : "/maps?live=1"} />}>
            <MapIcon /> Live map
          </Button>
        </div>
      </header>
      {note && <p className="text-[13px] text-zinc-500">{note}</p>}
      <div className="rounded-2xl border border-zinc-200/80 bg-white/90 p-5 dark:border-white/[0.07] dark:bg-zinc-900/70">
        {!ready ? (
          <p className="text-sm text-zinc-500">Loading…</p>
        ) : point ? (
          <LiveDepartures key={`${point.lat},${point.lon}`} lat={point.lat} lon={point.lon} stops={4} />
        ) : (
          <p className="text-sm text-zinc-500">Tap &ldquo;Near me&rdquo; or set your city in your profile to see live departures.</p>
        )}
      </div>
    </div>
  );
}

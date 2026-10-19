"use client";
/**
 * /care — Health & emergency for wherever the user is: the emergency number
 * front and centre, every national and local helpline (Boston gets BOS:311
 * and Boston Police non-emergency; Chennai gets 1913 and TANGEDCO; …),
 * nearby hospitals/clinics/dentists/pharmacies with call, book and
 * directions, and the country's real booking & telehealth services.
 *
 * Emergency and helpline numbers come only from Navis's curated directory.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Baby,
  Brain,
  Building2,
  Bus,
  CalendarCheck,
  ExternalLink,
  Flame,
  Globe,
  HeartPulse,
  Info,
  Loader2,
  LocateFixed,
  MapPin,
  MessageSquare,
  Navigation,
  Phone,
  Pill,
  Plug,
  Shield,
  Sparkles,
  Stethoscope,
} from "lucide-react";

import { LocationSearch } from "@/components/runtime/LocationSearch";
import { Button } from "@/components/ui/button";
import type { CareFacility, CareResponse, HelpLine } from "@/lib/maps/types";
import { runtimeClient } from "@/lib/runtime/client";
import type { Location } from "@/lib/runtime/location";
import { googleMapsDirectionsUrl } from "@/lib/runtime/maps";
import { useProfileContext } from "@/lib/profile/context";
import { cn } from "@/lib/utils";

const CATEGORY_META: Record<string, { label: string; icon: typeof Phone; order: number }> = {
  emergency: { label: "Emergency", icon: AlertTriangle, order: 0 },
  police: { label: "Police", icon: Shield, order: 1 },
  medical: { label: "Medical & health advice", icon: HeartPulse, order: 2 },
  fire: { label: "Fire", icon: Flame, order: 3 },
  mental_health: { label: "Mental health & crisis", icon: Brain, order: 4 },
  women_children: { label: "Women, children & safety", icon: Baby, order: 5 },
  poison: { label: "Poison control", icon: AlertTriangle, order: 6 },
  city: { label: "City services", icon: Building2, order: 7 },
  utilities: { label: "Power & water", icon: Plug, order: 8 },
  transit: { label: "Transit", icon: Bus, order: 9 },
  tourist: { label: "Tourist help", icon: Globe, order: 10 },
  other: { label: "Other helplines", icon: Phone, order: 11 },
};

const FACILITY_ICONS: Record<string, typeof Phone> = {
  hospitals: HeartPulse,
  clinics: Stethoscope,
  dentists: Stethoscope,
  pharmacies: Pill,
};

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; data: CareResponse }
  | { status: "error" };

function km(m?: number): string {
  if (typeof m !== "number") return "";
  return m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(m < 10_000 ? 1 : 0)} km`;
}

export default function CarePage() {
  const { ready, profile } = useProfileContext();
  const [place, setPlace] = useState<Location | null>(null);
  const [seeded, setSeeded] = useState(false);
  const [state, setState] = useState<State>({ status: "idle" });
  const [tab, setTab] = useState("hospitals");
  const [locating, setLocating] = useState(false);

  if (!seeded && ready) {
    setSeeded(true);
    if (profile?.cityLocation) setPlace(profile.cityLocation);
  }

  useEffect(() => {
    if (!place) return;
    const controller = new AbortController();
    const handle = setTimeout(() => setState({ status: "loading" }), 0);
    runtimeClient
      .care(
        { lat: place.lat, lon: place.lon, city: place.city || place.name, countryCode: place.country_code,
          country: place.country, region: place.region },
        controller.signal
      )
      .then((data) => {
        clearTimeout(handle);
        setState({ status: "done", data });
      })
      .catch(() => {
        clearTimeout(handle);
        if (!controller.signal.aborted) setState({ status: "error" });
      });
    return () => {
      clearTimeout(handle);
      controller.abort();
    };
  }, [place]);

  const useMyLocation = () => {
    if (!("geolocation" in navigator)) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const loc = await runtimeClient.geocodeReverse(pos.coords.latitude, pos.coords.longitude).catch(() => null);
        setLocating(false);
        if (loc) setPlace(loc);
      },
      () => setLocating(false),
      { timeout: 10_000, maximumAge: 300_000 }
    );
  };

  const city = place ? place.city || place.name : null;
  const data = state.status === "done" ? state.data.data : null;

  return (
    <div className="mx-auto flex w-full min-w-0 max-w-5xl flex-col gap-6">
      <header className="flex flex-col gap-2">
        <p className="inline-flex w-fit items-center gap-2 rounded-full border border-rose-200/70 bg-rose-50/70 px-3 py-1 text-xs font-medium text-rose-700 dark:border-rose-400/20 dark:bg-rose-500/10 dark:text-rose-300">
          <HeartPulse className="size-3.5" aria-hidden /> Health & emergency
        </p>
        <h1 className="text-3xl font-semibold tracking-[-0.02em] text-zinc-900 sm:text-4xl dark:text-zinc-50">
          Help{city ? <> in <span className="text-gradient">{city}</span></> : null}
        </h1>
        <p className="text-[15px] text-zinc-500 dark:text-zinc-400">
          Emergency and helpline numbers for where you are, nearby care, and where to book a doctor.
        </p>
      </header>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <LocationSearch value={place?.label ?? ""} onSelect={setPlace} near={profile?.cityLocation} placeholder="Search any city, town or island" />
        </div>
        <Button variant="outline" size="sm" onClick={useMyLocation} disabled={locating}>
          {locating ? <Loader2 className="animate-spin" /> : <LocateFixed />} Use my location
        </Button>
      </div>

      {!place && ready && (
        <p className="rounded-2xl border border-dashed border-zinc-300/80 px-6 py-12 text-center text-sm text-zinc-500 dark:border-white/10">
          Pick a place to see its emergency numbers and nearby care.
        </p>
      )}

      {state.status === "loading" && (
        <div role="status" aria-label="Loading" className="h-40 rounded-3xl bg-gradient-to-r from-zinc-100 via-zinc-200/70 to-zinc-100 bg-[length:200%_100%] animate-shimmer dark:from-zinc-900 dark:via-zinc-800 dark:to-zinc-900" />
      )}

      {state.status === "error" && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-900 dark:border-rose-400/20 dark:bg-rose-500/10 dark:text-rose-100">
          <p className="font-semibold">We couldn&apos;t load local details right now.</p>
          <p className="mt-1">In a life-threatening emergency, call <a href="tel:112" className="font-bold underline">112</a> (works on most mobile phones worldwide) or your local emergency number.</p>
        </div>
      )}

      {data && (
        <>
          <EmergencyHero line={data.emergency} city={city} curated={data.curated_country} />
          <Helplines national={data.helplines.national} cityLines={data.helplines.city} city={city} />
          {data.city_resources.length > 0 && <CityResources sites={data.city_resources} city={city} />}
          <FindCare facilities={data.facilities} tab={tab} onTab={setTab} />
          {data.booking.length > 0 && <Booking options={data.booking} />}
          <p className="flex items-start gap-2 text-xs text-zinc-500 dark:text-zinc-400">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            Navis links to providers&apos; own booking pages and phone lines; appointments are made with them directly.
            Facility details come from OpenStreetMap and may be out of date. Call ahead if you can.
          </p>
        </>
      )}
    </div>
  );
}

function telHref(line: HelpLine): string {
  return `tel:${line.number}`;
}

function EmergencyHero({ line, city, curated }: { line: HelpLine; city: string | null; curated: boolean }) {
  return (
    <a
      href={telHref(line)}
      className="flex items-center justify-between gap-4 rounded-3xl bg-gradient-to-br from-rose-600 to-red-700 p-6 text-white shadow-lg transition-transform hover:scale-[1.01] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-rose-300"
    >
      <div>
        <p className="text-sm font-medium text-rose-100">Emergency{city ? ` in ${city}` : ""}</p>
        <p className="mt-1 text-5xl font-bold tracking-tight">{line.display}</p>
        <p className="mt-2 text-sm text-rose-100">
          {line.name}{line.note ? ` · ${line.note}` : ""}
          {!curated && " · confirm the local number when you arrive"}
        </p>
      </div>
      <span className="flex size-16 shrink-0 items-center justify-center rounded-full bg-white/20">
        <Phone className="size-8" aria-hidden />
      </span>
    </a>
  );
}

function LineRow({ line, local }: { line: HelpLine & { generated?: boolean }; local?: string | null }) {
  return (
    <li className="flex items-center justify-between gap-3 py-2.5">
      <div className="min-w-0">
        <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          {line.name}
          {local && <span className="ml-1.5 rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300">In {local}</span>}
        </p>
        {line.note && <p className="text-xs text-zinc-500">{line.note}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {line.url && (
          <a href={line.url} target="_blank" rel="noreferrer noopener" aria-label={`${line.name} website`} className="rounded-lg p-2 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-white/[0.06]">
            <ExternalLink className="size-4" />
          </a>
        )}
        {line.sms && (
          <a href={`sms:${line.number}`} aria-label={`Text ${line.display}`} className="rounded-lg p-2 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-white/[0.06]">
            <MessageSquare className="size-4" />
          </a>
        )}
        <a href={telHref(line)} className="flex items-center gap-1.5 rounded-xl bg-zinc-900 px-3 py-1.5 text-sm font-semibold text-white hover:bg-zinc-800 dark:bg-white dark:text-zinc-900">
          <Phone className="size-3.5" /> {line.display}
        </a>
      </div>
    </li>
  );
}

function Helplines({ national, cityLines, city }: { national: HelpLine[]; cityLines: HelpLine[]; city: string | null }) {
  const rows = [
    ...cityLines.map((l) => ({ line: l, local: city })),
    ...national.map((l) => ({ line: l, local: null as string | null })),
  ];
  const groups = new Map<string, typeof rows>();
  for (const r of rows) {
    const key = CATEGORY_META[r.line.category] ? r.line.category : "other";
    groups.set(key, [...(groups.get(key) ?? []), r]);
  }
  const ordered = [...groups.entries()].sort((a, b) => CATEGORY_META[a[0]].order - CATEGORY_META[b[0]].order);
  return (
    <section className="rounded-3xl border border-zinc-200/80 bg-white/90 p-5 shadow-soft dark:border-white/[0.07] dark:bg-zinc-900/70">
      <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-50">Helplines</h2>
      {cityLines.length === 0 && city && (
        <p className="mt-1 text-xs text-zinc-500">
          These are the national numbers. We don&apos;t have verified local lines for {city} yet.
        </p>
      )}
      <div className="mt-3 grid grid-cols-1 gap-x-8 md:grid-cols-2">
        {ordered.map(([cat, items]) => {
          const meta = CATEGORY_META[cat];
          const Icon = meta.icon;
          return (
            <div key={cat} className="min-w-0 py-2">
              <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-400">
                <Icon className="size-3.5" /> {meta.label}
              </p>
              <ul className="divide-y divide-zinc-100 dark:divide-white/[0.05]">
                {items.map(({ line, local }) => <LineRow key={`${line.name}-${line.number}`} line={line} local={local} />)}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function CityResources({ sites, city }: { sites: CareResponse["data"]["city_resources"]; city: string | null }) {
  return (
    <section className="rounded-3xl border border-zinc-200/80 bg-white/90 p-5 shadow-soft dark:border-white/[0.07] dark:bg-zinc-900/70">
      <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-50">Official {city ? `${city} ` : ""}services online</h2>
      <p className="mt-1 flex items-center gap-1 text-xs text-zinc-500">
        <Sparkles className="size-3" /> Suggested by AI and link-checked. Find local phone numbers on these official sites.
      </p>
      <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {sites.map((s) => (
          <li key={s.url}>
            <a href={s.url} target="_blank" rel="noreferrer noopener" className="flex items-center justify-between gap-2 rounded-xl border border-zinc-200 px-3 py-2.5 text-sm hover:border-indigo-300 dark:border-white/10">
              <span className="min-w-0">
                <span className="block truncate font-medium text-zinc-900 dark:text-zinc-100">{s.name}</span>
                <span className="block truncate text-xs text-zinc-500">{s.url.replace(/^https:\/\//, "")}</span>
              </span>
              <ExternalLink className="size-4 shrink-0 text-zinc-400" />
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

function FindCare({
  facilities, tab, onTab,
}: {
  facilities: CareResponse["data"]["facilities"];
  tab: string;
  onTab: (t: string) => void;
}) {
  const current = facilities[tab];
  return (
    <section className="rounded-3xl border border-zinc-200/80 bg-white/90 p-5 shadow-soft dark:border-white/[0.07] dark:bg-zinc-900/70">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-50">Find care nearby</h2>
        <Link href={`/maps?category=${tab === "hospitals" ? "hospitals" : "pharmacies"}`} className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
          <MapPin className="size-3.5" /> View on map
        </Link>
      </div>
      <div className="no-scrollbar -mx-1 mt-3 flex gap-1.5 overflow-x-auto px-1" role="tablist">
        {Object.entries(facilities).map(([key, f]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => onTab(key)}
            className={cn(
              "shrink-0 rounded-full px-3.5 py-1.5 text-[13px] font-medium",
              tab === key ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900" : "bg-zinc-100 text-zinc-600 dark:bg-white/[0.06] dark:text-zinc-300"
            )}
          >
            {f.label} <span className="opacity-60">{f.items.length}</span>
          </button>
        ))}
      </div>
      {current && current.items.length === 0 && (
        <p className="mt-4 text-sm text-zinc-500">
          None mapped close by. The nearest larger town will have more; try the map to look further.
        </p>
      )}
      <ul className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        {current?.items.map((f) => <FacilityCard key={`${f.name}-${f.lat}`} f={f} kind={tab} />)}
      </ul>
    </section>
  );
}

function FacilityCard({ f, kind }: { f: CareFacility; kind: string }) {
  const Icon = FACILITY_ICONS[kind] ?? Stethoscope;
  const phone = f.phone ? f.phone.replace(/[^\d+]/g, "") : null;
  return (
    <li className="min-w-0 rounded-2xl border border-zinc-200/80 p-4 dark:border-white/[0.07]">
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-rose-50 text-rose-600 dark:bg-rose-500/10 dark:text-rose-300">
          <Icon className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-medium text-zinc-900 dark:text-zinc-100">{f.name}</p>
          {f.address && <p className="truncate text-xs text-zinc-500">{f.address}</p>}
          <p className="mt-0.5 text-xs text-zinc-400">
            {km(f.distance_m)}{f.opening_hours ? ` · ${f.opening_hours}` : ""}
          </p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {phone && (
          <a href={`tel:${phone}`} className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-semibold text-white dark:bg-white dark:text-zinc-900">
            <Phone className="size-3.5" /> Call
          </a>
        )}
        {f.website && (
          <a href={f.website} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700">
            <CalendarCheck className="size-3.5" /> Book or contact
          </a>
        )}
        <Link href={`/maps?lat=${f.lat}&lon=${f.lon}&name=${encodeURIComponent(f.name)}`} className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-700 dark:bg-white/[0.06] dark:text-zinc-200">
          <Navigation className="size-3.5" /> Directions
        </Link>
        <a href={googleMapsDirectionsUrl(f.lat, f.lon)} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200">
          Google Maps <ExternalLink className="size-3" />
        </a>
      </div>
    </li>
  );
}

function Booking({ options }: { options: CareResponse["data"]["booking"] }) {
  return (
    <section className="rounded-3xl border border-zinc-200/80 bg-white/90 p-5 shadow-soft dark:border-white/[0.07] dark:bg-zinc-900/70">
      <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-50">Book a doctor or video visit</h2>
      <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {options.map((o) => (
          <li key={o.url}>
            <a href={o.url} target="_blank" rel="noreferrer noopener" className="flex h-full flex-col rounded-2xl border border-zinc-200 p-4 hover:border-indigo-300 hover:shadow-soft dark:border-white/10">
              <span className="flex items-center justify-between gap-2 font-semibold text-zinc-900 dark:text-zinc-100">
                {o.name} <ExternalLink className="size-3.5 text-zinc-400" />
              </span>
              <span className="mt-1 text-[13px] text-zinc-500">{o.what}</span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

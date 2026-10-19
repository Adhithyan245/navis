"use client";
/**
 * Renderers for agent sections (multi-agent answers and the /today hub).
 *
 *   <SectionStatusNote>  the agent's positive message + alternatives when it
 *                        has little or nothing to show (status ≠ ok)
 *   <AgentSectionBody>   purpose-built views for the domain agents (weather,
 *                        money, safety, transit, arrival, culture, tech).
 *                        Returns null for workflow kinds, which ResultStream
 *                        renders with its existing item grids.
 */
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Bike,
  Bus,
  Clock,
  ExternalLink,
  Info,
  Lightbulb,
  Phone,
  Plane,
  Ship,
  Sparkles,
  Sunrise,
  Wind,
  Sunset,
  Train,
} from "lucide-react";

import { EventListingCard } from "@/components/runtime/EventListingCard";
import type { RuntimeSection } from "@/lib/runtime/events";
import type { EventListing } from "@/lib/runtime/listings";
import { googleMapsDirectionsUrl } from "@/lib/runtime/maps";
import { cn } from "@/lib/utils";

type Rec = Record<string, unknown>;

interface Poi {
  name: string;
  address?: string | null;
  distance_m?: number;
  lat?: number;
  lon?: number;
  phone?: string | null;
  tags?: Record<string, string>;
}

const asRec = (v: unknown): Rec => (v && typeof v === "object" ? (v as Rec) : {});
const asList = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

function km(m?: number): string {
  if (typeof m !== "number") return "";
  return m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(m < 10_000 ? 1 : 0)} km`;
}

export const DOMAIN_KINDS = new Set(["weather", "money", "safety", "transit", "arrival", "culture", "tech"]);

// ── Status note ─────────────────────────────────────────────────────────────

export function SectionStatusNote({ section }: { section: RuntimeSection }) {
  const status = section.status;
  const message = section.message;
  const alternatives = section.alternatives ?? [];
  if (!message || !status || status === "ok") return null;
  return (
    <div
      className={cn(
        "rounded-xl border px-4 py-3 text-[13px]",
        status === "unavailable"
          ? "border-zinc-200 bg-zinc-50 text-zinc-700 dark:border-white/10 dark:bg-white/[0.03] dark:text-zinc-300"
          : "border-indigo-200/70 bg-indigo-50/60 text-indigo-950 dark:border-indigo-400/20 dark:bg-indigo-500/10 dark:text-indigo-100"
      )}
    >
      <p className="flex items-start gap-2">
        <Info className="mt-0.5 size-4 shrink-0 opacity-70" aria-hidden />
        <span>{message}</span>
      </p>
      {alternatives.length > 0 && (
        <ul className="mt-2 space-y-1 pl-6">
          {alternatives.map((a) => (
            <li key={a} className="flex items-start gap-1.5 text-zinc-600 dark:text-zinc-400">
              <Lightbulb className="mt-0.5 size-3.5 shrink-0 text-amber-500" aria-hidden />
              {a}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** The agent's one-line answer for ok sections ("Clear, 5°C in Boston"). */
export function SectionLead({ section }: { section: RuntimeSection }) {
  if (section.status !== "ok" || !section.message) return null;
  return <p className="text-[15px] font-medium text-zinc-800 dark:text-zinc-100">{section.message}</p>;
}

// ── Domain bodies ───────────────────────────────────────────────────────────

export function AgentSectionBody({ section, limit }: { section: RuntimeSection; limit?: number }) {
  const data = asRec(section.data);
  switch (section.kind) {
    case "weather":
      return <WeatherBody data={data} />;
    case "money":
      return <MoneyBody data={data} />;
    case "safety":
      return <SafetyBody data={data} />;
    case "transit":
      return <TransitBody data={data} />;
    case "arrival":
      return <ArrivalBody data={data} />;
    case "culture":
      return <CultureBody data={data} />;
    case "tech":
      return <TechBody data={data} limit={limit} />;
    default:
      return null;
  }
}

function WeatherBody({ data }: { data: Rec }) {
  const days = asList<Rec>(data.days);
  const packing = asList<string>(data.packing);
  const today = days[0];
  return (
    <div className="space-y-3">
      {days.length > 0 && (
        <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1">
          {days.map((d) => {
            const date = typeof d.date === "string" ? new Date(`${d.date}T12:00:00`) : null;
            return (
              <div key={String(d.date)} className="min-w-[84px] shrink-0 rounded-xl border border-zinc-200/80 bg-white/70 px-3 py-2 text-center text-xs dark:border-white/[0.07] dark:bg-zinc-900/50">
                <p className="font-medium text-zinc-500">{date ? date.toLocaleDateString(undefined, { weekday: "short" }) : ""}</p>
                <p className="mt-1 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                  {num(d.max_c) !== null ? Math.round(num(d.max_c)!) : "–"}° <span className="font-normal text-zinc-400">{num(d.min_c) !== null ? Math.round(num(d.min_c)!) : "–"}°</span>
                </p>
                <p className="truncate text-zinc-500">{String(d.summary ?? "")}</p>
                {num(d.rain_chance) !== null && num(d.rain_chance)! >= 30 && <p className="text-sky-600 dark:text-sky-400">{num(d.rain_chance)}% rain</p>}
              </div>
            );
          })}
        </div>
      )}
      {today && (typeof today.sunrise === "string" || typeof today.sunset === "string") && (
        <p className="flex items-center gap-4 text-xs text-zinc-500">
          {typeof today.sunrise === "string" && <span className="flex items-center gap-1"><Sunrise className="size-3.5" />{today.sunrise.slice(11, 16)}</span>}
          {typeof today.sunset === "string" && <span className="flex items-center gap-1"><Sunset className="size-3.5" />{today.sunset.slice(11, 16)}</span>}
        </p>
      )}
      <AirQuality air={asRec(data.air)} />
      {packing.length > 0 && (
        <ul className="space-y-1 text-[13px] text-zinc-600 dark:text-zinc-400">
          {packing.map((p) => <li key={p}>• {p}</li>)}
        </ul>
      )}
    </div>
  );
}

const AQI_TONE: Record<string, string> = {
  Good: "bg-emerald-50 text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-200",
  Moderate: "bg-amber-50 text-amber-900 dark:bg-amber-500/10 dark:text-amber-200",
};

function AirQuality({ air }: { air: Rec }) {
  const aqi = num(air.us_aqi);
  const label = typeof air.label === "string" ? air.label : null;
  if (aqi === null || !label) return null;
  const pollen = asRec(air.pollen);
  const pollenText = Object.entries(pollen)
    .filter(([, v]) => typeof v === "number" && v >= 10)
    .map(([k]) => k)
    .join(", ");
  return (
    <p className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl px-3 py-2 text-[13px]",
      AQI_TONE[label] ?? "bg-rose-50 text-rose-800 dark:bg-rose-500/10 dark:text-rose-200")}>
      <span className="flex items-center gap-1.5 font-medium"><Wind className="size-4" aria-hidden /> Air: {label} (AQI {Math.round(aqi)})</span>
      {num(air.uv_index) !== null && <span>UV {Math.round(num(air.uv_index)!)}</span>}
      {pollenText && <span>Pollen: {pollenText}</span>}
    </p>
  );
}

function MoneyBody({ data }: { data: Rec }) {
  const tipping = typeof data.tipping === "string" ? data.tipping : null;
  if (!tipping) return null;
  return <p className="text-[13px] text-zinc-600 dark:text-zinc-400"><span className="font-medium">Tipping: </span>{tipping}</p>;
}

function PoiList({ items, icon: Icon }: { items: Poi[]; icon?: typeof Bus }) {
  if (items.length === 0) return null;
  return (
    <ul className="divide-y divide-zinc-100 dark:divide-white/[0.05]">
      {items.map((p, i) => (
        <li key={`${p.name}-${i}`} className="flex items-center justify-between gap-3 py-2 text-[13px]">
          <span className="flex min-w-0 items-center gap-2">
            {Icon && <Icon className="size-4 shrink-0 text-zinc-400" aria-hidden />}
            <span className="min-w-0">
              <span className="block truncate font-medium text-zinc-800 dark:text-zinc-100">{p.name}</span>
              {p.address && <span className="block truncate text-xs text-zinc-500">{p.address}</span>}
            </span>
          </span>
          <span className="flex shrink-0 items-center gap-2 text-xs text-zinc-500">
            {km(p.distance_m)}
            {typeof p.lat === "number" && typeof p.lon === "number" && (
              <a href={googleMapsDirectionsUrl(p.lat, p.lon)} target="_blank" rel="noreferrer noopener" className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                Directions
              </a>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

interface Line { name: string; number: string; display: string; category: string }

function SafetyBody({ data }: { data: Rec }) {
  const h = asRec(data.helplines);
  const national = asList<Line>(h.national);
  const city = asList<Line>(h.city);
  // Emergency-type national lines first, then the city's own lines.
  const lines = [
    ...national.filter((l) => ["emergency", "police", "medical", "fire"].includes(l.category)).slice(0, 4),
    ...city.slice(0, 3),
  ];
  const alerts = asList<Rec>(data.alerts);
  return (
    <div className="space-y-3">
      {alerts.length > 0 && <AlertList alerts={alerts.slice(0, 3)} />}
      <div className="flex flex-wrap gap-2">
        {lines.map((l) => (
          <a key={`${l.name}-${l.number}`} href={`tel:${l.number}`} className="flex max-w-full items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-rose-800 dark:border-rose-400/20 dark:bg-rose-500/10 dark:text-rose-200">
            <Phone className="size-4 shrink-0" aria-hidden />
            <span className="truncate text-xs">{l.name}</span>
            <span className="shrink-0 text-base font-semibold">{l.display}</span>
          </a>
        ))}
      </div>
      {(["hospitals", "pharmacies"] as const).map((g) =>
        asList<Poi>(data[g]).length > 0 ? (
          <div key={g}>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-400">{g === "hospitals" ? "Nearest hospitals" : "Nearest pharmacies"}</p>
            <PoiList items={asList<Poi>(data[g]).slice(0, 3)} />
          </div>
        ) : null
      )}
    </div>
  );
}

function AlertList({ alerts }: { alerts: Rec[] }) {
  return (
    <ul className="space-y-2">
      {alerts.map((a, i) => {
        const severe = ["extreme", "red", "severe"].includes(String(a.severity));
        return (
          <li key={`${String(a.title)}-${i}`} className={cn("rounded-xl border px-3 py-2 text-[13px]",
            severe ? "border-rose-300 bg-rose-50 text-rose-900 dark:border-rose-400/30 dark:bg-rose-500/10 dark:text-rose-100"
                   : "border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-400/20 dark:bg-amber-500/10 dark:text-amber-100")}>
            <p className="flex items-start gap-2 font-medium">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>
                {String(a.title)}
                {typeof a.distance_km === "number" && <span className="font-normal opacity-75"> · {a.distance_km} km away</span>}
              </span>
            </p>
            {typeof a.detail === "string" && a.detail && <p className="mt-0.5 pl-6 opacity-90">{a.detail}</p>}
            {typeof a.instruction === "string" && a.instruction && <p className="mt-1 pl-6">{a.instruction}</p>}
            <p className="mt-1 pl-6 text-[11px] opacity-70">
              {String(a.source ?? "")}
              {typeof a.url === "string" && a.url && (
                <a href={a.url} target="_blank" rel="noreferrer noopener" className="ml-2 underline">Details</a>
              )}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

const MODE_LABEL: Record<string, string> = { subway: "Metro", train: "Train", tram: "Tram", bus: "Bus", ferry: "Ferry" };
const MODE_ICON: Record<string, typeof Bus> = { subway: Train, train: Train, tram: Train, bus: Bus, ferry: Ship };

function TransitBody({ data }: { data: Rec }) {
  const tip = typeof data.tip === "string" ? data.tip : null;
  const modes = Object.keys(MODE_LABEL).filter((m) => asList<Poi>(data[m]).length > 0);
  return (
    <div className="space-y-3">
      {tip && (
        <p className="flex items-start gap-2 rounded-xl bg-amber-50 px-3 py-2 text-[13px] text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
          <Lightbulb className="mt-0.5 size-4 shrink-0" aria-hidden />{tip}
        </p>
      )}
      <BikeShare bikes={asRec(data.bikeshare)} />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {modes.map((m) => (
          <div key={m}>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-400">{MODE_LABEL[m]}</p>
            <PoiList items={asList<Poi>(data[m]).slice(0, 2)} icon={MODE_ICON[m]} />
          </div>
        ))}
      </div>
    </div>
  );
}

function BikeShare({ bikes }: { bikes: Rec }) {
  const stations = asList<Rec>(bikes.stations).slice(0, 3);
  if (typeof bikes.network !== "string" || stations.length === 0) return null;
  return (
    <div>
      <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-400">
        <Bike className="size-3.5" aria-hidden /> {bikes.network} bike share
      </p>
      <ul className="divide-y divide-zinc-100 dark:divide-white/[0.05]">
        {stations.map((st, i) => (
          <li key={`${String(st.name)}-${i}`} className="flex items-center justify-between gap-3 py-1.5 text-[13px]">
            <span className="min-w-0 truncate text-zinc-800 dark:text-zinc-100">{String(st.name)}</span>
            <span className="shrink-0 text-xs text-zinc-500">
              <span className="font-semibold text-emerald-600 dark:text-emerald-400">{num(st.free_bikes) ?? "–"}</span> bikes ·{" "}
              {num(st.empty_slots) ?? "–"} docks · {km(num(st.distance_m) ?? undefined)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ArrivalBody({ data }: { data: Rec }) {
  const airports = asList<Poi>(data.airports);
  const ferries = asList<Poi>(data.ferry_terminals);
  const localTime = typeof data.local_time === "string" ? data.local_time : null;
  const tz = typeof data.timezone === "string" ? data.timezone : null;
  return (
    <div className="space-y-3">
      {localTime && (
        <p className="flex items-center gap-2 text-[13px] text-zinc-600 dark:text-zinc-400">
          <Clock className="size-4" aria-hidden />
          Local time {new Date(localTime).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
          {tz && <span className="text-zinc-400">· {tz.replace(/_/g, " ")}</span>}
        </p>
      )}
      <PoiList items={airports.slice(0, 3).map((a) => ({ ...a, name: a.tags?.iata ? `${a.name} (${a.tags.iata})` : a.name }))} icon={Plane} />
      {airports.length === 0 && <PoiList items={ferries.slice(0, 2)} icon={Ship} />}
    </div>
  );
}

function CultureBody({ data }: { data: Rec }) {
  const overview = asRec(data.overview);
  const culture = asRec(data.culture);
  const tips = asList<string>(culture.etiquette);
  const phrases = asList<{ phrase: string; meaning: string }>(culture.phrases);
  return (
    <div className="space-y-3 text-[13px] text-zinc-700 dark:text-zinc-300">
      {typeof overview.extract === "string" && (
        <p className="leading-relaxed">
          {overview.extract.length > 420 ? `${overview.extract.slice(0, 420)}…` : overview.extract}
          {typeof overview.url === "string" && (
            <a href={overview.url} target="_blank" rel="noreferrer noopener" className="ml-1 inline-flex items-center gap-0.5 font-medium text-indigo-600 hover:underline dark:text-indigo-400">
              Read more <ExternalLink className="size-3" />
            </a>
          )}
        </p>
      )}
      {typeof asRec(data.travel_guide).url === "string" && (
        <a
          href={String(asRec(data.travel_guide).url)}
          target="_blank"
          rel="noreferrer noopener"
          className="flex items-center justify-between gap-2 rounded-xl border border-zinc-200/80 px-3 py-2 font-medium text-indigo-700 hover:bg-indigo-50/50 dark:border-white/[0.07] dark:text-indigo-300 dark:hover:bg-indigo-500/10"
        >
          <span>Travel guide: getting around, sights, eating, staying safe</span>
          <span className="flex shrink-0 items-center gap-1 text-xs text-zinc-500">Wikivoyage <ExternalLink className="size-3" /></span>
        </a>
      )}
      {tips.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-400">Good to know</p>
          <ul className="space-y-1">{tips.map((t) => <li key={t}>• {t}</li>)}</ul>
        </div>
      )}
      {phrases.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-400">
            Handy phrases{typeof culture.language === "string" && culture.language ? ` (${culture.language})` : ""}
          </p>
          <div className="flex flex-wrap gap-2">
            {phrases.map((p) => (
              <span key={p.phrase} className="rounded-lg bg-zinc-100 px-2.5 py-1 dark:bg-white/[0.06]">
                <span className="font-medium">{p.phrase}</span> <span className="text-zinc-500">· {p.meaning}</span>
              </span>
            ))}
          </div>
        </div>
      )}
      {culture.generated === true && (
        <p className="flex items-center gap-1 text-[11px] text-zinc-400">
          <Sparkles className="size-3" /> Customs and phrases are AI-compiled; check with locals when in doubt.
        </p>
      )}
    </div>
  );
}

function TechBody({ data, limit = 6 }: { data: Rec; limit?: number }) {
  const local = asList<EventListing>(data.results);
  const online = asList<EventListing>(data.online);
  const shown = (local.length > 0 ? local : online).slice(0, limit);
  return (
    <div className="space-y-3">
      {shown.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((e) => <EventListingCard key={e.id} event={e} />)}
        </div>
      )}
      <Link href="/events?category=tech" className="inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400">
        {local.length > 0 && online.length > 0
          ? `See all ${local.length + online.length} tech events, ${online.length} online`
          : "See all tech events"}
        <ArrowRight className="size-3.5" />
      </Link>
    </div>
  );
}

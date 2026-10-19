/** Shapes returned by /v2/maps/* and /v2/care. */

export interface MapPoi {
  name: string;
  address?: string | null;
  categories?: string[];
  lat: number;
  lon: number;
  distance_m?: number;
  phone?: string | null;
  website?: string | null;
  opening_hours?: string | null;
  tags?: Record<string, string>;
  /** /v2/maps/place only */
  attributes?: Record<string, string>;
  landmark?: boolean;
  about?: { extract: string; image?: string | null; url?: string | null } | null;
}

export interface PlaceDetailsResponse {
  place: MapPoi;
}

export interface NearbyResponse {
  items: MapPoi[];
  message: string | null;
}

export interface RouteStep {
  instruction: string;
  distance_m?: number;
  time_s?: number;
  /** transit legs: ISO departure time; realtime = live-tracked */
  departure?: string;
  realtime?: boolean;
}

export interface TransitLine {
  name: string;
  mode: string;
  color: string | null;
  text_color: string | null;
  agency?: string | null;
  url?: string | null;
  departure?: string | null;
  from?: string | null;
  realtime?: boolean;
}

export type TravelMode = "drive" | "walk" | "bike" | "transit";

export interface RouteOption {
  mode: TravelMode;
  distance_km: number;
  duration_min: number;
  geometry: [number, number][];
  steps: RouteStep[];
  /** transit from timetables only */
  lines?: TransitLine[];
  departure?: string;
  arrival?: string;
  timezone?: string | null;
  alerts?: string[];
  source?: "timetable";
}

export interface RouteResponse {
  routes: RouteOption[];
  message: string | null;
}

export interface HelpLine {
  name: string;
  number: string;
  display: string;
  category: string;
  note?: string;
  sms?: boolean;
  url?: string;
}

export interface CareFacility {
  name: string;
  address?: string | null;
  distance_m?: number;
  lat: number;
  lon: number;
  phone?: string | null;
  website?: string | null;
  opening_hours?: string | null;
  emergency?: boolean;
}

export interface CareResponse {
  status: "ok" | "partial" | "empty" | "unavailable";
  message: string;
  alternatives: string[];
  data: {
    emergency: HelpLine;
    helplines: { national: HelpLine[]; city: HelpLine[] };
    city_resources: Array<{ name: string; url: string; category: string; generated?: boolean }>;
    facilities: Record<string, { label: string; items: CareFacility[] }>;
    booking: Array<{ name: string; url: string; what: string }>;
    curated_country: boolean;
  };
}

export const MAP_CATEGORIES = [
  { key: "restaurants", label: "Restaurants" },
  { key: "cafes", label: "Coffee" },
  { key: "groceries", label: "Groceries" },
  { key: "pharmacies", label: "Pharmacies" },
  { key: "hospitals", label: "Hospitals" },
  { key: "atms", label: "ATMs & banks" },
  { key: "transit", label: "Transit" },
  { key: "hotels", label: "Hotels" },
  { key: "attractions", label: "Things to do" },
  { key: "parks", label: "Parks" },
  { key: "gas", label: "Gas & charging" },
  { key: "parking", label: "Parking" },
] as const;

export type MapCategory = (typeof MAP_CATEGORIES)[number]["key"];

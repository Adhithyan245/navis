import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Navis — your local companion anywhere",
    short_name: "Navis",
    description:
      "Maps, events, transit, health and emergency numbers, essentials and local know-how for any city or island.",
    start_url: "/today",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#0b0c14",
    theme_color: "#4f46e5",
    categories: ["travel", "navigation", "lifestyle"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Maps", url: "/maps", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Health & emergency", url: "/care", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Events", url: "/events", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
    ],
  };
}

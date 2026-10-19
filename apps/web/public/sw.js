/*
 * Navis service worker: keeps the app shell usable on a bad connection.
 *
 *   - Page navigations: network first; offline → cached page or /offline.
 *   - Static assets (/_next/static, /icons, /maplibre): cache first.
 *   - API calls, auth and map tiles: never cached here (always live).
 */
const VERSION = "navis-v1";
const OFFLINE_URL = "/offline";
const PRECACHE = [OFFLINE_URL, "/icons/icon-192.png", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function isStatic(url) {
  return (
    url.origin === self.location.origin &&
    (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/") || url.pathname.startsWith("/maplibre/"))
  );
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (req.mode === "navigate") {
    if (url.pathname.startsWith("/api/")) return;
    event.respondWith(
      fetch(req).catch(async () => (await caches.match(req)) || (await caches.match(OFFLINE_URL)) || Response.error())
    );
    return;
  }

  if (isStatic(url)) {
    event.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            if (res.ok) {
              const copy = res.clone();
              caches.open(VERSION).then((c) => c.put(req, copy));
            }
            return res;
          })
      )
    );
  }
});

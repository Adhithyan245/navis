import type { NextConfig } from "next";

// Headers for every response (pages, API routes, static files). The
// Content-Security-Policy is set per request in src/proxy.ts (it needs a nonce).
const securityHeaders = [
  ...(process.env.NODE_ENV === "production"
    ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" }]
    : []),
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Location (maps, nearby care) and microphone (voice search) for our own pages only.
  { key: "Permissions-Policy", value: "camera=(), geolocation=(self), microphone=(self), payment=(), usb=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin-allow-popups" },
];

// Comma-separated hosts (e.g. a phone testing over Wi-Fi) allowed to use the dev server.
const devOrigins = (process.env.NAVIS_DEV_ORIGINS ?? "").split(",").map((s) => s.trim()).filter(Boolean);
const apiRaw = (process.env.NAVIS_API_INTERNAL_URL || "http://127.0.0.1:8100").replace(/\/+$/, "");
// Hosts such as Render pass a private address as "host:port".
const apiInternal = /^https?:\/\//.test(apiRaw) ? apiRaw : `http://${apiRaw}`;

const nextConfig: NextConfig = {
  poweredByHeader: false,
  allowedDevOrigins: devOrigins,
  // Same-origin path to the API (NEXT_PUBLIC_API_URL=/navis-api): phones and the
  // native app then need only the web origin, and CORS isn't involved.
  async rewrites() {
    return [{ source: "/navis-api/:path*", destination: `${apiInternal}/:path*` }];
  },
  async headers() {
    return [
      { source: "/:path*", headers: securityHeaders },
      {
        // The service worker must always be revalidated so updates ship promptly.
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Content-Type", value: "application/javascript; charset=utf-8" },
        ],
      },
      {
        // Android App Links / iOS Universal Links verification files.
        source: "/.well-known/:file*",
        headers: [{ key: "Content-Type", value: "application/json" }],
      },
    ];
  },
};

export default nextConfig;

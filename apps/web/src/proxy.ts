/**
 * Runs before every page:
 *
 * 1. Content-Security-Policy with a per-request nonce (Next applies it to
 *    its own scripts; the root layout applies it to the theme script).
 * 2. Optimistic auth check (cookie only, no backend call):
 *      * signed-out visitors to app pages → /login?next=<where they were going>
 *      * signed-in visitors to /login or /signup → /today
 *    Public pages (landing, legal, support, offline) are open to everyone.
 *    The (main) layout does the authoritative check again on the server.
 */
import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE, decodeSession } from "@/lib/auth/session";

const PUBLIC_PATHS = new Set(["/", "/login", "/signup", "/privacy", "/terms", "/disclaimer", "/support", "/offline"]);
const AUTH_PAGES = new Set(["/login", "/signup"]);

function apiOrigin(): string {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8100").origin;
  } catch {
    return "";
  }
}

function contentSecurityPolicy(nonce: string): string {
  const dev = process.env.NODE_ENV === "development";
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    // React style props and MapLibre set inline styles.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    "font-src 'self' data:",
    `connect-src 'self' ${apiOrigin()} https://api.maptiler.com https://*.maptiler.com${dev ? " ws: http://localhost:* http://127.0.0.1:*" : ""}`,
    "worker-src 'self' blob:",
    "media-src 'self' blob:",
    "frame-src 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(dev ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");
}

function withCsp(response: NextResponse, csp: string): NextResponse {
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export default async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const nonce = btoa(crypto.randomUUID());
  const csp = contentSecurityPolicy(nonce);

  const user = await decodeSession(request.cookies.get(SESSION_COOKIE)?.value);
  if (PUBLIC_PATHS.has(pathname)) {
    if (user && AUTH_PAGES.has(pathname)) {
      return withCsp(NextResponse.redirect(new URL("/today", request.nextUrl)), csp);
    }
  } else if (!user) {
    const login = new URL("/login", request.nextUrl);
    login.searchParams.set("next", `${pathname}${search}`);
    return withCsp(NextResponse.redirect(login), csp);
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  return withCsp(NextResponse.next({ request: { headers: requestHeaders } }), csp);
}

// Skip API routes (incl. /api/auth/*), the /navis-api proxy (the API does its own
// auth), Next internals, static files and prefetches.
export const config = {
  matcher: [
    {
      source: "/((?!api|navis-api|_next/static|_next/image|favicon.ico|.*\\..*).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};

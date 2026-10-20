"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bookmark,
  CalendarDays,
  ClipboardList,
  Compass,
  HeartPulse,
  Home as HomeIcon,
  Map as MapIcon,
  MapPinned,
  MoreHorizontal,
  Route,
  ShieldCheck,
  Sparkles,
  Sun,
  TrainFront,
  Waypoints,
  X,
} from "lucide-react";

import { DarkModeToggle } from "@/components/runtime/DarkModeToggle";
import { UserMenu } from "@/components/UserMenu";
import type { SessionUser } from "@/lib/auth/session";
import { cn } from "@/lib/utils";

// Primary destinations. /explore, /match and /commute previously had no
// entry point anywhere in the UI.
const NAV = [
  { href: "/today", label: "Today", icon: Sun },
  { href: "/ask", label: "Ask", icon: Sparkles },
  { href: "/maps", label: "Maps", icon: MapIcon },
  { href: "/transit", label: "Transit", icon: TrainFront },
  { href: "/care", label: "Health", icon: HeartPulse },
  { href: "/explore", label: "Explore", icon: Compass },
  { href: "/events", label: "Events", icon: CalendarDays },
  { href: "/match", label: "Neighborhoods", icon: HomeIcon },
  { href: "/commute", label: "Commute", icon: Route },
  { href: "/plan", label: "Plan", icon: Waypoints },
  { href: "/essentials", label: "Essentials", icon: ClipboardList },
] as const;

const UTIL = [
  { href: "/locations", label: "Saved locations", icon: MapPinned },
  { href: "/saved", label: "Saved items", icon: Bookmark },
] as const;

// Phone "More" sheet only (desktop has these in the account menu).
const MOBILE_EXTRA = [{ href: "/account", label: "Account", icon: ShieldCheck }] as const;

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppLayout({
  children,
  user,
}: {
  children: React.ReactNode;
  user: SessionUser;
}) {
  const pathname = usePathname() ?? "/";

  return (
    <div className="flex min-h-screen flex-col text-zinc-900 dark:text-zinc-100">
      <header className="glass sticky top-0 z-50 w-full border-b border-zinc-200/70 pt-[env(safe-area-inset-top)] dark:border-white/[0.06]">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-6">
          <Link
            href="/today"
            className="group flex shrink-0 items-center gap-2.5 rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            <span className="relative flex size-8 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-indigo-600 to-fuchsia-500 text-sm font-bold text-white shadow-glow transition-transform group-hover:scale-105">
              N
            </span>
            <span className="text-[15px] font-semibold tracking-tight">Navis</span>
          </Link>

          <nav aria-label="Primary" className="no-scrollbar hidden min-w-0 flex-1 items-center gap-0.5 overflow-x-auto md:flex">
            {NAV.map(({ href, label }) => {
              const active = isActive(pathname, href);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "shrink-0 rounded-full px-2.5 py-1.5 text-[13px] font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-indigo-400",
                    active
                      ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
                      : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-white/[0.06] dark:hover:text-zinc-100"
                  )}
                >
                  {label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-1">
            {UTIL.map(({ href, label, icon: Icon }) => {
              const active = isActive(pathname, href);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-label={label}
                  title={label}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "inline-flex size-9 items-center justify-center rounded-full transition-colors outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 [&_svg]:size-4",
                    active
                      ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300"
                      : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-white/[0.06] dark:hover:text-zinc-100"
                  )}
                >
                  <Icon />
                </Link>
              );
            })}
            <span aria-hidden className="mx-1 h-5 w-px bg-zinc-200 dark:bg-white/10" />
            <DarkModeToggle />
            <span className="ml-1">
              <UserMenu user={user} />
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full min-w-0 max-w-6xl flex-1 px-[max(1rem,env(safe-area-inset-left))] pt-6 pb-[calc(7rem+env(safe-area-inset-bottom))] sm:px-6 md:pt-10 md:pb-16 animate-in fade-in slide-in-from-bottom-1 duration-500">
        {children}
        {!pathname.startsWith("/maps") && (
          <p className="mx-auto mt-12 max-w-2xl text-center text-[11px] leading-relaxed text-zinc-400 dark:text-zinc-500">
            Information in Navis is gathered from the web and public data, and some of it is written by AI. It can be
            out of date or wrong, so check official sources before relying on it. Navis isn&apos;t professional advice
            or an emergency service.{" "}
            <Link href="/disclaimer" className="underline hover:text-zinc-600 dark:hover:text-zinc-300">Disclaimer</Link>
          </p>
        )}
      </main>

      <MobileTabBar pathname={pathname} />
    </div>
  );
}

// Phone tab bar: the four most-used destinations plus "More" for the rest.
const MOBILE_PRIMARY = 4;

function MobileTabBar({ pathname }: { pathname: string }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [openedAt, setOpenedAt] = useState(pathname);
  // Close the sheet after navigating (set-during-render, no effect).
  if (moreOpen && pathname !== openedAt) {
    setMoreOpen(false);
  }
  useEffect(() => {
    if (!moreOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMoreOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [moreOpen]);

  const primary = NAV.slice(0, MOBILE_PRIMARY);
  const rest = [...NAV.slice(MOBILE_PRIMARY), ...UTIL, ...MOBILE_EXTRA];
  const restActive = rest.some(({ href }) => isActive(pathname, href));

  return (
    <>
      {moreOpen && (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label="More">
          <button type="button" aria-label="Close menu" className="absolute inset-0 bg-zinc-950/30" onClick={() => setMoreOpen(false)} />
          <div className="glass absolute inset-x-3 bottom-[calc(5rem+env(safe-area-inset-bottom))] rounded-2xl border border-zinc-200/70 p-2 shadow-soft dark:border-white/[0.08]">
            <div className="grid grid-cols-3 gap-1">
              {rest.map(({ href, label, icon: Icon }) => (
                <Link
                  key={href}
                  href={href}
                  aria-current={isActive(pathname, href) ? "page" : undefined}
                  onClick={() => setMoreOpen(false)}
                  className={cn(
                    "flex flex-col items-center gap-1 rounded-xl px-2 py-3 text-[11px] font-medium [&_svg]:size-5",
                    isActive(pathname, href)
                      ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300"
                      : "text-zinc-600 dark:text-zinc-300"
                  )}
                >
                  <Icon />
                  <span className="text-center">{label === "Neighborhoods" ? "Areas" : label}</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}
      <nav
        aria-label="Primary"
        className="glass fixed inset-x-3 bottom-[calc(0.75rem+env(safe-area-inset-bottom))] z-50 flex items-center justify-between rounded-2xl border border-zinc-200/70 px-1.5 py-1.5 shadow-soft md:hidden dark:border-white/[0.08]"
      >
        {primary.map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-xl px-1 py-1.5 text-[10px] font-medium transition-colors [&_svg]:size-[18px]",
                active
                  ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300"
                  : "text-zinc-500 dark:text-zinc-400"
              )}
            >
              <Icon />
              <span className="max-w-full truncate">{label === "Neighborhoods" ? "Areas" : label}</span>
            </Link>
          );
        })}
        <button
          type="button"
          onClick={() => {
            setOpenedAt(pathname);
            setMoreOpen((v) => !v);
          }}
          aria-expanded={moreOpen}
          className={cn(
            "flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-xl px-1 py-1.5 text-[10px] font-medium transition-colors [&_svg]:size-[18px]",
            restActive || moreOpen
              ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300"
              : "text-zinc-500 dark:text-zinc-400"
          )}
        >
          {moreOpen ? <X /> : <MoreHorizontal />}
          <span>More</span>
        </button>
      </nav>
    </>
  );
}

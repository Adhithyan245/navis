/**
 * Landing page — public. Explains Navis to first-time visitors and routes
 * them to sign-up / sign-in (or straight into the app when signed in).
 */
import Link from "next/link";
import { cookies } from "next/headers";
import {
  ArrowRight,
  CalendarDays,
  ClipboardList,
  Compass,
  Globe2,
  Home,
  Mic,
  Route,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { SESSION_COOKIE, decodeSession } from "@/lib/auth/session";

export const metadata = {
  title: "Navis · Your guide to any place you land",
  description:
    "Navis helps you settle into any city, town or island: what's on, where to stay, how to get around, and what to sort out first.",
};

const FEATURES = [
  {
    icon: Sparkles,
    title: "Ask anything",
    body: "“Coffee near my hotel”, “how do I get from the airport”, “is this area safe at night”. Plain answers with real places.",
  },
  {
    icon: CalendarDays,
    title: "What's on",
    body: "Concerts, sports, theatre, tech conferences, festivals and public holidays, with times, venues and tickets.",
  },
  {
    icon: ClipboardList,
    title: "First-week essentials",
    body: "SIM and data, transit cards, banking, emergency numbers, registration. The things locals forget to tell you.",
  },
  {
    icon: Home,
    title: "Find your neighborhood",
    body: "Areas that fit your budget, household and commute, with the trade-offs spelled out.",
  },
  {
    icon: Route,
    title: "Get around",
    body: "Door-to-door times by car, bike and on foot, so you can choose where to live or stay with confidence.",
  },
  {
    icon: Mic,
    title: "Just say it",
    body: "Hands full of luggage? Ask out loud and Navis transcribes and answers.",
  },
] as const;

const STEPS = [
  { title: "Tell us where you're landing", body: "Any city, town, island or exact address. Abbreviations like NYC or JFK work too." },
  { title: "Get a plan for your first days", body: "Navis tailors essentials, neighborhoods and events to you." },
  { title: "Explore like a local", body: "Ask follow-ups any time; everything links to maps, tickets and official sources." },
] as const;

const PLACES = ["Tokyo", "Reykjavík", "Bali", "Nairobi", "Lisbon", "Lima", "Malta", "Boston", "Chennai", "Hobart"];

export default async function LandingPage() {
  const user = await decodeSession((await cookies()).get(SESSION_COOKIE)?.value);
  const primary = user
    ? { href: "/today", label: "Open Navis" }
    : { href: "/signup", label: "Get started, it's free" };

  return (
    <div className="flex min-h-screen flex-col text-zinc-900 dark:text-zinc-100">
      {/* Nav */}
      <header className="glass sticky top-0 z-50 border-b border-zinc-200/70 dark:border-white/[0.06]">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-indigo-600 to-fuchsia-500 text-sm font-bold text-white shadow-glow">
              N
            </span>
            <span className="text-[15px] font-semibold tracking-tight">Navis</span>
          </Link>
          <nav className="ml-auto flex items-center gap-2">
            {user ? (
              <Link href="/today" className={BTN_PRIMARY_SM}>
                Open Navis <ArrowRight className="size-4" />
              </Link>
            ) : (
              <>
                <Link href="/login" className="rounded-full px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-white/[0.06]">
                  Sign in
                </Link>
                <Link href="/signup" className={BTN_PRIMARY_SM}>
                  Get started
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <main className="flex-1">
        {/* Hero */}
        <section className="mx-auto max-w-6xl px-4 pb-16 pt-16 sm:px-6 sm:pt-24">
          <div className="mx-auto max-w-3xl text-center">
            <p className="mx-auto mb-5 inline-flex items-center gap-2 rounded-full border border-indigo-200/70 bg-indigo-50/70 px-3 py-1 text-xs font-medium text-indigo-700 dark:border-indigo-400/20 dark:bg-indigo-500/10 dark:text-indigo-300">
              <Globe2 className="size-3.5" /> Built for anywhere: cities, small towns and islands
            </p>
            <h1 className="text-4xl font-semibold leading-[1.05] tracking-[-0.035em] sm:text-6xl">
              Land anywhere.
              <br />
              <span className="text-gradient">Feel at home by tomorrow.</span>
            </h1>
            <p className="mx-auto mt-5 max-w-2xl text-[17px] leading-relaxed text-zinc-500 dark:text-zinc-400">
              Navis is your companion for a new place: what&apos;s happening, where to stay, how to get
              around, and what to sort out first, tailored to you.
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link href={primary.href} className={BTN_PRIMARY_LG}>
                {primary.label} <ArrowRight className="size-4" />
              </Link>
              {!user && (
                <Link href="/login" className="rounded-xl px-5 py-3 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-white/[0.06]">
                  I already have an account
                </Link>
              )}
            </div>
          </div>

          {/* Product preview */}
          <div className="mx-auto mt-14 max-w-3xl rounded-3xl border border-zinc-200/80 bg-white/80 p-4 shadow-glow backdrop-blur-sm sm:p-6 dark:border-white/[0.07] dark:bg-zinc-900/60">
            <div className="flex items-center gap-3 rounded-2xl border border-zinc-200/80 bg-white px-4 py-3 dark:border-white/[0.08] dark:bg-zinc-900">
              <Sparkles className="size-5 text-indigo-500" />
              <span className="text-[15px] text-zinc-700 dark:text-zinc-200">
                I just landed in Reykjavík. What should I do first?
              </span>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {[
                { icon: ClipboardList, t: "Get a local SIM", s: "Essentials · Do first" },
                { icon: Compass, t: "Old Harbour walk", s: "Explore · 1.2 km" },
                { icon: CalendarDays, t: "Live music tonight", s: "Events · 8:00 PM" },
              ].map(({ icon: Icon, t, s }) => (
                <div key={t} className="rounded-2xl border border-zinc-200/80 p-4 dark:border-white/[0.07]">
                  <Icon className="size-5 text-indigo-500" />
                  <p className="mt-3 text-sm font-semibold">{t}</p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">{s}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Features */}
        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 className="text-center text-3xl font-semibold tracking-[-0.02em]">Everything you need in a new place</h2>
          <p className="mx-auto mt-3 max-w-2xl text-center text-zinc-500 dark:text-zinc-400">
            One app instead of ten tabs, forum threads and guesswork.
          </p>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <div key={title} className="rounded-2xl border border-zinc-200/80 bg-white/80 p-6 shadow-soft dark:border-white/[0.07] dark:bg-zinc-900/60">
                <span className="flex size-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-300">
                  <Icon className="size-5" />
                </span>
                <h3 className="mt-4 font-semibold">{title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-zinc-500 dark:text-zinc-400">{body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 className="text-center text-3xl font-semibold tracking-[-0.02em]">How it works</h2>
          <ol className="mt-10 grid gap-4 md:grid-cols-3">
            {STEPS.map((step, i) => (
              <li key={step.title} className="rounded-2xl border border-zinc-200/80 bg-white/80 p-6 dark:border-white/[0.07] dark:bg-zinc-900/60">
                <span className="flex size-8 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-sm font-semibold text-white">
                  {i + 1}
                </span>
                <h3 className="mt-4 font-semibold">{step.title}</h3>
                <p className="mt-1.5 text-sm text-zinc-500 dark:text-zinc-400">{step.body}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* Anywhere */}
        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <div className="rounded-3xl border border-zinc-200/80 bg-gradient-to-br from-indigo-50 via-white to-fuchsia-50 p-8 text-center sm:p-12 dark:border-white/[0.07] dark:from-indigo-500/10 dark:via-zinc-900/40 dark:to-fuchsia-500/10">
            <h2 className="text-3xl font-semibold tracking-[-0.02em]">Wherever you&apos;re headed</h2>
            <p className="mx-auto mt-3 max-w-xl text-zinc-500 dark:text-zinc-400">
              Megacities, mountain towns, remote islands. Navis works from real map and event data
              worldwide and tells you honestly when local listings are thin.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-2">
              {PLACES.map((p) => (
                <span key={p} className="rounded-full border border-zinc-200/80 bg-white/80 px-4 py-1.5 text-sm text-zinc-700 dark:border-white/[0.08] dark:bg-zinc-900/60 dark:text-zinc-300">
                  {p}
                </span>
              ))}
            </div>
            <div className="mt-10 flex flex-col items-center gap-3">
              <Link href={primary.href} className={BTN_PRIMARY_LG}>
                {primary.label} <ArrowRight className="size-4" />
              </Link>
              <p className="flex items-center gap-1.5 text-xs text-zinc-500">
                <ShieldCheck className="size-3.5" /> Your preferences are private to your account. We never sell your data.
              </p>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-zinc-200/70 py-8 pb-[max(2rem,env(safe-area-inset-bottom))] text-center text-xs text-zinc-500 dark:border-white/[0.06]">
        <nav className="mb-2 flex justify-center gap-4">
          <Link href="/privacy" className="hover:text-zinc-900 dark:hover:text-zinc-100">Privacy</Link>
          <Link href="/terms" className="hover:text-zinc-900 dark:hover:text-zinc-100">Terms</Link>
          <Link href="/support" className="hover:text-zinc-900 dark:hover:text-zinc-100">Support</Link>
        </nav>
        © {new Date().getFullYear()} Navis · Map data © OpenStreetMap contributors
      </footer>
    </div>
  );
}

const BTN_PRIMARY_SM =
  "inline-flex items-center gap-1.5 rounded-full bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200";
const BTN_PRIMARY_LG =
  "inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-fuchsia-600 px-6 py-3 text-sm font-semibold text-white shadow-glow transition-opacity hover:opacity-95";

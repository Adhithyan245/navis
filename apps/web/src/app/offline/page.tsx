import type { Metadata } from "next";

export const metadata: Metadata = { title: "You're offline" };

/** Shown by the service worker when a page can't load without a connection. */
export default function OfflinePage() {
  return (
    <main className="mx-auto flex min-h-[80dvh] max-w-md flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">You&apos;re offline</h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        Navis needs a connection for live maps, events and directions. In an emergency, call the local emergency
        number directly: 112 works on mobile phones in most countries, 911 in North America.
      </p>
      <a href="/today" className="rounded-full bg-indigo-600 px-5 py-2 text-sm font-medium text-white">
        Try again
      </a>
    </main>
  );
}

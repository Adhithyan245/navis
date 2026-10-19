/** Shared shell for the public legal / support pages (no sign-in needed). */
import Link from "next/link";
import type { ReactNode } from "react";

export const SUPPORT_EMAIL = process.env.NEXT_PUBLIC_SUPPORT_EMAIL || "support@navis.app";
export const COMPANY_NAME = process.env.NEXT_PUBLIC_COMPANY_NAME || "Navis";

export function LegalPage({ title, updated, children }: { title: string; updated?: string; children: ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-16 pt-[max(1.5rem,env(safe-area-inset-top))] sm:px-6">
      <nav className="mb-8 flex items-center justify-between text-sm">
        <Link href="/" className="font-semibold text-zinc-900 dark:text-zinc-100">
          Navis
        </Link>
        <div className="flex gap-4 text-zinc-500">
          <Link href="/privacy" className="hover:text-zinc-900 dark:hover:text-zinc-100">Privacy</Link>
          <Link href="/terms" className="hover:text-zinc-900 dark:hover:text-zinc-100">Terms</Link>
          <Link href="/support" className="hover:text-zinc-900 dark:hover:text-zinc-100">Support</Link>
        </div>
      </nav>
      <h1 className="text-3xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">{title}</h1>
      {updated && <p className="mt-1 text-sm text-zinc-500">Last updated {updated}</p>}
      <div className="legal mt-8 space-y-6 text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300">{children}</div>
    </div>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">{title}</h2>
      {children}
    </section>
  );
}

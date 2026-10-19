import Link from "next/link";

/** Centered card layout for /login and /signup. */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="mx-auto flex h-16 w-full max-w-6xl items-center px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-indigo-600 to-fuchsia-500 text-sm font-bold text-white shadow-glow">
            N
          </span>
          <span className="text-[15px] font-semibold tracking-tight">Navis</span>
        </Link>
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pb-16 pt-6 sm:pt-12">
        <div className="w-full max-w-md rounded-3xl border border-zinc-200/80 bg-white/90 p-6 shadow-soft backdrop-blur-sm sm:p-8 dark:border-white/[0.07] dark:bg-zinc-900/70">
          {children}
        </div>
      </main>
    </div>
  );
}

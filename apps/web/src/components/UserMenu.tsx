"use client";
/**
 * UserMenu — avatar button with the signed-in user's name/email, quick
 * links and Sign out. Closes on outside click and Escape.
 */
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { LogOut, ShieldCheck, UserCog } from "lucide-react";

import { logoutAction } from "@/lib/auth/actions";
import { forgetPushDevice } from "@/lib/push/native";
import type { SessionUser } from "@/lib/auth/session";

function initials(user: SessionUser): string {
  const source = user.name || user.email;
  const parts = source.replace(/@.*/, "").split(/[\s._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

export function UserMenu({ user }: { user: SessionUser }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="flex size-9 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-xs font-semibold text-white outline-none ring-offset-2 focus-visible:ring-2 focus-visible:ring-indigo-400"
      >
        {user.picture ? (
          // eslint-disable-next-line @next/next/no-img-element -- Google avatar URL
          <img src={user.picture} alt="" referrerPolicy="no-referrer" className="size-full object-cover" />
        ) : (
          initials(user)
        )}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-11 z-50 w-64 overflow-hidden rounded-xl border border-zinc-200 bg-white py-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
        >
          <div className="border-b border-zinc-100 px-4 py-3 dark:border-white/[0.06]">
            {user.name && <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">{user.name}</p>}
            <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">{user.email}</p>
          </div>
          <Link
            role="menuitem"
            href="/profile"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50 dark:text-zinc-200 dark:hover:bg-white/[0.04]"
          >
            <UserCog className="size-4" /> Profile & preferences
          </Link>
          <Link
            role="menuitem"
            href="/account"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50 dark:text-zinc-200 dark:hover:bg-white/[0.04]"
          >
            <ShieldCheck className="size-4" /> Account & privacy
          </Link>
          {/* Stop this phone's notifications for the account before signing out. */}
          <form action={logoutAction} onSubmit={() => void forgetPushDevice()}>
            <button
              role="menuitem"
              type="submit"
              className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-500/10"
            >
              <LogOut className="size-4" /> Sign out
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

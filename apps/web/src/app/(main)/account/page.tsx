import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { AccountActions } from "@/components/account/AccountActions";
import { currentUser } from "@/lib/auth/server";

export const metadata: Metadata = { title: "Account & privacy" };

export default async function AccountPage() {
  const user = await currentUser();
  if (!user) redirect("/login?next=/account");
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Account &amp; privacy</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Signed in as <span className="font-medium text-zinc-700 dark:text-zinc-200">{user.email}</span>
        </p>
      </header>
      <AccountActions userId={user.id} />
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        Read our <Link href="/privacy" className="text-indigo-600 hover:underline dark:text-indigo-400">privacy policy</Link>
        {" · "}
        <Link href="/terms" className="text-indigo-600 hover:underline dark:text-indigo-400">terms</Link>
        {" · "}
        <Link href="/disclaimer" className="text-indigo-600 hover:underline dark:text-indigo-400">disclaimer</Link>
        {" · "}
        <Link href="/support" className="text-indigo-600 hover:underline dark:text-indigo-400">get help</Link>
      </p>
    </div>
  );
}

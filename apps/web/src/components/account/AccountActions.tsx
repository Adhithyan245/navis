"use client";
/**
 * Data export, sign out everywhere, and permanent account deletion (with a
 * typed confirmation). Deleting also clears this device's copy of the
 * account's local data.
 */
import { useState } from "react";
import { Download, LogOut, Trash2 } from "lucide-react";

import { NotificationSettings } from "@/components/account/NotificationSettings";
import { Button } from "@/components/ui/button";
import { SYNCED_KEYS } from "@/lib/account/scope";
import { forgetPushDevice } from "@/lib/push/native";
import { clearApiToken } from "@/lib/runtime/apiToken";

function clearLocalData(userId: string) {
  try {
    for (const base of [...Object.values(SYNCED_KEYS), "navis_onboarding_dismissed_v1"]) {
      window.localStorage.removeItem(`${base}:${userId}`);
    }
  } catch {
    /* storage disabled */
  }
}

function Card({ title, body, children, danger }: { title: string; body: string; children: React.ReactNode; danger?: boolean }) {
  return (
    <section
      className={
        danger
          ? "rounded-2xl border border-rose-200 bg-rose-50/60 p-5 dark:border-rose-500/20 dark:bg-rose-500/[0.06]"
          : "rounded-2xl border border-zinc-200/80 bg-white/90 p-5 dark:border-white/[0.07] dark:bg-zinc-900/70"
      }
    >
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{title}</h2>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{body}</p>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function AccountActions({ userId }: { userId: string }) {
  const [status, setStatus] = useState<string | null>(null);
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState<"signout" | "delete" | null>(null);

  const signOutEverywhere = async () => {
    setBusy("signout");
    setStatus(null);
    try {
      const res = await fetch("/api/account/sign-out-everywhere", { method: "POST" });
      setStatus(res.ok ? "Signed out on every other device." : "That didn't work. Please try again.");
    } catch {
      setStatus("That didn't work. Please try again.");
    } finally {
      setBusy(null);
    }
  };

  const deleteAccount = async () => {
    setBusy("delete");
    setStatus(null);
    try {
      const res = await fetch("/api/account", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { error?: string };
        setStatus(data.error ?? "We couldn't delete your account right now.");
        setBusy(null);
        return;
      }
      await forgetPushDevice();
      clearLocalData(userId);
      clearApiToken();
      window.location.assign("/?deleted=1");
    } catch {
      setStatus("We couldn't delete your account right now.");
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <NotificationSettings />

      <Card title="Download your data" body="A JSON file with your account details, profile, saved items and checklist.">
        <Button variant="outline" size="sm" nativeButton={false} render={<a href="/api/account/export" download />}>
          <Download /> Download my data
        </Button>
      </Card>

      <Card title="Sign out everywhere" body="Ends your sessions on all other phones and browsers. You'll stay signed in here.">
        <Button variant="outline" size="sm" onClick={() => void signOutEverywhere()} disabled={busy !== null}>
          <LogOut /> {busy === "signout" ? "Signing out…" : "Sign out everywhere"}
        </Button>
      </Card>

      <Card
        danger
        title="Delete account"
        body="Permanently deletes your account and everything synced to it. This can't be undone."
      >
        <label className="block text-sm text-zinc-700 dark:text-zinc-300">
          Type <span className="font-mono font-semibold">DELETE</span> to confirm
          <input
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="off"
            className="mt-1.5 block w-full max-w-xs rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-zinc-950"
          />
        </label>
        <Button
          className="mt-3 bg-rose-600 text-white hover:bg-rose-700"
          size="sm"
          disabled={confirm !== "DELETE" || busy !== null}
          onClick={() => void deleteAccount()}
        >
          <Trash2 /> {busy === "delete" ? "Deleting…" : "Delete my account"}
        </Button>
      </Card>

      {status && (
        <p role="status" className="text-sm text-zinc-600 dark:text-zinc-300">
          {status}
        </p>
      )}
    </div>
  );
}

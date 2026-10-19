"use client";
/**
 * Notifications card on Account & privacy. In the native app: turn
 * notifications on for this phone, pick which kinds, send a test. On the
 * web: explains they're available in the app.
 */
import { useEffect, useState, useSyncExternalStore } from "react";
import { Bell, BellRing } from "lucide-react";

import { Button } from "@/components/ui/button";
import { enablePush, pushSupported } from "@/lib/push/native";

interface Prefs {
  safety_alerts: boolean;
  event_reminders: boolean;
  devices: number;
}

const KINDS: Array<{ key: "safety_alerts" | "event_reminders"; label: string; hint: string }> = [
  { key: "safety_alerts", label: "Safety alerts", hint: "Severe weather, disasters and strong earthquakes near your city" },
  { key: "event_reminders", label: "Event reminders", hint: "A heads-up the day before events you've saved" },
];

const noopSubscribe = () => () => undefined;

export function NotificationSettings() {
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [available, setAvailable] = useState<Record<string, boolean>>({});
  // Server render (and the web) say false; inside the app the client says true.
  const native = useSyncExternalStore(noopSubscribe, pushSupported, () => false);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/push/prefs", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { prefs?: Prefs; available?: Record<string, boolean> } | null) => {
        if (cancelled) return;
        if (d?.prefs) setPrefs(d.prefs);
        if (d?.available) setAvailable(d.available);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const turnOn = async () => {
    setBusy(true);
    setStatus(null);
    const result = await enablePush();
    setBusy(false);
    if (result === "enabled") {
      setStatus("Notifications are on for this phone.");
      setPrefs((p) => (p ? { ...p, devices: Math.max(1, p.devices) } : { safety_alerts: true, event_reminders: true, devices: 1 }));
    } else if (result === "unsupported") {
      setStatus("Notifications aren't available yet. They'll switch on in an app update.");
    } else if (result === "denied") {
      setStatus("Notifications are blocked. Allow them for Navis in your phone's Settings, then try again.");
    } else {
      setStatus("We couldn't turn on notifications right now. Please try again.");
    }
  };

  const toggle = async (key: "safety_alerts" | "event_reminders", value: boolean) => {
    if (!prefs) return;
    setPrefs({ ...prefs, [key]: value });
    const res = await fetch("/api/push/prefs", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [key]: value }),
    }).catch(() => null);
    if (res?.ok) setPrefs(((await res.json()) as { prefs: Prefs }).prefs);
    else {
      setPrefs({ ...prefs, [key]: !value });
      setStatus("That setting didn't save. Please try again.");
    }
  };

  const sendTest = async () => {
    setStatus(null);
    const res = await fetch("/api/push/test", { method: "POST" }).catch(() => null);
    const sent = res?.ok ? ((await res.json()) as { result?: { sent?: number } }).result?.sent ?? 0 : 0;
    setStatus(sent > 0 ? "Test sent. It should arrive in a few seconds." : "No test was delivered; check that notifications are allowed.");
  };

  const hasDevice = (prefs?.devices ?? 0) > 0;

  return (
    <section className="rounded-2xl border border-zinc-200/80 bg-white/90 p-5 dark:border-white/[0.07] dark:bg-zinc-900/70">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        <Bell className="size-4" aria-hidden /> Notifications
      </h2>
      {!native && !hasDevice ? (
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Get safety alerts for your city and reminders for saved events in the Navis app for Android and iPhone.
        </p>
      ) : (
        <>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {hasDevice
              ? `On for ${prefs?.devices === 1 ? "1 device" : `${prefs?.devices} devices`}. Choose what you get:`
              : "Turn on notifications to get safety alerts and event reminders on this phone."}
          </p>
          {native && !hasDevice && !Object.values(available).some(Boolean) && (
            <p className="mt-2 text-xs text-zinc-500">Coming soon to this app.</p>
          )}
          {native && !hasDevice && Object.values(available).some(Boolean) && (
            <Button size="sm" className="mt-3" onClick={() => void turnOn()} disabled={busy}>
              <BellRing /> {busy ? "Turning on…" : "Turn on notifications"}
            </Button>
          )}
          {hasDevice && prefs && (
            <div className="mt-3 space-y-3">
              {KINDS.map((k) => (
                <label key={k.key} className="flex cursor-pointer items-start justify-between gap-4">
                  <span>
                    <span className="block text-sm font-medium text-zinc-800 dark:text-zinc-100">{k.label}</span>
                    <span className="block text-xs text-zinc-500">{k.hint}</span>
                  </span>
                  <input
                    type="checkbox"
                    role="switch"
                    checked={prefs[k.key]}
                    onChange={(e) => void toggle(k.key, e.target.checked)}
                    className="mt-1 size-5 shrink-0 accent-indigo-600"
                  />
                </label>
              ))}
              <Button variant="outline" size="sm" onClick={() => void sendTest()}>
                Send a test notification
              </Button>
            </div>
          )}
        </>
      )}
      {status && (
        <p role="status" className="mt-3 text-sm text-zinc-600 dark:text-zinc-300">
          {status}
        </p>
      )}
    </section>
  );
}

/**
 * Two-way sync between this device's localStorage (per-account scoped) and
 * the account's server copy at /api/me/data.
 *
 *   1. Pull on sign-in. A section the server has replaces the local copy;
 *      a section only this device has (first sign-in, migrated pre-account
 *      data) is uploaded.
 *   2. Push local changes as they happen (debounced), and flush on page hide.
 *
 * The stores keep reading/writing localStorage exactly as before; they only
 * learn about pulled data through their usual change events.
 */
import { SYNCED_KEYS, scopedKey } from "./scope";

type Section = keyof typeof SYNCED_KEYS;
const SECTIONS = Object.keys(SYNCED_KEYS) as Section[];

// Same event names the stores' contexts listen to.
const EVENTS: Record<Section, string> = {
  profile: "navis:profile-changed",
  saved: "navis:saved-changed",
  checklist: "navis:checklist-changed",
};

const PUSH_DEBOUNCE_MS = 800;
const ENDPOINT = "/api/me/data";

function readRaw(section: Section): string | null {
  try {
    return window.localStorage.getItem(scopedKey(SYNCED_KEYS[section]));
  } catch {
    return null;
  }
}

function writeRaw(section: Section, value: unknown): void {
  try {
    const key = scopedKey(SYNCED_KEYS[section]);
    if (value === null || value === undefined) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage disabled */
  }
}

function parse(raw: string | null): unknown {
  if (raw === null) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/** Starts syncing for the signed-in account. Returns a cleanup function. */
export function startAccountSync(): () => void {
  let pulled = false;
  let applying = false;
  let stopped = false;
  const dirty = new Set<Section>();
  let timer: ReturnType<typeof setTimeout> | null = null;

  const push = async (sections: Section[], keepalive = false) => {
    if (sections.length === 0) return;
    const body: Record<string, unknown> = {};
    for (const s of sections) body[s] = parse(readRaw(s));
    try {
      await fetch(ENDPOINT, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        keepalive,
      });
    } catch {
      // Offline: put them back so the next change or page hide retries.
      sections.forEach((s) => dirty.add(s));
    }
  };

  const flush = (keepalive = false) => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    if (!pulled || dirty.size === 0) return;
    const sections = [...dirty];
    dirty.clear();
    void push(sections, keepalive);
  };

  const listeners = SECTIONS.map((section) => {
    const onChange = () => {
      if (applying || stopped) return;
      dirty.add(section);
      if (!pulled) return; // pushed once the initial pull settles
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => flush(), PUSH_DEBOUNCE_MS);
    };
    window.addEventListener(EVENTS[section], onChange);
    return () => window.removeEventListener(EVENTS[section], onChange);
  });

  const onHide = () => flush(true);
  window.addEventListener("pagehide", onHide);

  void (async () => {
    let server: Record<string, unknown> | null = null;
    try {
      const res = await fetch(ENDPOINT, { cache: "no-store" });
      if (res.ok) server = ((await res.json()) as { data?: Record<string, unknown> }).data ?? null;
    } catch {
      server = null;
    }
    if (stopped) return;
    if (server) {
      const upload: Section[] = [];
      for (const section of SECTIONS) {
        if (dirty.has(section)) continue; // edited during the pull: local wins
        const remote = server[section];
        const localRaw = readRaw(section);
        if (remote !== null && remote !== undefined) {
          if (JSON.stringify(remote) !== localRaw) {
            applying = true;
            writeRaw(section, remote);
            window.dispatchEvent(new CustomEvent(EVENTS[section]));
            applying = false;
          }
        } else if (localRaw !== null) {
          upload.push(section);
        }
      }
      upload.forEach((s) => dirty.add(s));
    }
    // If the pull failed (offline), keep working locally; changes stay
    // dirty and go up with the next successful push.
    pulled = server !== null;
    flush();
  })();

  return () => {
    stopped = true;
    flush(true);
    listeners.forEach((off) => off());
    window.removeEventListener("pagehide", onHide);
  };
}

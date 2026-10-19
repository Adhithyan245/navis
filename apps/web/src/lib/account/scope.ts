/**
 * Per-account localStorage scoping.
 *
 * The profile / saved / checklist stores keep using localStorage as their
 * fast, offline copy, but under keys suffixed with the signed-in account id
 * ("navis_user_profile_v1:u_abc…"), so two accounts on one browser never
 * see each other's data. The server copy (lib/account/sync.ts) is the
 * source of truth across devices.
 *
 * `setStorageScope` runs during render of <AccountScope>, before any store
 * reads, so the first snapshot is already the right account's.
 */

let scope: string | null = null;

/** Base keys of the synced stores (also used to migrate pre-account data). */
export const SYNCED_KEYS = {
  profile: "navis_user_profile_v1",
  saved: "navis_saved_items_v1",
  checklist: "navis_checklist_v1",
} as const;

export function setStorageScope(userId: string | null): void {
  if (userId === scope) return;
  scope = userId;
  if (userId) claimLegacyData(userId);
}

export function storageScope(): string | null {
  return scope;
}

/** The localStorage key for `base` in the current account's scope. */
export function scopedKey(base: string): string {
  return scope ? `${base}:${scope}` : base;
}

/**
 * Data saved before accounts existed lives under the bare keys. The first
 * account to sign in on this browser adopts it (once), so nobody loses
 * their profile; later accounts start clean.
 */
function claimLegacyData(userId: string): void {
  if (typeof window === "undefined") return;
  try {
    const ls = window.localStorage;
    for (const base of [...Object.values(SYNCED_KEYS), "navis_onboarding_dismissed_v1"]) {
      const legacy = ls.getItem(base);
      if (legacy === null) continue;
      const scoped = `${base}:${userId}`;
      if (ls.getItem(scoped) === null) ls.setItem(scoped, legacy);
      ls.removeItem(base);
    }
  } catch {
    /* storage disabled — nothing to migrate */
  }
}

"use client";
/**
 * /profile — view, edit, and reset the persisted UserProfile.
 *
 * Reads the same ProfileContext the wizard writes to. When no profile
 * exists, shows an empty state with a CTA that resurrects the wizard
 * via restoreOnboarding().
 */
import { useState } from "react";
import { RotateCcw, Save, UserCog } from "lucide-react";

import { LocationSearch } from "@/components/runtime/LocationSearch";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useProfileContext } from "@/lib/profile/context";
import {
  BUDGET_BAND_OPTIONS,
  EMPTY_PROFILE,
  GOAL_OPTIONS,
  HOUSEHOLD_OPTIONS,
  INTEREST_OPTIONS,
  MOVE_STAGES,
  WORK_STYLE_OPTIONS,
  type MoveStage,
  type UserProfile,
} from "@/lib/profile/schema";
import { cn } from "@/lib/utils";

export default function ProfilePage() {
  const { ready, profile, setProfile, clearProfile, restoreOnboarding } =
    useProfileContext();
  // Re-seed the editable draft whenever the source profile changes (e.g.
  // hydration finishes, or another tab updates storage). Set-during-render
  // is React's canonical "derive state from props" pattern; using useEffect
  // here would trigger an extra render cycle.
  const [draft, setDraft] = useState<UserProfile>(profile ?? EMPTY_PROFILE);
  const [seedProfile, setSeedProfile] = useState<UserProfile | null>(profile);
  if (profile !== seedProfile) {
    setSeedProfile(profile);
    if (profile) setDraft(profile);
  }
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // Stable empty render during SSR + first paint — avoids hydration mismatch.
  if (!ready) {
    return (
      <div className="py-12 text-sm text-zinc-500 dark:text-zinc-400">
        Loading your profile…
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center justify-center gap-6 py-16 text-center">
        <div className="flex size-12 items-center justify-center rounded-full bg-indigo-50 dark:bg-indigo-950/40">
          <UserCog className="size-6 text-indigo-500" />
        </div>
        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            Set up your Navis profile
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Tell Navis a bit about your move and we&apos;ll tailor results for you.
            Saved to your account, so it follows you to any device you sign in on.
          </p>
        </div>
        <Button onClick={restoreOnboarding}>Set up profile</Button>
      </div>
    );
  }

  const toggleMulti = (key: "interests" | "goals", v: string) =>
    setDraft((d) => ({
      ...d,
      [key]: d[key].includes(v) ? d[key].filter((x) => x !== v) : [...d[key], v],
    }));

  const save = () => {
    setProfile(draft);
    setSavedAt(Date.now());
  };

  const reset = () => {
    if (typeof window !== "undefined") {
      const ok = window.confirm(
        "Reset your profile? This clears your saved answers on every device."
      );
      if (!ok) return;
    }
    clearProfile();
    setDraft(EMPTY_PROFILE);
    setSavedAt(null);
  };

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 py-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
            Your profile
          </h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Saved to your account and synced across your devices. Used to tailor every Navis query.
          </p>
        </div>
        {savedAt !== null && (
          <span className="text-xs text-emerald-600 dark:text-emerald-400">
            Saved
          </span>
        )}
      </header>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">City</CardTitle>
        </CardHeader>
        <CardContent>
          <LocationSearch
            value={draft.city}
            placeholder="e.g. Boston"
            onSelect={(loc) =>
              setDraft({
                ...draft,
                city: loc.city || loc.name || loc.label,
                cityLocation: loc,
              })
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Home area / neighborhood</CardTitle>
        </CardHeader>
        <CardContent>
          <LocationSearch
            value={draft.homeArea}
            near={draft.cityLocation}
            placeholder="e.g. Cambridge, Allston, Adyar, Velachery"
            onSelect={(loc) =>
              setDraft({
                ...draft,
                homeArea: loc.name || loc.label,
                homeAreaLocation: loc,
              })
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Move stage</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {MOVE_STAGES.map((s) => (
            <button
              key={s.value}
              type="button"
              onClick={() => setDraft({ ...draft, moveStage: s.value as MoveStage })}
              className={cn(
                "w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors",
                draft.moveStage === s.value
                  ? "border-indigo-300 bg-indigo-50 dark:border-indigo-500/40 dark:bg-indigo-950/30"
                  : "border-zinc-200 bg-white hover:border-indigo-200 dark:border-zinc-700 dark:bg-zinc-900"
              )}
            >
              <div className="font-medium text-zinc-900 dark:text-zinc-100">{s.label}</div>
              <div className="text-xs text-zinc-500 dark:text-zinc-400">{s.hint}</div>
            </button>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Household</CardTitle>
        </CardHeader>
        <CardContent>
          <ChipRow
            options={HOUSEHOLD_OPTIONS}
            value={draft.household}
            onChange={(household) => setDraft({ ...draft, household })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Work style</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ChipRow
            options={WORK_STYLE_OPTIONS}
            value={draft.workStyle}
            onChange={(workStyle) => setDraft({ ...draft, workStyle })}
          />
          <LocationSearch
            near={draft.cityLocation}
            placeholder="Office area / address (optional)"
            value={draft.officeLocation ?? ""}
            onSelect={(loc) =>
              setDraft({
                ...draft,
                officeLocation: loc.label,
                officeLocationResolved: loc,
              })
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Budget band</CardTitle>
        </CardHeader>
        <CardContent>
          <ChipRow
            options={BUDGET_BAND_OPTIONS}
            value={draft.budgetBand}
            onChange={(budgetBand) => setDraft({ ...draft, budgetBand })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Goals</CardTitle>
        </CardHeader>
        <CardContent>
          <MultiChipRow
            options={GOAL_OPTIONS}
            values={draft.goals}
            onToggle={(v) => toggleMulti("goals", v)}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Interests</CardTitle>
        </CardHeader>
        <CardContent>
          <MultiChipRow
            options={INTEREST_OPTIONS}
            values={draft.interests}
            onToggle={(v) => toggleMulti("interests", v)}
          />
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        <Button variant="destructive" size="sm" onClick={reset}>
          <RotateCcw />
          Reset profile
        </Button>
        <Button variant="default" size="sm" onClick={save}>
          <Save />
          Save changes
        </Button>
      </div>
    </div>
  );
}

function ChipRow({
  options,
  value,
  onChange,
}: {
  options: readonly string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => onChange(opt)}
          className={cn(
            "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
            value === opt
              ? "border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-500/40 dark:bg-indigo-950/40 dark:text-indigo-300"
              : "border-zinc-200 bg-white text-zinc-700 hover:border-indigo-200 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
          )}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

function MultiChipRow({
  options,
  values,
  onToggle,
}: {
  options: readonly string[];
  values: string[];
  onToggle: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((opt) => {
        const active = values.includes(opt);
        return (
          <button
            key={opt}
            type="button"
            onClick={() => onToggle(opt)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
              active
                ? "border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-500/40 dark:bg-indigo-950/40 dark:text-indigo-300"
                : "border-zinc-200 bg-white text-zinc-700 hover:border-indigo-200 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
            )}
          >
            {opt}
          </button>
        );
      })}
    </div>
  );
}

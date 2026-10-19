"use client";
/**
 * OnboardingWizard — first-visit modal that captures the UserProfile.
 *
 * Lifecycle:
 *   * Rendered conditionally by OnboardingGate when no profile exists
 *     and onboarding has not been dismissed.
 *   * Each step has Back / Skip / Next; the last has Finish.
 *   * The header X dismisses entirely (sets onboarding_dismissed=true).
 *   * Finish persists the draft profile; skip-step records the field's
 *     default and proceeds.
 *
 * Steps (8 — per the modification spec):
 *   1. City
 *   2. Home area / neighborhood
 *   3. Move stage
 *   4. Household
 *   5. Work style (+ optional office location)
 *   6. Budget band
 *   7. Goals
 *   8. Interests
 *
 * Mobile-friendly: max-width modal, full-width inputs, large tap targets.
 */
import { useState } from "react";
import { Check, ChevronLeft, ChevronRight, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { LocationSearch } from "@/components/runtime/LocationSearch";
import type { Location } from "@/lib/runtime/location";
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

const STEP_COUNT = 8;

export function OnboardingWizard() {
  const { setProfile, dismissOnboarding } = useProfileContext();
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<UserProfile>(EMPTY_PROFILE);

  const back = () => setStep((s) => Math.max(0, s - 1));
  const next = () => setStep((s) => Math.min(STEP_COUNT - 1, s + 1));
  const skip = () => next();
  const finish = () => setProfile(draft);
  const close = () => dismissOnboarding();

  const toggleMulti = (key: "interests" | "goals", v: string) =>
    setDraft((d) => ({
      ...d,
      [key]: d[key].includes(v) ? d[key].filter((x) => x !== v) : [...d[key], v],
    }));

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Set up your Navis profile"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-zinc-950/50 px-4 py-6 backdrop-blur-md animate-in fade-in duration-300"
    >
      <div className="w-full max-w-md overflow-hidden rounded-3xl border border-zinc-200/80 bg-white shadow-2xl shadow-indigo-500/10 dark:border-white/[0.08] dark:bg-zinc-900 animate-in zoom-in-95 slide-in-from-bottom-2 duration-300">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-100 px-5 py-3 dark:border-zinc-800">
          <div>
            <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Step {step + 1} of {STEP_COUNT}
            </p>
            <h2 className="mt-0.5 text-base font-semibold text-zinc-900 dark:text-zinc-100">
              Tell us about your move
            </h2>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Skip onboarding"
            className="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Progress */}
        <div className="h-1 w-full bg-zinc-100 dark:bg-zinc-800">
          <div
            className="h-full rounded-r-full bg-gradient-to-r from-indigo-500 to-fuchsia-500 transition-all duration-500"
            style={{ width: `${((step + 1) / STEP_COUNT) * 100}%` }}
          />
        </div>

        {/* Step body */}
        <div className="min-h-[200px] px-5 py-6">
          {step === 0 && (
            <StepLocation
              label="Which city are you moving to (or have moved to)?"
              placeholder="e.g. Boston, Berlin, Bangalore"
              value={draft.city}
              onSelect={(loc) =>
                setDraft({
                  ...draft,
                  city: loc.city || loc.name || loc.label,
                  cityLocation: loc,
                })
              }
            />
          )}
          {step === 1 && (
            <StepLocation
              near={draft.cityLocation}
              label="What area or neighborhood are you living in (or considering)?"
              placeholder="e.g. Cambridge, Allston, Adyar, Velachery"
              value={draft.homeArea}
              onSelect={(loc) =>
                setDraft({
                  ...draft,
                  homeArea: loc.name || loc.label,
                  homeAreaLocation: loc,
                })
              }
            />
          )}
          {step === 2 && (
            <StepStage
              value={draft.moveStage}
              onChange={(moveStage) => setDraft({ ...draft, moveStage })}
            />
          )}
          {step === 3 && (
            <StepChips
              label="Who's moving with you?"
              options={HOUSEHOLD_OPTIONS}
              value={draft.household}
              onChange={(household) => setDraft({ ...draft, household })}
            />
          )}
          {step === 4 && (
            <StepChips
              label="How do you work?"
              options={WORK_STYLE_OPTIONS}
              value={draft.workStyle}
              onChange={(workStyle) => setDraft({ ...draft, workStyle })}
              extra={
                <div className="mt-3">
                  <LocationSearch
                    near={draft.cityLocation}
                    placeholder="Office area or address (optional)"
                    value={draft.officeLocation ?? ""}
                    onSelect={(loc) =>
                      setDraft({
                        ...draft,
                        officeLocation: loc.label,
                        officeLocationResolved: loc,
                      })
                    }
                  />
                </div>
              }
            />
          )}
          {step === 5 && (
            <StepChips
              label="What's your budget band?"
              options={BUDGET_BAND_OPTIONS}
              value={draft.budgetBand}
              onChange={(budgetBand) => setDraft({ ...draft, budgetBand })}
            />
          )}
          {step === 6 && (
            <StepMultiChips
              label="What are you trying to get done?"
              hint="Pick any. We'll prioritize accordingly."
              options={GOAL_OPTIONS}
              values={draft.goals}
              onToggle={(v) => toggleMulti("goals", v)}
            />
          )}
          {step === 7 && (
            <StepMultiChips
              label="What are you into?"
              hint="Pick any."
              options={INTEREST_OPTIONS}
              values={draft.interests}
              onToggle={(v) => toggleMulti("interests", v)}
            />
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-zinc-100 px-5 py-3 dark:border-zinc-800">
          <Button variant="ghost" size="sm" onClick={back} disabled={step === 0}>
            <ChevronLeft />
            Back
          </Button>
          <div className="flex items-center gap-2">
            {step < STEP_COUNT - 1 ? (
              <>
                <Button variant="ghost" size="sm" onClick={skip}>
                  Skip
                </Button>
                <Button variant="default" size="sm" onClick={next}>
                  Next
                  <ChevronRight />
                </Button>
              </>
            ) : (
              <Button variant="default" size="sm" onClick={finish}>
                <Check />
                Finish
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Step subcomponents ─────────────────────────────────────────────────────

function StepLocation({
  label,
  placeholder,
  value,
  onSelect,
  near,
}: {
  label: string;
  placeholder: string;
  value: string;
  onSelect: (loc: Location) => void;
  near?: Location | null;
}) {
  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
        {label}
      </label>
      <LocationSearch
        autoFocus
        placeholder={placeholder}
        value={value}
        onSelect={onSelect}
        near={near}
      />
    </div>
  );
}

function StepStage({
  value,
  onChange,
}: {
  value: MoveStage;
  onChange: (v: MoveStage) => void;
}) {
  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
        Where are you in the move?
      </label>
      <div className="space-y-2">
        {MOVE_STAGES.map((s) => (
          <button
            key={s.value}
            type="button"
            onClick={() => onChange(s.value)}
            className={cn(
              "w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors",
              value === s.value
                ? "border-indigo-300 bg-indigo-50 text-zinc-900 dark:border-indigo-500/40 dark:bg-indigo-950/30 dark:text-zinc-100"
                : "border-zinc-200 bg-white text-zinc-700 hover:border-indigo-200 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
            )}
          >
            <div className="font-medium">{s.label}</div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400">{s.hint}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

function StepChips({
  label,
  options,
  value,
  onChange,
  extra,
}: {
  label: string;
  options: readonly string[];
  value: string;
  onChange: (v: string) => void;
  extra?: React.ReactNode;
}) {
  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
        {label}
      </label>
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
      {extra}
    </div>
  );
}

function StepMultiChips({
  label,
  hint,
  options,
  values,
  onToggle,
}: {
  label: string;
  hint?: string;
  options: readonly string[];
  values: string[];
  onToggle: (v: string) => void;
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {label}
        </label>
        {hint && (
          <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{hint}</p>
        )}
      </div>
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
    </div>
  );
}

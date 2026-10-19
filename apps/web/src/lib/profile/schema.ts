/**
 * UserProfile schema — the canonical product-layer representation of a
 * relocation user. Persisted in localStorage; injected into every
 * /v2/query request as `user_context`.
 *
 * Schema is versioned via the storage key (`navis_user_profile_v1`).
 * When fields change incompatibly, bump the key version in storage.ts.
 */

import type { Location } from "@/lib/runtime/location";

export type MoveStage =
  | "exploring"
  | "pre_arrival"
  | "week_1"
  | "month_1"
  | "settled";

export interface UserProfile {
  city: string;
  homeArea: string;
  moveStage: MoveStage;
  household: string;
  workStyle: string;
  officeLocation?: string;
  budgetBand: string;
  interests: string[];
  goals: string[];
  // Resolved canonical Location snapshots (Phase 3A). Optional + additive:
  // the display strings above remain the source of truth for workflows; these
  // carry coordinates/admin hierarchy for any geospatial consumer. Older
  // profiles without them rehydrate with these left undefined.
  cityLocation?: Location | null;
  homeAreaLocation?: Location | null;
  officeLocationResolved?: Location | null;
}

export const MOVE_STAGES: ReadonlyArray<{
  value: MoveStage;
  label: string;
  hint: string;
}> = [
  { value: "exploring",   label: "Just exploring",  hint: "Considering a move, no date yet" },
  { value: "pre_arrival", label: "Pre-arrival",     hint: "Moving soon — researching the city" },
  { value: "week_1",      label: "First week",      hint: "Just arrived, getting oriented" },
  { value: "month_1",     label: "First month",     hint: "Sorting essentials, starting to explore" },
  { value: "settled",     label: "Settled",         hint: "Lived here a while, still discovering" },
];

export const HOUSEHOLD_OPTIONS = [
  "Solo",
  "Couple",
  "Family with kids",
  "Roommates",
] as const;

export const WORK_STYLE_OPTIONS = [
  "Remote",
  "Hybrid",
  "Office",
  "Freelance",
  "Between jobs",
  "Student",
] as const;

export const BUDGET_BAND_OPTIONS = [
  "Budget-conscious",
  "Moderate",
  "Comfortable",
  "Premium",
] as const;

export const INTEREST_OPTIONS = [
  "Food",
  "Coffee",
  "Music",
  "Tech",
  "Fitness",
  "Outdoors",
  "Art",
  "Nightlife",
  "Family",
  "Reading",
  "Language exchange",
  "Volunteering",
] as const;

export const GOAL_OPTIONS = [
  "Find housing",
  "Meet people",
  "Build professional network",
  "Explore the city",
  "Find workspaces",
  "Family activities",
  "Get settled quickly",
] as const;

export const EMPTY_PROFILE: UserProfile = {
  city: "",
  homeArea: "",
  moveStage: "exploring",
  household: "",
  workStyle: "",
  budgetBand: "",
  interests: [],
  goals: [],
};

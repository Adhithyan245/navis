"use client";
/**
 * AuthForm — email/password sign-in or sign-up, plus "Continue with Apple / Google".
 * Submits to the server actions in lib/auth/actions.ts via useActionState.
 */
import { useActionState, useState } from "react";
import Link from "next/link";
import { Eye, EyeOff, Loader2 } from "lucide-react";

import { SocialSignIn } from "@/components/auth/SocialSignIn";
import { loginAction, signupAction, type AuthFormState } from "@/lib/auth/actions";

const INITIAL: AuthFormState = { error: null, email: "", name: "" };

export function AuthForm({
  mode,
  next,
  googleEnabled,
  appleEnabled = false,
  notice,
}: {
  mode: "login" | "signup";
  next: string;
  googleEnabled: boolean;
  appleEnabled?: boolean;
  notice: string | null;
}) {
  const [state, formAction, pending] = useActionState(mode === "login" ? loginAction : signupAction, INITIAL);
  const [showPassword, setShowPassword] = useState(false);
  const isSignup = mode === "signup";
  const error = state.error ?? notice;

  return (
    <div className="flex flex-col gap-5">
      <SocialSignIn next={next} googleEnabled={googleEnabled} appleEnabled={appleEnabled} />

      <div className="flex items-center gap-3 text-xs text-zinc-400">
        <span className="h-px flex-1 bg-zinc-200 dark:bg-white/10" />
        or with email
        <span className="h-px flex-1 bg-zinc-200 dark:bg-white/10" />
      </div>

      <form action={formAction} className="flex flex-col gap-4" noValidate>
        <input type="hidden" name="next" value={next} />
        {isSignup && (
          <Field label="Name" htmlFor="name">
            <input
              id="name"
              name="name"
              autoComplete="name"
              defaultValue={state.name}
              maxLength={80}
              placeholder="What should we call you?"
              className={INPUT}
            />
          </Field>
        )}
        <Field label="Email" htmlFor="email">
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            defaultValue={state.email}
            maxLength={320}
            placeholder="you@example.com"
            className={INPUT}
          />
        </Field>
        <Field
          label="Password"
          htmlFor="password"
          hint={isSignup ? "At least 8 characters, not just numbers." : undefined}
        >
          <div className="relative">
            <input
              id="password"
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete={isSignup ? "new-password" : "current-password"}
              required
              minLength={isSignup ? 8 : undefined}
              maxLength={256}
              className={`${INPUT} pr-11`}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
            >
              {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </Field>

        {error && (
          <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={pending}
          className="flex h-11 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-fuchsia-600 text-sm font-semibold text-white shadow-glow transition-opacity hover:opacity-95 disabled:opacity-60"
        >
          {pending && <Loader2 className="size-4 animate-spin" />}
          {isSignup ? "Create account" : "Sign in"}
        </button>
      </form>

      <p className="text-center text-sm text-zinc-500 dark:text-zinc-400">
        {isSignup ? "Already have an account? " : "New to Navis? "}
        <Link
          href={`${isSignup ? "/login" : "/signup"}${next !== "/today" ? `?next=${encodeURIComponent(next)}` : ""}`}
          className="font-medium text-indigo-600 hover:underline dark:text-indigo-400"
        >
          {isSignup ? "Sign in" : "Create an account"}
        </Link>
      </p>
    </div>
  );
}

const INPUT =
  "h-11 w-full rounded-xl border border-zinc-200 bg-white px-3.5 text-sm outline-none placeholder:text-zinc-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-500/10 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-zinc-400">{hint}</p>}
    </div>
  );
}

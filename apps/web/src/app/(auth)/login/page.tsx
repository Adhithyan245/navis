import { AuthForm } from "@/components/auth/AuthForm";
import { appleConfigured } from "@/lib/auth/apple";
import { googleConfigured } from "@/lib/auth/google";
import { safeNext } from "@/lib/auth/session";

export const metadata = { title: "Sign in" };

const ERRORS: Record<string, string> = {
  google_unavailable: "Google sign-in isn't set up on this server yet. Use email for now.",
  google_cancelled: "Google sign-in was cancelled.",
  google_state: "That sign-in link expired. Please try again.",
  google_failed: "We couldn't sign you in with Google. Please try again.",
  google_unverified: "Your Google email isn't verified, so we can't link it to your existing account.",
  apple_unavailable: "Sign in with Apple isn't set up on this server yet. Use email for now.",
  apple_cancelled: "Sign in with Apple was cancelled.",
  apple_state: "That sign-in link expired. Please try again.",
  apple_failed: "We couldn't sign you in with Apple. Please try again.",
  apple_unverified: "Your Apple email isn't verified, so we can't link it to your existing account.",
  handoff_failed: "That sign-in took too long to finish. Please try again.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const next = safeNext(typeof params.next === "string" ? params.next : null);
  const error = typeof params.error === "string" ? ERRORS[params.error] ?? null : null;

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Welcome back</h1>
      <p className="mb-6 mt-1 text-sm text-zinc-500 dark:text-zinc-400">
        Sign in to pick up where you left off.
      </p>
      <AuthForm mode="login" next={next} googleEnabled={googleConfigured()} appleEnabled={appleConfigured()} notice={error} />
    </>
  );
}

import { AuthForm } from "@/components/auth/AuthForm";
import { appleConfigured } from "@/lib/auth/apple";
import { googleConfigured } from "@/lib/auth/google";
import { safeNext } from "@/lib/auth/session";

export const metadata = { title: "Create your account · Navis" };

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const next = safeNext(typeof params.next === "string" ? params.next : null);

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
        Create your Navis account
      </h1>
      <p className="mb-6 mt-1 text-sm text-zinc-500 dark:text-zinc-400">
        Free. Your guide to any place you land, from big cities to small islands.
      </p>
      <AuthForm mode="signup" next={next} googleEnabled={googleConfigured()} appleEnabled={appleConfigured()} notice={null} />
    </>
  );
}

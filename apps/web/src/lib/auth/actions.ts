"use server";
/**
 * Server actions for the sign-in / sign-up forms and sign-out.
 * On success they set the signed session cookie and redirect.
 */
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AuthBackendError, authBackend } from "@/lib/auth/backend";
import { clientIp } from "@/lib/auth/server";
import { SESSION_COOKIE, encodeSession, safeNext, sessionCookieOptions } from "@/lib/auth/session";

export interface AuthFormState {
  error: string | null;
  email: string;
  name: string;
}

function field(formData: FormData, key: string, max: number): string {
  const v = formData.get(key);
  return typeof v === "string" ? v.slice(0, max) : "";
}

async function startSession(user: Awaited<ReturnType<typeof authBackend.login>>) {
  const store = await cookies();
  store.set(SESSION_COOKIE, await encodeSession(user), sessionCookieOptions());
}

export async function loginAction(_prev: AuthFormState, formData: FormData): Promise<AuthFormState> {
  const email = field(formData, "email", 320).trim();
  const password = field(formData, "password", 256);
  const next = safeNext(field(formData, "next", 512));
  if (!email || !password) return { error: "Enter your email and password.", email, name: "" };
  try {
    await startSession(await authBackend.login(email, password, await clientIp()));
  } catch (err) {
    return {
      error: err instanceof AuthBackendError ? err.message : "Something went wrong. Please try again.",
      email,
      name: "",
    };
  }
  redirect(next);
}

export async function signupAction(_prev: AuthFormState, formData: FormData): Promise<AuthFormState> {
  const email = field(formData, "email", 320).trim();
  const name = field(formData, "name", 80).trim();
  const password = field(formData, "password", 256);
  const next = safeNext(field(formData, "next", 512));
  if (!email || !password) return { error: "Enter your email and choose a password.", email, name };
  try {
    await startSession(await authBackend.register(email, password, name || null, await clientIp()));
  } catch (err) {
    return {
      error: err instanceof AuthBackendError ? err.message : "Something went wrong. Please try again.",
      email,
      name,
    };
  }
  redirect(next);
}

export async function logoutAction(): Promise<void> {
  const store = await cookies();
  store.delete(SESSION_COOKIE);
  redirect("/");
}

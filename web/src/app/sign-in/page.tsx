"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { AuthCard, Field, FormError, PrimaryButton } from "@/components/form";
import { Notice } from "@/components/ui/notice";
import { supabase } from "@/lib/supabase";

export default function SignIn() {
  return (
    <Suspense>
      <SignInForm />
    </Suspense>
  );
}

function SignInForm() {
  const router = useRouter();
  // Sent here by a request that found the session over (`SIGNED_OUT_URL`).
  const signedOut = useSearchParams().has("signed-out");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    const { error } = await supabase().auth.signInWithPassword({
      email: String(form.get("email")),
      password: String(form.get("password")),
    });
    setBusy(false);
    if (error) {
      setError(error.status === 400 ? "That email and password don't match." : error.message);
      return;
    }
    router.replace("/");
  }

  return (
    <AuthCard title="Sign in">
      {signedOut && (
        <div className="mb-5">
          <Notice>You were signed out. Sign in again to carry on.</Notice>
        </div>
      )}
      <form onSubmit={onSubmit} className="space-y-5">
        <Field label="Email" name="email" type="email" autoComplete="email" required autoFocus />
        <Field label="Password" name="password" type="password" autoComplete="current-password" required />
        <FormError message={error} />
        <PrimaryButton busy={busy}>{busy ? "Signing in…" : "Sign in"}</PrimaryButton>
      </form>
      <p className="mt-5">
        <Link href="/sign-in/forgot" className="font-semibold text-accent underline-offset-4 hover:underline">
          Forgot your password?
        </Link>
      </p>
    </AuthCard>
  );
}

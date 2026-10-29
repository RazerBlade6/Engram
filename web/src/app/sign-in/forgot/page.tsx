"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";

import { AuthCard, Field, FormError, PrimaryButton } from "@/components/form";
import { supabase } from "@/lib/supabase";

/** Emails a link for choosing a new password. It never says whether an address has an account. */
export default function ForgotPassword() {
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = String(new FormData(event.currentTarget).get("email"));
    setBusy(true);
    setError(null);
    const { error } = await supabase().auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/auth/reset-password`,
    });
    setBusy(false);
    if (error?.status === 429) {
      setError("Too many requests. Wait a minute, then try again.");
      return;
    }
    setSent(true);
  }

  return (
    <AuthCard title="Forgot your password?">
      {sent ? (
        <p>If that address has an account, a link to choose a new password is on its way. It works for an hour.</p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-5">
          <p className="text-muted">Enter your email and we&apos;ll send you a link to choose a new one.</p>
          <Field label="Email" name="email" type="email" autoComplete="email" required autoFocus />
          <FormError message={error} />
          <PrimaryButton busy={busy}>{busy ? "Sending…" : "Send the link"}</PrimaryButton>
        </form>
      )}
      <p className="mt-5">
        <Link href="/sign-in" className="font-semibold text-accent underline-offset-4 hover:underline">
          Back to sign in
        </Link>
      </p>
    </AuthCard>
  );
}

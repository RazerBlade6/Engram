"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { AuthCard, Field, FormError, PrimaryButton } from "@/components/form";
import { supabase } from "@/lib/supabase";

export default function SignIn() {
  const router = useRouter();
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
      <form onSubmit={onSubmit} className="space-y-5">
        <Field label="Email" name="email" type="email" autoComplete="email" required autoFocus />
        <Field label="Password" name="password" type="password" autoComplete="current-password" required />
        <FormError message={error} />
        <PrimaryButton busy={busy}>{busy ? "Signing in…" : "Sign in"}</PrimaryButton>
      </form>
    </AuthCard>
  );
}

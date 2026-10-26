"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { AuthCard, Field, FormError, PrimaryButton } from "@/components/form";
import { supabase } from "@/lib/supabase";

const MIN_LENGTH = 8;

/** Invite links land here. supabase-js reads the session from the link before this renders. */
export default function SetPassword() {
  const router = useRouter();
  const [ready, setReady] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    supabase()
      .auth.getSession()
      .then(({ data }) => setReady(data.session !== null));
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const password = String(new FormData(event.currentTarget).get("password"));
    if (password.length < MIN_LENGTH) {
      setError(`Use at least ${MIN_LENGTH} characters.`);
      return;
    }
    setBusy(true);
    setError(null);
    const { error } = await supabase().auth.updateUser({ password });
    setBusy(false);
    if (error) {
      setError(error.message);
      return;
    }
    router.replace("/");
  }

  if (ready === null) return null;
  if (!ready) {
    return (
      <AuthCard title="This link has expired">
        <p className="text-muted">Ask for a new invite, or sign in if you already set a password.</p>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Choose a password">
      <form onSubmit={onSubmit} className="space-y-5">
        <Field label="Password" name="password" type="password" autoComplete="new-password" required autoFocus />
        <FormError message={error} />
        <PrimaryButton busy={busy}>{busy ? "Saving…" : "Continue"}</PrimaryButton>
      </form>
    </AuthCard>
  );
}

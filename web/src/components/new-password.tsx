"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useEffect, useState } from "react";

import { AuthCard, Field, FormError, PrimaryButton } from "@/components/form";
import { supabase } from "@/lib/supabase";

const MIN_LENGTH = 8;

/**
 * Where invite and password-reset links land: the link signs them in, then they choose a
 * password. supabase-js reads the session from the link before this renders.
 */
export function NewPassword({ title, expired }: { title: string; expired: ReactNode }) {
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
        <p className="text-muted">{expired}</p>
      </AuthCard>
    );
  }

  return (
    <AuthCard title={title}>
      <form onSubmit={onSubmit} className="space-y-5">
        <Field label="Password" name="password" type="password" autoComplete="new-password" required autoFocus />
        <FormError message={error} />
        <PrimaryButton busy={busy}>{busy ? "Saving…" : "Continue"}</PrimaryButton>
      </form>
    </AuthCard>
  );
}

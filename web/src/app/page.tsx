"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { supabase } from "@/lib/supabase";

type Profile = { id: string; display_name: string | null; role: "student" | "admin" };

export default function Home() {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);

  useEffect(() => {
    supabase()
      .auth.getSession()
      .then(async ({ data }) => {
        if (!data.session) {
          router.replace("/sign-in");
          return;
        }
        setProfile(await api<Profile>("/me"));
      });
  }, [router]);

  async function signOut() {
    await supabase().auth.signOut();
    router.replace("/sign-in");
  }

  if (!profile) return null;

  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <div className="flex items-baseline justify-between">
        <h1 className="text-3xl font-semibold">
          {profile.display_name ? `Hi, ${profile.display_name}` : "Engram"}
        </h1>
        <button onClick={signOut} className="text-muted underline hover:text-foreground">
          Sign out
        </button>
      </div>
      <p className="mt-4 text-muted">Nothing due yet.</p>
    </main>
  );
}

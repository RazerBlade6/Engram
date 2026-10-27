"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { useProfile } from "@/lib/profile";
import { supabase } from "@/lib/supabase";

export default function Home() {
  const router = useRouter();
  const profile = useProfile();

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
      {profile.role === "admin" && (
        <p className="mt-8">
          <Link href="/admin" className="text-accent underline">
            Ingested materials
          </Link>
        </p>
      )}
    </main>
  );
}

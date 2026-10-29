"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "./api";
import { supabase } from "./supabase";

export type Profile = {
  id: string;
  display_name: string | null;
  role: "student" | "admin";
  /** When they finished or skipped the welcome tour; null until then. */
  welcomed_at: string | null;
};

/** The signed-in user's profile, or null while loading. Sends signed-out visitors to sign in. */
export function useProfile(): Profile | null {
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

  return profile;
}

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { CourseSummary } from "@/lib/courses";
import { useProfile } from "@/lib/profile";
import { supabase } from "@/lib/supabase";

export default function Home() {
  const router = useRouter();
  const profile = useProfile();
  const [courses, setCourses] = useState<CourseSummary[] | null>(null);

  useEffect(() => {
    if (profile) api<CourseSummary[]>("/courses").then(setCourses);
  }, [profile]);

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

      {courses && (
        <section aria-labelledby="courses-heading" className="mt-10">
          <h2 id="courses-heading" className="text-xl font-semibold">
            Your courses
          </h2>
          {courses.length === 0 ? (
            <p className="mt-3 text-muted">No courses yet.</p>
          ) : (
            <ul className="mt-3 space-y-3">
              {courses.map((c) => (
                <li key={c.id}>
                  <Link
                    href={`/courses/${c.id}`}
                    className="block rounded-lg border border-border bg-white px-5 py-4 hover:border-accent"
                  >
                    <span className="block text-lg font-semibold">{c.title}</span>
                    <span className="text-muted">
                      {c.chapters ? `${c.covered} of ${c.chapters} chapters covered` : "No chapters yet"}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {profile.role === "admin" && (
        <p className="mt-10">
          <Link href="/admin" className="text-accent underline">
            Ingested materials
          </Link>
        </p>
      )}
    </main>
  );
}

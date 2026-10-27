"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { CourseSummary } from "@/lib/courses";
import type { ReviewSummary, SessionSummary } from "@/lib/review";
import { useProfile } from "@/lib/profile";
import { supabase } from "@/lib/supabase";

export default function Home() {
  const router = useRouter();
  const profile = useProfile();
  const [courses, setCourses] = useState<CourseSummary[] | null>(null);
  const [reviews, setReviews] = useState<ReviewSummary | null>(null);

  useEffect(() => {
    if (!profile) return;
    api<CourseSummary[]>("/courses").then(setCourses);
    api<ReviewSummary>("/review/summary").then(setReviews);
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
      {reviews && <ReviewHero summary={reviews} />}
      {courses && courses.length > 0 && (
        <p className="mt-6">
          <Link href="/ask" className="text-lg text-accent underline">
            Ask a question about your courses
          </Link>
        </p>
      )}

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
            Admin: materials and review order
          </Link>
        </p>
      )}
    </main>
  );
}

function ReviewHero({ summary }: { summary: ReviewSummary }) {
  const sessions = summary.sessions.filter((s) => s.cards > 0);
  if (!sessions.length) {
    return (
      <section className="mt-8">
        <h2 className="text-2xl font-semibold">Nothing to review right now</h2>
        <p className="mt-2 text-muted">When you mark a chapter as covered, its cards show up here.</p>
      </section>
    );
  }
  // With the "separate" order, the review (flashcards) and the quiz (multiple choice) are
  // started on their own.
  const separate = summary.order === "separate";
  return sessions.map((s) => <SessionHero key={s.session} summary={s} separate={separate} />);
}

const SESSION_TEXT = {
  review: { one: "card", many: "cards", heading: "to review", action: "Start review" },
  flashcards: { one: "flashcard", many: "flashcards", heading: "to review", action: "Start review" },
  quiz: { one: "question", many: "questions", heading: "in your quiz", action: "Start quiz" },
};

function SessionHero({ summary, separate }: { summary: SessionSummary; separate: boolean }) {
  const text = SESSION_TEXT[summary.session === "quiz" ? "quiz" : separate ? "flashcards" : "review"];
  const id = `${summary.session}-heading`;
  return (
    <section className="mt-8 rounded-2xl border border-border bg-white p-8" aria-labelledby={id}>
      <h2 id={id} className="text-3xl font-semibold">
        {summary.cards} {summary.cards === 1 ? text.one : text.many} {text.heading}
      </h2>
      <p className="mt-2 text-lg text-muted">
        About {summary.minutes} {summary.minutes === 1 ? "minute" : "minutes"}, from {listOf(summary.courses)}.
      </p>
      <Link
        href={summary.session === "quiz" ? "/review?session=quiz" : "/review"}
        className="mt-6 inline-block rounded-lg bg-accent px-6 py-3 text-lg font-medium text-white hover:bg-accent-strong"
      >
        {text.action}
      </Link>
    </section>
  );
}

function listOf(items: string[]): string {
  return new Intl.ListFormat("en", { type: "conjunction" }).format(items);
}

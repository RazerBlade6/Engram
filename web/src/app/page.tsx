"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { DateRow } from "@/components/dates";
import { ApiError, api } from "@/lib/api";
import { courseColors, isoDay, upcoming, type CourseDate } from "@/lib/calendar";
import type { CourseSummary } from "@/lib/courses";
import type { ReviewSummary, SessionSummary } from "@/lib/review";
import { useProfile } from "@/lib/profile";

export default function Home() {
  const router = useRouter();
  const profile = useProfile();
  const [courses, setCourses] = useState<CourseSummary[] | null>(null);
  const [reviews, setReviews] = useState<ReviewSummary | null>(null);
  const [dates, setDates] = useState<CourseDate[] | null>(null);

  useEffect(() => {
    if (!profile) return;
    api<CourseSummary[]>("/courses").then(setCourses);
    api<ReviewSummary>("/review/summary").then(setReviews);
    api<CourseDate[]>("/dates").then(setDates);
  }, [profile]);

  if (!profile) return null;

  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="text-3xl font-semibold">
        {profile.display_name ? `Hi, ${profile.display_name}` : "Engram"}
      </h1>
      {reviews && <ReviewHero summary={reviews} />}
      {courses && courses.length > 0 && dates && <ComingUp courses={courses} dates={dates} />}
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
            <p className="mt-3 text-muted">No courses yet. Add one for each subject you&apos;re studying.</p>
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
          <NewCourse onCreated={(course) => router.push(`/courses/${course.id}`)} />
        </section>
      )}
    </main>
  );
}

/** A course needs only a name; its materials are added on the course page. */
function NewCourse({ onCreated }: { onCreated: (course: CourseSummary) => void }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      onCreated(await api<CourseSummary>("/courses", { method: "POST", body: JSON.stringify({ title: title.trim() }) }));
    } catch (error) {
      setProblem(
        error instanceof ApiError && error.status === 422
          ? "Give the course a name."
          : "The course couldn't be added. Please try again.",
      );
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mt-4 rounded-lg border border-accent px-4 py-2 font-medium text-accent hover:bg-accent hover:text-white"
      >
        Add a course
      </button>
    );
  }
  return (
    <form onSubmit={create} className="mt-4 rounded-lg border border-border bg-white px-5 py-4">
      <label className="block">
        <span className="block font-medium">Course name</span>
        <input
          autoFocus
          required
          maxLength={200}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Introduction to Psychology"
          className="mt-2 w-full rounded-lg border border-border bg-white px-4 py-3 outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
        />
      </label>
      <div className="mt-3 flex items-center gap-4">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-accent px-6 py-2 font-medium text-white hover:bg-accent-strong disabled:opacity-60"
        >
          {busy ? "Adding…" : "Add course"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="text-muted underline hover:text-foreground">
          Cancel
        </button>
      </div>
      {problem && (
        <p role="alert" className="mt-3 rounded-lg bg-danger-soft px-4 py-3 text-danger">
          {problem}
        </p>
      )}
    </form>
  );
}

/** The next two exams, quizzes or deadlines. */
const COMING_UP = 2;

function ComingUp({ courses, dates }: { courses: CourseSummary[]; dates: CourseDate[] }) {
  const [today] = useState(() => isoDay(new Date()));
  const next = upcoming(dates, today).slice(0, COMING_UP);
  const colors = courseColors(courses);
  return (
    <section aria-labelledby="coming-up-heading" className="mt-10">
      <h2 id="coming-up-heading" className="text-xl font-semibold">
        Coming up
      </h2>
      {next.length > 0 && (
        <ul className="mt-3 space-y-3">
          {next.map((d) => (
            <li key={d.id} className="rounded-lg border border-border bg-white px-5 py-4">
              <DateRow date={d} color={colors.get(d.course_id)} today={today} />
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3">
        <Link href="/calendar" className="text-lg text-accent underline">
          {next.length ? "Open the calendar" : "Add your exams and deadlines to the calendar"}
        </Link>
      </p>
    </section>
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

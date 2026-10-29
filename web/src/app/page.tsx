"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { DateRow } from "@/components/dates";
import { WelcomeTour, tourSeen } from "@/components/welcome-tour";
import { Button, ButtonLink } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { IndexCard } from "@/components/ui/index-card";
import { Notice } from "@/components/ui/notice";
import { ProgressBar } from "@/components/ui/progress";
import { RowList } from "@/components/ui/row-list";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { courseColors, isoDay, upcoming, type CourseDate } from "@/lib/calendar";
import type { CourseSummary } from "@/lib/courses";
import type { ReviewSummary, SessionSummary } from "@/lib/review";
import { useProfile } from "@/lib/profile";

type Loaded = { courses: CourseSummary[]; reviews: ReviewSummary; dates: CourseDate[] };

export default function Home() {
  const router = useRouter();
  const profile = useProfile();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [failed, setFailed] = useState(false);
  // The first visit opens with a short tour. The page renders nothing on the server until the
  // profile has loaded, so reading browser storage here can't mismatch the server's HTML.
  const [touring, setTouring] = useState(() => typeof window !== "undefined" && !tourSeen());

  useEffect(() => {
    if (!profile) return;
    // Shown all at once, so the page doesn't shift as each part arrives.
    Promise.all([api<CourseSummary[]>("/courses"), api<ReviewSummary>("/review/summary"), api<CourseDate[]>("/dates")])
      .then(([courses, reviews, dates]) => setLoaded({ courses, reviews, dates }))
      .catch(() => setFailed(true));
  }, [profile]);

  if (!profile) return null;
  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="text-3xl font-bold">{profile.display_name ? `Hi, ${profile.display_name}` : "Today"}</h1>
      {failed ? (
        <div className="mt-8">
          <Notice
            tone="error"
            action={
              <Button variant="secondary" onClick={() => window.location.reload()}>
                Try again
              </Button>
            }
          >
            Today couldn&apos;t be loaded. Check your connection and try again.
          </Notice>
        </div>
      ) : !loaded ? (
        <TodayLoading />
      ) : (
        <>
          <ReviewHero summary={loaded.reviews} hasCourses={loaded.courses.length > 0} />
          {loaded.courses.length > 0 && <ComingUp courses={loaded.courses} dates={loaded.dates} />}
          {loaded.courses.length > 0 && (
            <p className="mt-6">
              <Link href="/ask" className="text-lg font-semibold text-accent underline-offset-4 hover:underline">
                Stuck on something? Ask a question
              </Link>
            </p>
          )}
          <Courses courses={loaded.courses} onCreated={(course) => router.push(`/courses/${course.id}`)} />
          {touring && (
            <WelcomeTour hasDue={loaded.reviews.sessions.some((s) => s.cards > 0)} onDone={() => setTouring(false)} />
          )}
        </>
      )}
    </main>
  );
}

function TodayLoading() {
  return (
    <div role="status" aria-label="Loading today" className="mt-8 flex flex-col gap-4">
      <Skeleton className="h-60" />
      <Skeleton className="mt-8 h-6 w-40" />
      <Skeleton className="h-16" />
      <Skeleton className="h-16" />
    </div>
  );
}

const SESSION_TEXT = {
  review: { one: "card", many: "cards", heading: "to review", action: "Start review", label: "Due today" },
  flashcards: {
    one: "flashcard",
    many: "flashcards",
    heading: "to review",
    action: "Start review",
    label: "Due today",
  },
  quiz: { one: "question", many: "questions", heading: "in your quiz", action: "Start quiz", label: "Quiz" },
};

/** The one obvious action: what's due, as a card on the desk. */
function ReviewHero({ summary, hasCourses }: { summary: ReviewSummary; hasCourses: boolean }) {
  const sessions = summary.sessions.filter((s) => s.cards > 0);
  if (!sessions.length) {
    return (
      <section className="mt-8">
        <IndexCard label="Due today" pile={false}>
          <h2 className="text-2xl font-bold">Nothing to review right now</h2>
          <p className="mt-2 text-lg text-muted">
            {hasCourses
              ? "When you mark a chapter as covered, its cards show up here."
              : "Add a course below, then mark the chapters you've covered. Their cards show up here."}
          </p>
        </IndexCard>
      </section>
    );
  }
  // With the "separate" order, the review (flashcards) and the quiz (multiple choice) are
  // started on their own. Only the first is the primary action.
  const separate = summary.order === "separate";
  return (
    <div className="mt-8 flex flex-col gap-10">
      {sessions.map((s, i) => (
        <SessionHero key={s.session} summary={s} separate={separate} primary={i === 0} />
      ))}
    </div>
  );
}

function SessionHero({ summary, separate, primary }: { summary: SessionSummary; separate: boolean; primary: boolean }) {
  const text = SESSION_TEXT[summary.session === "quiz" ? "quiz" : separate ? "flashcards" : "review"];
  const id = `${summary.session}-heading`;
  return (
    <section aria-labelledby={id}>
      <IndexCard label={text.label}>
        <h2 id={id} className="flex flex-wrap items-baseline gap-x-3 text-2xl font-bold">
          <span className="font-read text-6xl leading-none font-semibold text-accent tabular-nums">
            {summary.cards}
          </span>
          {summary.cards === 1 ? text.one : text.many} {text.heading}
        </h2>
        <p className="mt-3 text-lg text-muted">
          About {summary.minutes} {summary.minutes === 1 ? "minute" : "minutes"}, from {listOf(summary.courses)}.
        </p>
        <ButtonLink
          href={summary.session === "quiz" ? "/review?session=quiz" : "/review"}
          size="lg"
          variant={primary ? "primary" : "secondary"}
          className="mt-6"
        >
          {text.action}
        </ButtonLink>
      </IndexCard>
    </section>
  );
}

/** The next two exams, quizzes or deadlines. */
const COMING_UP = 2;

function ComingUp({ courses, dates }: { courses: CourseSummary[]; dates: CourseDate[] }) {
  const [today] = useState(() => isoDay(new Date()));
  const next = upcoming(dates, today).slice(0, COMING_UP);
  const colors = courseColors(courses);
  return (
    <section aria-labelledby="coming-up-heading" className="mt-12">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <h2 id="coming-up-heading" className="text-xl font-semibold">
          Coming up
        </h2>
        {next.length > 0 && (
          <Link href="/calendar" className="font-semibold text-accent underline-offset-4 hover:underline">
            Open the calendar
          </Link>
        )}
      </div>
      {next.length > 0 ? (
        <RowList className="mt-3">
          {next.map((d) => (
            <li key={d.id} className="py-3">
              <DateRow date={d} color={colors.get(d.course_id)} today={today} />
            </li>
          ))}
        </RowList>
      ) : (
        <p className="mt-2 text-muted">
          No exams or deadlines yet.{" "}
          <Link href="/calendar" className="font-semibold text-accent underline-offset-4 hover:underline">
            Add them to the calendar
          </Link>
        </p>
      )}
    </section>
  );
}

function Courses({ courses, onCreated }: { courses: CourseSummary[]; onCreated: (course: CourseSummary) => void }) {
  return (
    <section aria-labelledby="courses-heading" className="mt-12">
      <h2 id="courses-heading" className="text-xl font-semibold">
        Your courses
      </h2>
      {courses.length === 0 ? (
        <p className="mt-2 text-muted">No courses yet. Add one for each subject you&apos;re studying.</p>
      ) : (
        <RowList className="mt-3">
          {courses.map((c) => (
            <li key={c.id}>
              <Link
                href={`/courses/${c.id}`}
                className="block rounded-control px-2 py-3 transition-colors duration-150 hover:bg-foreground/5"
              >
                <span className="flex flex-wrap items-baseline justify-between gap-x-4">
                  <span className="text-lg font-semibold">{c.title}</span>
                  <span className="text-muted tabular-nums">
                    {c.chapters ? `${c.covered} of ${c.chapters} chapters covered` : "No chapters yet"}
                  </span>
                </span>
                {c.chapters > 0 && (
                  <ProgressBar value={c.covered} max={c.chapters} label="Chapters covered" className="mt-2" />
                )}
              </Link>
            </li>
          ))}
        </RowList>
      )}
      <NewCourse onCreated={onCreated} />
    </section>
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
      onCreated(
        await api<CourseSummary>("/courses", { method: "POST", body: JSON.stringify({ title: title.trim() }) }),
      );
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
      <Button variant="secondary" onClick={() => setOpen(true)} className="mt-4">
        Add a course
      </Button>
    );
  }
  return (
    <form onSubmit={create} className="rise-in mt-4 rounded-control border border-border bg-surface p-5 shadow-card">
      <Field
        label="Course name"
        autoFocus
        required
        maxLength={200}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="e.g. Introduction to Psychology"
      />
      <div className="mt-4 flex items-center gap-3">
        <Button type="submit" disabled={busy || !title.trim()}>
          {busy ? "Adding…" : "Add course"}
        </Button>
        <Button variant="quiet" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
      {problem && (
        <div className="mt-4">
          <Notice tone="error">{problem}</Notice>
        </div>
      )}
    </form>
  );
}

function listOf(items: string[]): string {
  return new Intl.ListFormat("en", { type: "conjunction" }).format(items);
}

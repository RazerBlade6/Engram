"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Toast, type ToastMessage } from "@/components/toast";
import { Button, ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { api, apiFetch } from "@/lib/api";
import { chapterNote, splitChapterTitle, type Chapter, type Coverage, type Course } from "@/lib/courses";
import { cx } from "@/lib/cx";
import { useProfile } from "@/lib/profile";

import { CardList } from "./card-list";
import { MaterialsPanel } from "./materials-panel";

// Day first, as everywhere else (D54).
const dateFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long" });
const POLL_MS = 4000;
// "uploading" isn't here: this page uploads and then reloads, so one left uploading was abandoned.
const pending = (status: string) => ["queued", "processing"].includes(status);

export function CourseView() {
  const { id } = useParams<{ id: string }>();
  const profile = useProfile();
  const [course, setCourse] = useState<Course | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const toastId = useRef(0);

  const reload = useCallback(() => {
    api<Course>(`/courses/${id}`)
      .then(setCourse)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  useEffect(() => {
    if (profile) reload();
  }, [profile, reload]);

  // While anything is still being read, or cards are being made, check back every few seconds.
  const reading =
    (course?.materials.some((m) => pending(m.status)) ||
      course?.textbooks.some((t) => t.chapters.some((ch) => ch.cards_status === "pending"))) ??
    false;
  useEffect(() => {
    if (!reading) return;
    const timer = setInterval(reload, POLL_MS);
    return () => clearInterval(timer);
  }, [reading, reload]);

  const setCovered = useCallback((chapterId: string, coveredAt: string | null) => {
    setCourse(
      (c) =>
        c && {
          ...c,
          textbooks: c.textbooks.map((t) => ({
            ...t,
            chapters: t.chapters.map((ch) =>
              ch.id === chapterId
                ? { ...ch, covered_at: coveredAt, cards_status: coveredAt ? (ch.cards_status ?? "pending") : null }
                : ch,
            ),
          })),
        },
    );
  }, []);

  const show = useCallback((text: string, undo?: () => void) => {
    toastId.current += 1;
    setToast({ id: toastId.current, text, undo });
  }, []);
  const hideToast = useCallback(() => setToast(null), []);

  // Say so when an upload finishes being read.
  const statuses = useRef(new Map<string, string>());
  useEffect(() => {
    for (const m of course?.materials ?? []) {
      const before = statuses.current.get(m.id);
      if (before && pending(before) && m.status === "ready") show(`${m.title} is ready.`);
      if (before && pending(before) && m.status === "failed") show(`${m.title} couldn't be read.`);
      statuses.current.set(m.id, m.status);
    }
    // And when a chapter's cards have been made.
    for (const ch of course?.textbooks.flatMap((t) => t.chapters) ?? []) {
      const before = statuses.current.get(ch.id);
      if (before === "pending" && ch.cards_status === "ready") {
        show(`${chapterName(ch)}: ${ch.cards} ${ch.cards === 1 ? "card is" : "cards are"} ready.`);
      }
      if (before === "pending" && ch.cards_status === "failed") {
        show(`The cards for ${chapterName(ch)} couldn't be made.`);
      }
      statuses.current.set(ch.id, ch.cards_status ?? "");
    }
  }, [course, show]);

  async function cover(chapter: Chapter) {
    const name = chapterName(chapter);
    setCovered(chapter.id, new Date().toISOString()); // shown at once; confirmed below
    try {
      const saved = await api<Coverage>(`/sections/${chapter.id}/covered`, { method: "PUT" });
      setCovered(chapter.id, saved.covered_at);
      show(`${name} marked as covered.`, () => uncover({ ...chapter, covered_at: saved.covered_at }, true));
    } catch {
      setCovered(chapter.id, null);
      show(`Couldn't mark ${name} as covered. Please try again.`);
    }
  }

  async function uncover(chapter: Chapter, undoing = false) {
    const previous = chapter.covered_at;
    setCovered(chapter.id, null);
    try {
      await apiFetch(`/sections/${chapter.id}/covered`, { method: "DELETE" });
      if (!undoing) show(`${chapterName(chapter)} is no longer marked as covered.`);
    } catch {
      setCovered(chapter.id, previous);
      show("Couldn't undo that. Please try again.");
    }
  }

  if (error) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-10">
        <Notice
          tone="error"
          action={
            <Button variant="secondary" onClick={() => window.location.reload()}>
              Try again
            </Button>
          }
        >
          This course couldn&apos;t be loaded. Check your connection and try again.
        </Notice>
        <ButtonLink href="/" variant="secondary" className="mt-4">
          ← Today
        </ButtonLink>
      </main>
    );
  }
  if (!course) return <CourseLoading />;

  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <ButtonLink href="/" variant="secondary">
        ← Today
      </ButtonLink>
      <h1 className="mt-6 text-3xl font-bold">{course.title}</h1>

      <div className="mt-8 grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <section aria-labelledby="chapters-heading" className="min-w-0">
          <h2 id="chapters-heading" className="text-xl font-semibold">
            Chapters
          </h2>
          <p className="text-muted">
            When you&apos;ve covered a chapter in class, mark it here. Its cards are made for you.
          </p>

          {course.textbooks.length === 0 && (
            <div className="mt-5">
              <EmptyState
                title={
                  course.materials.some((m) => m.kind === "textbook" && pending(m.status))
                    ? "Your textbook is being read"
                    : "No chapters yet"
                }
              >
                {course.materials.some((m) => m.kind === "textbook" && pending(m.status))
                  ? "Its chapters will appear here once it's ready. You can leave this page."
                  : "Chapters come from the course textbook. They'll appear here once it's added."}
              </EmptyState>
            </div>
          )}

          {course.textbooks.map((book) => (
            <div key={book.material_id} className="mt-5">
              {course.textbooks.length > 1 && <h3 className="mb-2 font-semibold">{book.title}</h3>}
              {/* The book's contents page. */}
              <ol className="divide-y divide-border/70 rounded-card bg-paper shadow-card">
                {book.chapters.map((chapter) => (
                  <ChapterRow key={chapter.id} chapter={chapter} onCover={cover} onUncover={uncover} />
                ))}
              </ol>
            </div>
          ))}
        </section>

        <MaterialsPanel
          courseId={course.id}
          materials={course.materials}
          onChange={reload}
          show={show}
          canAddTextbook={profile?.role === "admin"}
        />
      </div>

      <Toast key={toast?.id} toast={toast} onDone={hideToast} />
    </main>
  );
}

function CourseLoading() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-8" role="status" aria-label="Loading the course">
      <Skeleton className="h-11 w-28" />
      <Skeleton className="mt-6 h-9 w-72" />
      <div className="mt-8 grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <Skeleton className="h-96" />
        <Skeleton className="h-64" />
      </div>
    </main>
  );
}

function ChapterRow({
  chapter,
  onCover,
  onUncover,
}: {
  chapter: Chapter;
  onCover: (chapter: Chapter) => void;
  onUncover: (chapter: Chapter) => void;
}) {
  const { number, title } = splitChapterTitle(chapter.title);
  const [open, setOpen] = useState(false);
  const note = chapterNote(chapter, (iso) => dateFormat.format(new Date(iso)));
  const making = chapter.covered_at !== null && chapter.cards_status === "pending";
  return (
    <li className="px-5 py-4 sm:px-6">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <span className="w-8 shrink-0 font-read text-2xl font-semibold text-muted tabular-nums">{number}</span>
        <div className="min-w-0 flex-1 basis-48">
          <div className="text-lg font-semibold">{title}</div>
          <div
            className={cx(
              "flex flex-wrap items-center gap-x-2 text-sm",
              chapter.cards_status === "failed" ? "text-danger" : "text-muted",
            )}
          >
            {making && <MakingCards />}
            {note}
            {chapter.cards > 0 && (
              <>
                <span aria-hidden>·</span>
                <button
                  onClick={() => setOpen((o) => !o)}
                  aria-expanded={open}
                  className="font-semibold text-accent underline-offset-4 hover:underline"
                >
                  {open ? "Hide cards" : "See cards"}
                </button>
              </>
            )}
          </div>
        </div>
        <ChapterAction chapter={chapter} onCover={onCover} onUncover={onUncover} />
      </div>
      {open && <CardList sectionId={chapter.id} chapter={chapterName(chapter)} />}
    </li>
  );
}

/** A tiny pile of cards being dealt, while a chapter's cards are made. */
function MakingCards() {
  return (
    <span aria-hidden className="making-cards relative inline-block h-3.5 w-5">
      <i />
      <i />
      <i />
    </span>
  );
}

function ChapterAction({
  chapter,
  onCover,
  onUncover,
}: {
  chapter: Chapter;
  onCover: (chapter: Chapter) => void;
  onUncover: (chapter: Chapter) => void;
}) {
  return chapter.covered_at ? (
    <span className="flex shrink-0 items-center gap-2">
      <span className="flex items-center gap-1 font-semibold" style={{ color: "var(--rate-3)" }}>
        <CheckIcon /> Covered
      </span>
      <Button variant="quiet" onClick={() => onUncover(chapter)} aria-label={`Unmark ${chapterName(chapter)}`}>
        Unmark
      </Button>
    </span>
  ) : (
    <Button variant="secondary" onClick={() => onCover(chapter)} aria-label={`Mark ${chapterName(chapter)} as covered`}>
      We&apos;ve covered this
    </Button>
  );
}

function chapterName(chapter: Chapter): string {
  const { number, title } = splitChapterTitle(chapter.title);
  return number ? `Chapter ${number}: ${title}` : title;
}

function CheckIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="size-5" fill="currentColor">
      <path
        fillRule="evenodd"
        d="M16.7 5.3a1 1 0 0 1 0 1.4l-8 8a1 1 0 0 1-1.4 0l-4-4a1 1 0 1 1 1.4-1.4L8 12.6l7.3-7.3a1 1 0 0 1 1.4 0Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

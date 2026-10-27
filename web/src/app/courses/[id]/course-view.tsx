"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Toast, type ToastMessage } from "@/components/toast";
import { api, apiFetch } from "@/lib/api";
import {
  pageRange,
  splitChapterTitle,
  type Chapter,
  type Coverage,
  type Course,
  type Material,
} from "@/lib/courses";
import { useProfile } from "@/lib/profile";

const dateFormat = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "long" });

export function CourseView() {
  const { id } = useParams<{ id: string }>();
  const profile = useProfile();
  const [course, setCourse] = useState<Course | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const toastId = useRef(0);

  useEffect(() => {
    if (!profile) return;
    api<Course>(`/courses/${id}`)
      .then(setCourse)
      .catch((e: Error) => setError(e.message));
  }, [id, profile]);

  const setCovered = useCallback((chapterId: string, coveredAt: string | null) => {
    setCourse((c) =>
      c && {
        ...c,
        textbooks: c.textbooks.map((t) => ({
          ...t,
          chapters: t.chapters.map((ch) => (ch.id === chapterId ? { ...ch, covered_at: coveredAt } : ch)),
        })),
      },
    );
  }, []);

  const show = useCallback((text: string, undo?: () => void) => {
    toastId.current += 1;
    setToast({ id: toastId.current, text, undo });
  }, []);
  const hideToast = useCallback(() => setToast(null), []);

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
      <main className="mx-auto max-w-3xl px-6 py-16">
        <p>This course couldn&apos;t be loaded.</p>
        <Link href="/" className="mt-4 inline-block text-accent underline">
          Back to your courses
        </Link>
      </main>
    );
  }
  if (!course) return null;

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <Link href="/" className="text-muted underline hover:text-foreground">
        Your courses
      </Link>
      <h1 className="mt-4 text-3xl font-semibold">{course.title}</h1>

      <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <section aria-labelledby="chapters-heading">
          <h2 id="chapters-heading" className="text-xl font-semibold">
            Chapters
          </h2>
          <p className="mt-1 text-muted">When you&apos;ve covered a chapter in class, mark it here.</p>

          {course.textbooks.length === 0 && (
            <p className="mt-6 rounded-lg border border-border bg-white px-5 py-4">
              Your textbook is still being prepared. Its chapters will appear here once it&apos;s ready.
            </p>
          )}

          {course.textbooks.map((book) => (
            <div key={book.material_id} className="mt-6">
              {course.textbooks.length > 1 && <h3 className="mb-2 font-semibold">{book.title}</h3>}
              <ol className="divide-y divide-border rounded-lg border border-border bg-white">
                {book.chapters.map((chapter) => (
                  <ChapterRow key={chapter.id} chapter={chapter} onCover={cover} onUncover={uncover} />
                ))}
              </ol>
            </div>
          ))}
        </section>

        <section aria-labelledby="materials-heading">
          <h2 id="materials-heading" className="text-xl font-semibold">
            Materials
          </h2>
          <ul className="mt-3 space-y-3">
            {course.materials.map((m) => (
              <li key={m.id} className="rounded-lg border border-border bg-white px-4 py-3">
                <div className="font-medium">{m.title}</div>
                <div className="text-sm text-muted">{materialStatus(m)}</div>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <Toast key={toast?.id} toast={toast} onDone={hideToast} />
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
  const pages = pageRange(chapter);
  return (
    <li className="flex items-center gap-4 px-5 py-4">
      <span className="w-8 shrink-0 text-lg font-semibold text-muted tabular-nums">{number}</span>
      <div className="min-w-0 flex-1">
        <div className="font-medium">{title}</div>
        <div className="text-sm text-muted">
          {chapter.covered_at ? `Covered on ${dateFormat.format(new Date(chapter.covered_at))}` : pages}
        </div>
      </div>
      {chapter.covered_at ? (
        <span className="flex shrink-0 items-center gap-3">
          <span className="flex items-center gap-1 font-medium text-success">
            <CheckIcon /> Covered
          </span>
          <button
            onClick={() => onUncover(chapter)}
            className="text-sm text-muted underline hover:text-foreground"
            aria-label={`Unmark ${chapterName(chapter)}`}
          >
            Unmark
          </button>
        </span>
      ) : (
        <button
          onClick={() => onCover(chapter)}
          className="shrink-0 rounded-lg border border-accent px-4 py-2 font-medium text-accent hover:bg-accent hover:text-white"
          aria-label={`Mark ${chapterName(chapter)} as covered`}
        >
          We&apos;ve covered this
        </button>
      )}
    </li>
  );
}

function chapterName(chapter: Chapter): string {
  const { number, title } = splitChapterTitle(chapter.title);
  return number ? `Chapter ${number}: ${title}` : title;
}

function materialStatus(m: Material): string {
  const kind = m.kind === "textbook" ? "Textbook" : "Slides";
  switch (m.status) {
    case "ready":
      return kind;
    case "failed":
      return `${kind} · couldn't be read`;
    default:
      return `${kind} · being prepared`;
  }
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

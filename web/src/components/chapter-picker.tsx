"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Course } from "@/lib/courses";

/**
 * Optional checkboxes for the chapters an exam, quiz or deadline covers, from the course's
 * textbooks. Shows nothing for a course without any.
 */
export function ChapterPicker({
  courseId,
  selected,
  onChange,
}: {
  courseId: string;
  selected: string[];
  onChange: (chapters: string[]) => void;
}) {
  const [course, setCourse] = useState<Course | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<Course>(`/courses/${courseId}`).then((c) => !cancelled && setCourse(c));
    return () => {
      cancelled = true;
    };
  }, [courseId]);

  const textbooks = course?.id === courseId ? course.textbooks.filter((t) => t.chapters.length) : [];
  if (!textbooks.length) return null;
  const toggle = (id: string, on: boolean) => onChange(on ? [...selected, id] : selected.filter((s) => s !== id));

  return (
    <details className="rounded-control border border-border-strong bg-surface" open={selected.length > 0 || undefined}>
      <summary className="cursor-pointer rounded-control px-4 py-3 font-semibold hover:bg-foreground/5">
        Chapters it covers <span className="font-normal text-muted">(optional)</span>
        {selected.length > 0 && <span className="font-normal text-muted"> · {selected.length} chosen</span>}
      </summary>
      <div className="space-y-4 border-t border-border px-4 py-3">
        {textbooks.map((t) => (
          <fieldset key={t.material_id}>
            <legend className={textbooks.length > 1 ? "mb-2 font-semibold" : "sr-only"}>{t.title}</legend>
            <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
              {t.chapters.map((ch) => (
                <label key={ch.id} className="flex items-start gap-3 py-1">
                  <input
                    type="checkbox"
                    checked={selected.includes(ch.id)}
                    onChange={(e) => toggle(ch.id, e.target.checked)}
                    className="mt-1 size-5 shrink-0 accent-accent"
                  />
                  <span>{ch.title}</span>
                </label>
              ))}
            </div>
          </fieldset>
        ))}
      </div>
    </details>
  );
}

"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { CONTROL } from "@/components/ui/field";
import { api } from "@/lib/api";
import { splitChapterTitle, type Chapter, type Course } from "@/lib/courses";
import { cx } from "@/lib/cx";

/** A textbook this long shows its covered chapters and a range, with the full list one step away. */
const SHORT = 12;

/**
 * Optional checkboxes for the chapters an exam, quiz or deadline covers, from the course's
 * textbooks. Shows nothing for a course without any. Tests cover what has been taught, so a long
 * textbook leads with the chapters already covered and a from–to range (D66).
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

  return (
    <details className="rounded-control border border-border-strong bg-surface" open={selected.length > 0 || undefined}>
      <summary className="cursor-pointer rounded-control px-4 py-3 font-semibold hover:bg-foreground/5">
        Chapters it covers <span className="font-normal text-muted">(optional)</span>
        {selected.length > 0 && <span className="font-normal text-muted"> · {selected.length} chosen</span>}
      </summary>
      <div className="space-y-6 border-t border-border px-4 py-4">
        {textbooks.map((t) => (
          <fieldset key={t.material_id}>
            <legend className={textbooks.length > 1 ? "mb-2 font-semibold" : "sr-only"}>{t.title}</legend>
            <Chapters chapters={t.chapters} selected={selected} onChange={onChange} />
          </fieldset>
        ))}
      </div>
    </details>
  );
}

function Chapters({
  chapters,
  selected,
  onChange,
}: {
  chapters: Chapter[];
  selected: string[];
  onChange: (chapters: string[]) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const [from, setFrom] = useState(0);
  const [to, setTo] = useState(0);

  const toggle = (id: string, on: boolean) => onChange(on ? [...selected, id] : selected.filter((s) => s !== id));
  const mine = chapters.filter((ch) => selected.includes(ch.id));

  if (chapters.length <= SHORT) return <List chapters={chapters} selected={selected} onToggle={toggle} />;

  const covered = chapters.filter((ch) => ch.covered_at);
  // Chosen through the range but not on screen: listed, so nothing chosen is out of sight.
  const hidden = showAll ? [] : mine.filter((ch) => !ch.covered_at);

  function addRange() {
    const [start, end] = from <= to ? [from, to] : [to, from];
    const ids = chapters.slice(start, end + 1).map((ch) => ch.id);
    onChange([...selected, ...ids.filter((id) => !selected.includes(id))]);
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-x-3 gap-y-2">
        <RangeSelect label="Chapters" chapters={chapters} value={from} onChange={setFrom} />
        <RangeSelect label="to" chapters={chapters} value={to} onChange={setTo} />
        <Button type="button" variant="secondary" onClick={addRange}>
          Choose {from === to ? "it" : "these"}
        </Button>
      </div>

      {!showAll && covered.length > 0 && (
        <div>
          <p className="text-sm font-semibold text-muted">Covered in class</p>
          <List chapters={covered} selected={selected} onToggle={toggle} />
        </div>
      )}

      {hidden.length > 0 && (
        <div>
          <p className="text-sm font-semibold text-muted">Also chosen</p>
          <List chapters={hidden} selected={selected} onToggle={toggle} />
        </div>
      )}

      {showAll ? (
        <div>
          <p className="text-sm font-semibold text-muted">All {chapters.length} chapters</p>
          <List chapters={chapters} selected={selected} onToggle={toggle} />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="font-semibold text-accent underline-offset-4 hover:underline"
        >
          Show all {chapters.length} chapters
        </button>
      )}

      {mine.length > 0 && (
        <button
          type="button"
          onClick={() => onChange(selected.filter((id) => !chapters.some((ch) => ch.id === id)))}
          className="block text-sm text-muted underline-offset-4 hover:text-foreground hover:underline"
        >
          Clear {mine.length === 1 ? "the chosen chapter" : `all ${mine.length} chosen`}
        </button>
      )}
    </div>
  );
}

function RangeSelect({
  label,
  chapters,
  value,
  onChange,
}: {
  label: string;
  chapters: Chapter[];
  value: number;
  onChange: (index: number) => void;
}) {
  return (
    <label className="flex min-w-0 flex-col">
      <span className="text-sm font-semibold">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className={cx(CONTROL, "mt-1 w-auto max-w-60 truncate")}
      >
        {chapters.map((ch, i) => (
          <option key={ch.id} value={i}>
            {chapterLabel(ch)}
          </option>
        ))}
      </select>
    </label>
  );
}

function List({
  chapters,
  selected,
  onToggle,
}: {
  chapters: Chapter[];
  selected: string[];
  onToggle: (id: string, on: boolean) => void;
}) {
  return (
    <div className="mt-1 grid gap-x-6 sm:grid-cols-2">
      {chapters.map((ch) => (
        <label key={ch.id} className="flex items-start gap-3 py-1">
          <input
            type="checkbox"
            checked={selected.includes(ch.id)}
            onChange={(e) => onToggle(ch.id, e.target.checked)}
            className="mt-1 size-5 shrink-0 accent-accent"
          />
          <span className={cx("min-w-0", selected.includes(ch.id) && "font-semibold")}>{chapterLabel(ch)}</span>
        </label>
      ))}
    </div>
  );
}

/** "Chapter 3 Biological Macromolecules" → "3 · Biological Macromolecules". */
function chapterLabel(chapter: Chapter): string {
  const { number, title } = splitChapterTitle(chapter.title);
  return number ? `${number} · ${title}` : title;
}

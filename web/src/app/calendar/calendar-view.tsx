"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent, type RefObject } from "react";

import { ChapterPicker } from "@/components/chapter-picker";
import { DateRow } from "@/components/dates";
import { FormError } from "@/components/form";
import { Toast, type ToastMessage } from "@/components/toast";
import { ApiError, api, apiFetch } from "@/lib/api";
import {
  KIND_EXAMPLE,
  KIND_LABEL,
  courseColors,
  dayLabel,
  isoDay,
  localFirstDay,
  monthWeeks,
  parseDay,
  upcoming,
  type CourseDate,
  type DateKind,
  type NewDate,
} from "@/lib/calendar";
import type { CourseSummary } from "@/lib/courses";
import { useProfile } from "@/lib/profile";

const KINDS = Object.keys(KIND_LABEL) as DateKind[];
// Matches the API's range: wide enough for any course, narrow enough to catch a mistyped year.
const MIN_DAY = "2000-01-01";
const MAX_DAY = "2100-12-31";

type Month = { year: number; month: number };

const byDay = (a: CourseDate, b: CourseDate) => a.on.localeCompare(b.on) || a.course.localeCompare(b.course);

export function CalendarView() {
  const profile = useProfile();
  const [courses, setCourses] = useState<CourseSummary[] | null>(null);
  const [dates, setDates] = useState<CourseDate[] | null>(null);

  useEffect(() => {
    if (!profile) return;
    api<CourseSummary[]>("/courses").then(setCourses);
    api<CourseDate[]>("/dates").then(setDates);
  }, [profile]);

  if (!profile || !courses || !dates) return null;
  return <Calendar courses={courses} initial={dates} />;
}

/** Rendered only in the browser, once loaded, so "today" is the student's today. */
function Calendar({ courses, initial }: { courses: CourseSummary[]; initial: CourseDate[] }) {
  const [dates, setDates] = useState(initial);
  const [today] = useState(() => isoDay(new Date()));
  const [firstDay] = useState(localFirstDay);
  const [month, setMonth] = useState<Month>(() => monthOf(today));
  const [day, setDay] = useState(today);
  const [editing, setEditing] = useState<CourseDate | null>(null);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const toasts = useRef(0);
  const what = useRef<HTMLInputElement>(null);

  const notify = useCallback((text: string, undo?: () => void) => {
    setToast({ id: ++toasts.current, text, undo });
  }, []);
  const clearToast = useCallback(() => setToast(null), []);

  const colors = courseColors(courses);
  const next = upcoming(dates, today);

  function added(date: CourseDate) {
    setDates((ds) => [...ds, date].sort(byDay));
    setMonth(monthOf(date.on));
  }

  function changed(date: CourseDate) {
    setDates((ds) => ds.map((d) => (d.id === date.id ? date : d)).sort(byDay));
    setMonth(monthOf(date.on));
    setEditing(null);
    notify(`Saved ${date.title}, ${dayLabel(date.on, today)}`);
  }

  function deleted(date: CourseDate) {
    setDates((ds) => ds.filter((d) => d.id !== date.id));
    setEditing(null);
    notify(`Deleted ${date.title}`, async () => {
      const { kind, title, on } = date;
      const chapters = date.chapters.map((c) => c.id);
      const back = await api<CourseDate>(`/courses/${date.course_id}/dates`, {
        method: "POST",
        body: JSON.stringify({ kind, title, on, chapters } satisfies NewDate),
      });
      setDates((ds) => [...ds, back].sort(byDay));
    });
  }

  function pickDay(on: string) {
    setDay(on);
    what.current?.focus();
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <Link href="/" className="text-muted underline hover:text-foreground">
        Back to Today
      </Link>
      <h1 className="mt-4 text-3xl font-semibold">Calendar</h1>

      {courses.length === 0 ? (
        <p className="mt-3 text-lg text-muted">Once you have a course, you can add its exams and deadlines here.</p>
      ) : (
        <QuickAdd
          courses={courses}
          day={day}
          onDay={setDay}
          what={what}
          onAdded={(date) => {
            added(date);
            notify(`Added ${date.title}, ${dayLabel(date.on, today)}`);
          }}
        />
      )}

      <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <MonthGrid
          month={month}
          onMonth={setMonth}
          thisMonth={monthOf(today)}
          firstDay={firstDay}
          dates={dates}
          colors={colors}
          today={today}
          onPickDay={courses.length ? pickDay : undefined}
          onOpen={setEditing}
        />

        <section aria-labelledby="upcoming-heading">
          <h2 id="upcoming-heading" className="text-xl font-semibold">
            Coming up
          </h2>
          {next.length === 0 ? (
            <p className="mt-3 text-muted">Nothing coming up. Exams, quizzes and deadlines you add show up here.</p>
          ) : (
            <ul className="mt-3 space-y-2">
              {next.map((d) => (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => setEditing(d)}
                    aria-label={`Change ${d.title}, ${d.course}`}
                    className="w-full rounded-lg border border-border bg-white px-4 py-3 text-left hover:border-accent"
                  >
                    <DateRow date={d} color={colors.get(d.course_id)} today={today} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {editing && (
        <EditDialog
          key={editing.id}
          date={editing}
          onClose={() => setEditing(null)}
          onSaved={changed}
          onDeleted={deleted}
        />
      )}
      <Toast toast={toast} onDone={clearToast} />
    </main>
  );
}

function monthOf(iso: string): Month {
  const d = parseDay(iso);
  return { year: d.getFullYear(), month: d.getMonth() };
}

function errorText(error: unknown): string {
  if (error instanceof ApiError && error.status === 422) return "Please check the name, the date and the chapters.";
  return "That couldn't be saved. Please try again.";
}

function QuickAdd({
  courses,
  day,
  onDay,
  what,
  onAdded,
}: {
  courses: CourseSummary[];
  day: string;
  onDay: (day: string) => void;
  what: RefObject<HTMLInputElement | null>;
  onAdded: (date: CourseDate) => void;
}) {
  const [course, setCourse] = useState(courses[0].id);
  const [kind, setKind] = useState<DateKind>("exam");
  const [title, setTitle] = useState("");
  const [chapters, setChapters] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim() || !day) return;
    setBusy(true);
    setError(null);
    try {
      const date = await api<CourseDate>(`/courses/${course}/dates`, {
        method: "POST",
        body: JSON.stringify({ kind, title: title.trim(), on: day, chapters } satisfies NewDate),
      });
      setTitle("");
      setChapters([]);
      onAdded(date);
      what.current?.focus();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const control = "rounded-lg border border-border bg-white px-3 py-3 text-lg";
  return (
    <form onSubmit={submit} className="mt-6 rounded-2xl border border-border bg-white p-6" aria-labelledby="add-heading">
      <h2 id="add-heading" className="text-xl font-semibold">
        Add an exam, quiz or deadline
      </h2>
      <div className="mt-4 flex flex-wrap items-end gap-3">
        {courses.length > 1 && (
          <label className="flex flex-col gap-1">
            <span className="font-medium">Course</span>
            <select value={course} onChange={(e) => {
                setCourse(e.target.value);
                setChapters([]);
              }} className={control}>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="flex flex-col gap-1">
          <span className="font-medium">Type</span>
          <select value={kind} onChange={(e) => setKind(e.target.value as DateKind)} className={control}>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABEL[k]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex min-w-48 flex-1 flex-col gap-1">
          <span className="font-medium">What</span>
          <input
            ref={what}
            type="text"
            required
            maxLength={200}
            autoComplete="off"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={`For example, ${KIND_EXAMPLE[kind]}`}
            className={control}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-medium">Date</span>
          <input
            type="date"
            required
            min={MIN_DAY}
            max={MAX_DAY}
            value={day}
            onChange={(e) => onDay(e.target.value)}
            className={control}
          />
        </label>
        <button
          type="submit"
          disabled={busy || !title.trim() || !day}
          className="rounded-lg bg-accent px-6 py-3 text-lg font-medium text-white hover:bg-accent-strong disabled:opacity-50"
        >
          Add
        </button>
      </div>
      {courses.length === 1 && <p className="mt-3 text-muted">For {courses[0].title}.</p>}
      <div className="mt-4">
        <ChapterPicker courseId={course} selected={chapters} onChange={setChapters} />
      </div>
      {error && (
        <div className="mt-4">
          <FormError message={error} />
        </div>
      )}
    </form>
  );
}

function MonthGrid({
  month,
  onMonth,
  thisMonth,
  firstDay,
  dates,
  colors,
  today,
  onPickDay,
  onOpen,
}: {
  month: Month;
  onMonth: (month: Month) => void;
  thisMonth: Month;
  firstDay: number;
  dates: CourseDate[];
  colors: Map<string, string>;
  today: string;
  onPickDay?: (day: string) => void;
  onOpen: (date: CourseDate) => void;
}) {
  const weeks = monthWeeks(month.year, month.month, firstDay);
  const onDay = Map.groupBy(dates, (d) => d.on);
  // Only the courses that have dates, so the key stays short.
  const legend = [...new Map(dates.map((d) => [d.course_id, d.course]))];
  const shift = (by: number) => {
    const d = new Date(month.year, month.month + by, 1);
    onMonth({ year: d.getFullYear(), month: d.getMonth() });
  };
  const title = new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(
    new Date(month.year, month.month, 1),
  );
  const weekday = new Intl.DateTimeFormat(undefined, { weekday: "short" });
  const isThisMonth = month.year === thisMonth.year && month.month === thisMonth.month;
  const button = "rounded-lg border border-border bg-white px-3 py-2 hover:border-accent";

  return (
    <section aria-labelledby="month-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="month-heading" className="text-xl font-semibold" aria-live="polite">
          {title}
        </h2>
        <div className="flex gap-2">
          {!isThisMonth && (
            <button type="button" className={button} onClick={() => onMonth(thisMonth)}>
              This month
            </button>
          )}
          <button type="button" className={button} onClick={() => shift(-1)} aria-label="Previous month">
            ←
          </button>
          <button type="button" className={button} onClick={() => shift(1)} aria-label="Next month">
            →
          </button>
        </div>
      </div>

      <table className="mt-4 w-full table-fixed border-collapse">
        <thead>
          <tr>
            {weeks[0].map((d) => (
              <th key={d} scope="col" className="pb-2 text-left text-sm font-semibold text-muted">
                {weekday.format(parseDay(d))}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week) => (
            <tr key={week[0]}>
              {week.map((d) => {
                const inMonth = parseDay(d).getMonth() === month.month;
                const items = onDay.get(d) ?? [];
                return (
                  <td
                    key={d}
                    className={`h-28 border border-border p-1 align-top ${inMonth ? "bg-white" : "bg-background"}`}
                  >
                    <DayNumber day={d} today={today} inMonth={inMonth} onPick={onPickDay} />
                    <ul className="mt-1 space-y-1">
                      {items.map((item) => (
                        <li key={item.id}>
                          <button
                            type="button"
                            onClick={() => onOpen(item)}
                            title={`${item.title} · ${item.course}`}
                            aria-label={`${item.title}, ${item.course}, ${dayLabel(d, today)}`}
                            className="block w-full truncate rounded border-l-4 bg-background px-1.5 py-0.5 text-left text-sm font-medium hover:underline"
                            style={{ borderColor: colors.get(item.course_id) }}
                          >
                            {item.title}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {legend.length > 1 && (
        <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-muted" aria-label="Course colors">
          {legend.map(([id, name]) => (
            <li key={id} className="flex items-center gap-2">
              <span aria-hidden className="size-3 rounded-full" style={{ background: colors.get(id) }} />
              {name}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function DayNumber({
  day,
  today,
  inMonth,
  onPick,
}: {
  day: string;
  today: string;
  inMonth: boolean;
  onPick?: (day: string) => void;
}) {
  const isToday = day === today;
  const number = parseDay(day).getDate();
  const style = `grid size-8 place-items-center rounded-full text-sm ${
    isToday ? "bg-accent font-bold text-white" : inMonth ? "" : "text-muted"
  }`;
  if (!onPick) return <span className={style}>{number}</span>;
  return (
    <button
      type="button"
      onClick={() => onPick(day)}
      aria-label={`Add a date on ${dayLabel(day, today)}`}
      aria-current={isToday ? "date" : undefined}
      className={`${style} ${isToday ? "" : "hover:bg-accent/10"}`}
    >
      {number}
    </button>
  );
}

function EditDialog({
  date,
  onClose,
  onSaved,
  onDeleted,
}: {
  date: CourseDate;
  onClose: () => void;
  onSaved: (date: CourseDate) => void;
  onDeleted: (date: CourseDate) => void;
}) {
  const [kind, setKind] = useState(date.kind);
  const [title, setTitle] = useState(date.title);
  const [on, setOn] = useState(date.on);
  const [chapters, setChapters] = useState(() => date.chapters.map((c) => c.id));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSaved(
        await api<CourseDate>(`/dates/${date.id}`, {
          method: "PUT",
          body: JSON.stringify({ kind, title: title.trim(), on, chapters } satisfies NewDate),
        }),
      );
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await apiFetch(`/dates/${date.id}`, { method: "DELETE" });
      onDeleted(date);
    } catch {
      setError("That couldn't be deleted. Please try again.");
      setBusy(false);
    }
  }

  const control = "mt-1 w-full rounded-lg border border-border bg-white px-3 py-3 text-lg";
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-heading"
        onSubmit={save}
        onClick={(e) => e.stopPropagation()}
        className="max-h-full w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"
      >
        <h2 id="edit-heading" className="text-xl font-semibold">
          {date.title}
        </h2>
        <p className="text-muted">{date.course}</p>
        <div className="mt-4 space-y-4">
          <label className="block">
            <span className="font-medium">Type</span>
            <select value={kind} onChange={(e) => setKind(e.target.value as DateKind)} className={control}>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {KIND_LABEL[k]}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="font-medium">What</span>
            <input
              type="text"
              required
              autoFocus
              maxLength={200}
              autoComplete="off"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className={control}
            />
          </label>
          <label className="block">
            <span className="font-medium">Date</span>
            <input
              type="date"
              required
              min={MIN_DAY}
              max={MAX_DAY}
              value={on}
              onChange={(e) => setOn(e.target.value)}
              className={control}
            />
          </label>
          <ChapterPicker courseId={date.course_id} selected={chapters} onChange={setChapters} />
          <FormError message={error} />
        </div>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={busy || !title.trim() || !on}
            className="rounded-lg bg-accent px-6 py-3 text-lg font-medium text-white hover:bg-accent-strong disabled:opacity-50"
          >
            Save
          </button>
          <button type="button" onClick={onClose} className="rounded-lg px-4 py-3 text-muted underline hover:text-foreground">
            Cancel
          </button>
          <button
            type="button"
            onClick={remove}
            disabled={busy}
            className="ml-auto rounded-lg px-4 py-3 text-danger underline disabled:opacity-50"
          >
            Delete
          </button>
        </div>
      </form>
    </div>
  );
}

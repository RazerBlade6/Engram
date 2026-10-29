"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent, type RefObject } from "react";

import { ChapterPicker } from "@/components/chapter-picker";
import { DateRow } from "@/components/dates";
import { FormError } from "@/components/form";
import { Toast, type ToastMessage } from "@/components/toast";
import { Button, ButtonLink } from "@/components/ui/button";
import { DateField } from "@/components/ui/date-field";
import { EmptyState } from "@/components/ui/empty-state";
import { CONTROL } from "@/components/ui/field";
import { RowList } from "@/components/ui/row-list";
import { Skeleton } from "@/components/ui/skeleton";
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
import { cx } from "@/lib/cx";
import { useProfile } from "@/lib/profile";

const KINDS = Object.keys(KIND_LABEL) as DateKind[];

type Month = { year: number; month: number };

const byDay = (a: CourseDate, b: CourseDate) => a.on.localeCompare(b.on) || a.course.localeCompare(b.course);

/** An entry tinted in its course's color, readable on the paper. */
const tint = (color: string | undefined) =>
  color ? `color-mix(in srgb, ${color} 13%, var(--paper))` : "var(--accent-soft)";

export function CalendarView() {
  const profile = useProfile();
  const [courses, setCourses] = useState<CourseSummary[] | null>(null);
  const [dates, setDates] = useState<CourseDate[] | null>(null);

  useEffect(() => {
    if (!profile) return;
    api<CourseSummary[]>("/courses").then(setCourses);
    api<CourseDate[]>("/dates").then(setDates);
  }, [profile]);

  if (!profile) return null;
  if (!courses || !dates) return <CalendarLoading />;
  return <Calendar courses={courses} initial={dates} />;
}

function CalendarLoading() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10" role="status" aria-label="Loading your calendar">
      <Skeleton className="h-9 w-48" />
      <Skeleton className="mt-6 h-36" />
      <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Skeleton className="h-[34rem]" />
        <Skeleton className="h-48" />
      </div>
    </main>
  );
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

  if (courses.length === 0) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="text-3xl font-bold">Calendar</h1>
        <div className="mt-8">
          <EmptyState
            title="No courses yet"
            action={
              <ButtonLink href="/" variant="secondary">
                Go to Today
              </ButtonLink>
            }
          >
            Add a course on Today, then put its exams, quizzes and deadlines here.
          </EmptyState>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-3xl font-bold">Calendar</h1>

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

      <div className="mt-10 grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <MonthGrid
          month={month}
          onMonth={setMonth}
          thisMonth={monthOf(today)}
          firstDay={firstDay}
          dates={dates}
          colors={colors}
          today={today}
          onPickDay={pickDay}
          onOpen={setEditing}
        />

        <section aria-labelledby="upcoming-heading">
          <h2 id="upcoming-heading" className="text-xl font-semibold">
            Coming up
          </h2>
          {next.length === 0 ? (
            <p className="mt-3 text-muted">Nothing coming up. Exams, quizzes and deadlines you add show up here.</p>
          ) : (
            <RowList className="mt-3">
              {next.map((d) => (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => setEditing(d)}
                    aria-label={`Change ${d.title}, ${d.course}`}
                    className="w-full rounded-control px-2 py-3 text-left transition-colors duration-150 hover:bg-foreground/5"
                  >
                    <DateRow date={d} color={colors.get(d.course_id)} today={today} />
                  </button>
                </li>
              ))}
            </RowList>
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

  return (
    <form
      onSubmit={submit}
      className="mt-6 rounded-control border border-border bg-surface p-5 shadow-card sm:p-6"
      aria-labelledby="add-heading"
    >
      <h2 id="add-heading" className="text-xl font-semibold">
        Add an exam, quiz or deadline
      </h2>
      {courses.length === 1 && <p className="text-muted">For {courses[0].title}. Or click a day on the calendar.</p>}
      {courses.length > 1 && <p className="text-muted">Or click a day on the calendar to fill in the date.</p>}
      <div className="mt-4 flex flex-wrap items-start gap-4">
        {courses.length > 1 && (
          <label className="flex flex-col">
            <span className="font-semibold">Course</span>
            <select
              value={course}
              onChange={(e) => {
                setCourse(e.target.value);
                setChapters([]);
              }}
              className={cx(CONTROL, "mt-2 w-auto")}
            >
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="flex flex-col">
          <span className="font-semibold">Type</span>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as DateKind)}
            className={cx(CONTROL, "mt-2 w-auto")}
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABEL[k]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex min-w-48 flex-1 flex-col">
          <span className="font-semibold">What</span>
          <input
            ref={what}
            type="text"
            required
            maxLength={200}
            autoComplete="off"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={`For example, ${KIND_EXAMPLE[kind]}`}
            className={cx(CONTROL, "mt-2")}
          />
        </label>
        <div className="w-60">
          <DateField label="Date" required value={day} onChange={onDay} />
        </div>
        {/* Level with the fields, not their hints. */}
        <Button type="submit" size="lg" disabled={busy || !title.trim() || !day} className="mt-8">
          Add
        </Button>
      </div>
      <div className="mt-3">
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

/** The month as a sheet of paper on the desk: a planner page, with each date in its course's color. */
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
  onPickDay: (day: string) => void;
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
  const title = new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric" }).format(
    new Date(month.year, month.month, 1),
  );
  const weekday = new Intl.DateTimeFormat("en-GB", { weekday: "short" });
  const isThisMonth = month.year === thisMonth.year && month.month === thisMonth.month;

  return (
    <section aria-labelledby="month-heading" className="min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="month-heading" className="text-xl font-semibold" aria-live="polite">
          {title}
        </h2>
        <div className="flex gap-2">
          {!isThisMonth && (
            <Button variant="secondary" onClick={() => onMonth(thisMonth)}>
              This month
            </Button>
          )}
          <Button variant="secondary" onClick={() => shift(-1)} aria-label="Previous month">
            ←
          </Button>
          <Button variant="secondary" onClick={() => shift(1)} aria-label="Next month">
            →
          </Button>
        </div>
      </div>

      <div className="mt-4 overflow-x-auto rounded-card bg-paper shadow-card">
        <table className="w-full min-w-[36rem] table-fixed border-collapse">
          <thead>
            <tr className="border-b-[1.5px] border-card-rule">
              {weeks[0].map((d) => (
                <th key={d} scope="col" className="px-2 pt-3 pb-2 text-left text-sm font-semibold text-muted">
                  {weekday.format(parseDay(d))}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {weeks.map((week) => (
              <tr key={week[0]} className="border-b border-border/70 last:border-b-0">
                {week.map((d) => {
                  const inMonth = parseDay(d).getMonth() === month.month;
                  const items = onDay.get(d) ?? [];
                  return (
                    <td
                      key={d}
                      className={cx(
                        "h-28 border-r border-border/70 p-1.5 align-top last:border-r-0",
                        !inMonth && "bg-desk/45",
                      )}
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
                              className="block w-full truncate rounded-sm border-l-[3px] px-1.5 py-0.5 text-left text-sm font-semibold transition-[filter] duration-150 hover:brightness-95"
                              style={{
                                borderColor: colors.get(item.course_id),
                                background: tint(colors.get(item.course_id)),
                              }}
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
      </div>

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
  onPick: (day: string) => void;
}) {
  const isToday = day === today;
  return (
    <button
      type="button"
      onClick={() => onPick(day)}
      aria-label={`Add a date on ${dayLabel(day, today)}`}
      aria-current={isToday ? "date" : undefined}
      className={cx(
        "grid size-8 place-items-center rounded-full text-sm tabular-nums transition-colors duration-150",
        isToday ? "bg-accent font-bold text-on-accent" : "hover:bg-accent-soft",
        !inMonth && !isToday && "text-muted",
      )}
    >
      {parseDay(day).getDate()}
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

  return (
    <div className="fade-in fixed inset-0 z-40 flex items-center justify-center bg-foreground/40 p-4" onClick={onClose}>
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-heading"
        onSubmit={save}
        onClick={(e) => e.stopPropagation()}
        className="rise-in max-h-full w-full max-w-lg overflow-y-auto rounded-control bg-paper p-6 shadow-lifted"
      >
        <h2 id="edit-heading" className="text-xl font-semibold">
          {date.title}
        </h2>
        <p className="text-muted">{date.course}</p>
        <div className="mt-5 space-y-5">
          <label className="block">
            <span className="font-semibold">Type</span>
            <select value={kind} onChange={(e) => setKind(e.target.value as DateKind)} className={cx(CONTROL, "mt-2")}>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {KIND_LABEL[k]}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="font-semibold">What</span>
            <input
              type="text"
              required
              autoFocus
              maxLength={200}
              autoComplete="off"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className={cx(CONTROL, "mt-2")}
            />
          </label>
          <DateField label="Date" required value={on} onChange={setOn} />
          <ChapterPicker courseId={date.course_id} selected={chapters} onChange={setChapters} />
          <FormError message={error} />
        </div>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <Button type="submit" size="lg" disabled={busy || !title.trim() || !on}>
            Save
          </Button>
          <Button variant="quiet" hint="Esc" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" onClick={remove} disabled={busy} className="ml-auto">
            Delete
          </Button>
        </div>
      </form>
    </div>
  );
}

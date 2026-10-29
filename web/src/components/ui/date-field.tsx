"use client";

import { useEffect, useId, useRef, useState } from "react";

import {
  isoDay,
  localFirstDay,
  longDayLabel,
  monthWeeks,
  parseDay,
  parseTypedDay,
  typedDay,
  FIRST_DAY,
  LAST_DAY,
} from "@/lib/calendar";
import { cx } from "@/lib/cx";

import { CONTROL } from "./field";

/**
 * A date typed day/month/year (D54), never in the browser's own order. The day it was read as
 * is written out underneath, and a small calendar beside it picks one by clicking.
 */
export function DateField({
  label,
  value,
  onChange,
  required,
}: {
  label: string;
  /** An ISO day, "2026-11-13", or "" when empty or not yet a real date. */
  value: string;
  onChange: (day: string) => void;
  required?: boolean;
}) {
  const id = useId();
  const [text, setText] = useState(() => (value ? typedDay(value) : ""));
  const [shown, setShown] = useState(value);
  const [left, setLeft] = useState(false);
  const [open, setOpen] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  // A day chosen elsewhere (a day on the month grid) replaces what's typed here.
  if (value !== shown) {
    setShown(value);
    if (value && value !== parseTypedDay(text)) setText(typedDay(value));
  }

  const day = parseTypedDay(text);
  const wrong = left && text.trim() !== "" && !day;

  function type(next: string) {
    setText(next);
    onChange(parseTypedDay(next) ?? "");
  }

  function pick(iso: string) {
    setText(typedDay(iso));
    onChange(iso);
    setOpen(false);
    input.current?.focus();
  }

  return (
    <div className="relative">
      <label htmlFor={id} className="block font-semibold">
        {label}
      </label>
      <div className="relative mt-2">
        <input
          ref={input}
          id={id}
          type="text"
          autoComplete="off"
          required={required}
          placeholder="dd/mm/yyyy"
          value={text}
          onChange={(e) => type(e.target.value)}
          onBlur={() => setLeft(true)}
          aria-invalid={wrong || undefined}
          aria-describedby={`${id}-hint`}
          className={cx(CONTROL, "pr-12 tabular-nums", wrong && "border-danger")}
        />
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-label="Choose from a calendar"
          aria-expanded={open}
          className="absolute top-1/2 right-2 grid size-9 -translate-y-1/2 place-items-center rounded-md text-muted transition-colors duration-150 hover:bg-foreground/5 hover:text-accent"
        >
          <CalendarIcon />
        </button>
      </div>
      <p id={`${id}-hint`} className={cx("mt-1 text-sm", wrong ? "text-danger" : "text-muted")} aria-live="polite">
        {day ? longDayLabel(day) : wrong ? "That isn't a date. Use day/month/year, like 13/11/2026." : "Day/month/year"}
      </p>
      {open && <MiniMonth selected={day} onPick={pick} onClose={() => setOpen(false)} />}
    </div>
  );
}

function CalendarIcon() {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="3" y="4.5" width="14" height="12.5" rx="2" />
      <path d="M3 8.5h14M7 2.5v4M13 2.5v4" strokeLinecap="round" />
    </svg>
  );
}

/** A small month to click a day in; Esc or a click elsewhere closes it. */
function MiniMonth({
  selected,
  onPick,
  onClose,
}: {
  selected: string | null;
  onPick: (day: string) => void;
  onClose: () => void;
}) {
  const [today] = useState(() => isoDay(new Date()));
  const [month, setMonth] = useState(() => {
    const d = parseDay(selected ?? today);
    return { year: d.getFullYear(), month: d.getMonth() };
  });
  const [firstDay] = useState(localFirstDay);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onPointer(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) onClose();
    }
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [onClose]);

  const weeks = monthWeeks(month.year, month.month, firstDay);
  const shift = (by: number) => {
    const d = new Date(month.year, month.month + by, 1);
    setMonth({ year: d.getFullYear(), month: d.getMonth() });
  };
  const title = new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric" }).format(
    new Date(month.year, month.month, 1),
  );
  const weekday = new Intl.DateTimeFormat("en-GB", { weekday: "narrow" });

  return (
    <div
      ref={root}
      role="dialog"
      aria-label="Choose a day"
      onKeyDown={(e) => {
        // Close just this, not a dialog it sits in.
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        }
      }}
      className="rise-in absolute right-0 z-30 mt-2 w-72 rounded-control border border-border bg-surface p-3 shadow-lifted"
    >
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => shift(-1)}
          aria-label="Previous month"
          className="grid size-9 place-items-center rounded-md hover:bg-foreground/5"
        >
          ‹
        </button>
        <p className="font-semibold" aria-live="polite">
          {title}
        </p>
        <button
          type="button"
          onClick={() => shift(1)}
          aria-label="Next month"
          className="grid size-9 place-items-center rounded-md hover:bg-foreground/5"
        >
          ›
        </button>
      </div>
      <div className="mt-2 grid grid-cols-7 text-center text-xs font-semibold text-muted">
        {weeks[0].map((d) => (
          <span key={d} aria-hidden>
            {weekday.format(parseDay(d))}
          </span>
        ))}
      </div>
      <div className="mt-1 grid grid-cols-7 gap-0.5">
        {weeks.flat().map((d) => {
          const inMonth = parseDay(d).getMonth() === month.month;
          const isSelected = d === selected;
          return (
            <button
              key={d}
              type="button"
              disabled={d < FIRST_DAY || d > LAST_DAY}
              onClick={() => onPick(d)}
              aria-label={longDayLabel(d)}
              aria-pressed={isSelected}
              autoFocus={isSelected}
              className={cx(
                "grid size-9 place-items-center justify-self-center rounded-full text-sm tabular-nums transition-colors duration-150",
                isSelected
                  ? "bg-accent font-semibold text-on-accent"
                  : cx("hover:bg-accent-soft", d === today && "font-bold text-accent ring-1 ring-accent"),
                !inMonth && !isSelected && "text-muted/70",
              )}
            >
              {parseDay(d).getDate()}
            </button>
          );
        })}
      </div>
    </div>
  );
}

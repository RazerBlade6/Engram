"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Toast, type ToastMessage } from "@/components/toast";
import { api, apiFetch } from "@/lib/api";
import { clozeParts, KIND_LABEL } from "@/lib/cards";
import { splitChapterTitle } from "@/lib/courses";
import { useProfile } from "@/lib/profile";
import {
  choiceRating,
  comesBackToday,
  FLAG_REASONS,
  passageParts,
  RATINGS,
  whenLabel,
  type Rating,
  type ReviewCard,
  type Reviewed,
} from "@/lib/review";

export function ReviewView() {
  const profile = useProfile();
  const [queue, setQueue] = useState<ReviewCard[] | null>(null);
  const [failed, setFailed] = useState(false);
  // Answers given this session (a card still being learned is answered more than once),
  // and cards finished for today.
  const [answers, setAnswers] = useState(0);
  const [finished, setFinished] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const [flagOpen, setFlagOpen] = useState(false);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const toastId = useRef(0);

  useEffect(() => {
    if (!profile) return;
    api<{ cards: ReviewCard[] }>("/review/queue")
      .then((body) => setQueue(body.cards))
      .catch(() => setFailed(true));
  }, [profile]);

  const show = useCallback((text: string, undo?: () => void) => {
    toastId.current += 1;
    setToast({ id: toastId.current, text, undo });
  }, []);
  const hideToast = useCallback(() => setToast(null), []);

  const card = queue?.[0] ?? null;
  const answered = card?.kind === "mcq" ? picked !== null : revealed;

  const next = useCallback(() => {
    setRevealed(false);
    setPicked(null);
    setFlagOpen(false);
  }, []);

  const rate = useCallback(
    async (rating: Rating) => {
      if (!card) return;
      // Move on at once; the rating is saved in the background.
      setQueue((q) => q && q.slice(1));
      setAnswers((n) => n + 1);
      next();
      try {
        const saved = await api<Reviewed>(`/cards/${card.id}/review`, {
          method: "POST",
          body: JSON.stringify({ rating }),
        });
        if (comesBackToday(saved.due, new Date())) {
          // Still being learned: it comes back later in this session.
          setQueue((q) => q && [...q, { ...card, new: false, next: saved.next }]);
        } else {
          setFinished((n) => n + 1);
        }
      } catch {
        setQueue((q) => q && [card, ...q]);
        setAnswers((n) => n - 1);
        show("That rating couldn't be saved. Please try again.");
      }
    },
    [card, next, show],
  );

  const flag = useCallback(
    async (reason: string) => {
      if (!card) return;
      setQueue((q) => q && q.slice(1));
      next();
      try {
        await apiFetch(`/cards/${card.id}/flag`, { method: "PUT", body: JSON.stringify({ reason }) });
        show("Thanks. That card is out of your reviews.", async () => {
          await apiFetch(`/cards/${card.id}/flag`, { method: "DELETE" });
          setQueue((q) => q && [card, ...q]);
        });
      } catch {
        setQueue((q) => q && [card, ...q]);
        show("That card couldn't be reported. Please try again.");
      }
    },
    [card, next, show],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (!card || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.target instanceof HTMLElement && event.target.matches("input, textarea")) return;
      if (event.key === "Escape") {
        setFlagOpen(false);
        return;
      }
      if (event.key === "f" || event.key === "F") {
        setFlagOpen((open) => !open);
        return;
      }
      if (event.key === " " || event.key === "Enter") {
        // Enter on a focused button already clicks it.
        if (event.key === "Enter" && event.target instanceof HTMLButtonElement) return;
        event.preventDefault();
        if (card.kind === "mcq" && picked !== null) rate(choiceRating(card, picked));
        else if (card.kind !== "mcq") setRevealed(true);
        return;
      }
      if (/^[1-4]$/.test(event.key)) {
        const n = Number(event.key);
        if (card.kind === "mcq" && picked === null) setPicked(card.choices[n - 1] ?? null);
        else if (card.kind !== "mcq" && revealed) rate(n as Rating);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [card, picked, revealed, rate]);

  if (!profile) return null;
  if (failed) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-16">
        <p>Your reviews couldn&apos;t be loaded. Please try again.</p>
        <Link href="/" className="mt-4 inline-block text-accent underline">
          Back to Today
        </Link>
      </main>
    );
  }
  if (!queue) return null;

  const total = answers + queue.length;
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex flex-wrap items-center gap-6">
        <Link href="/" className="text-muted underline hover:text-foreground">
          {card ? "Stop for now" : "Back to Today"}
        </Link>
        {card && (
          <div className="flex min-w-40 flex-1 items-center gap-3 text-muted tabular-nums">
            <span>
              {answers} of {total}
            </span>
            <div
              className="h-1.5 flex-1 overflow-hidden rounded-full bg-border"
              role="progressbar"
              aria-valuenow={answers}
              aria-valuemax={total}
              aria-label="Cards reviewed"
            >
              <div className="h-full bg-accent transition-[width]" style={{ width: `${(answers / total) * 100}%` }} />
            </div>
          </div>
        )}
      </div>

      {card ? (
        <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
          <section className="flex min-h-80 flex-col gap-6 rounded-2xl border border-border bg-white p-8" aria-live="polite">
            <CardTag card={card} />
            <CardFront card={card} revealed={revealed} picked={picked} onPick={setPicked} />
            <div className="mt-auto flex flex-col gap-4">
              <CardActions
                card={card}
                answered={answered}
                picked={picked}
                onReveal={() => setRevealed(true)}
                onRate={rate}
              />
            </div>
            <FlagMenu open={flagOpen} onToggle={() => setFlagOpen((o) => !o)} onFlag={flag} />
          </section>
          <SourcePanel card={card} answered={answered} />
        </div>
      ) : (
        <section className="mt-12 max-w-2xl">
          <h1 className="text-3xl font-semibold">That&apos;s everything for now.</h1>
          <p className="mt-3 text-lg text-muted">
            {finished ? `You reviewed ${finished} ${finished === 1 ? "card" : "cards"}. ` : ""}
            New cards and the ones due again will be here next time.
          </p>
          <Link
            href="/"
            className="mt-6 inline-block rounded-lg bg-accent px-5 py-3 font-medium text-white hover:bg-accent-strong"
          >
            Back to Today
          </Link>
        </section>
      )}

      <Toast key={toast?.id} toast={toast} onDone={hideToast} />
    </main>
  );
}

function CardTag({ card }: { card: ReviewCard }) {
  const chapter = card.chapter ? splitChapterTitle(card.chapter) : null;
  const parts = [
    card.course,
    chapter && (chapter.number ? `Chapter ${chapter.number}` : chapter.title),
    KIND_LABEL[card.kind],
    card.new && "New",
  ].filter(Boolean);
  return <div className="text-sm text-muted">{parts.join(" · ")}</div>;
}

function CardFront({
  card,
  revealed,
  picked,
  onPick,
}: {
  card: ReviewCard;
  revealed: boolean;
  picked: string | null;
  onPick: (choice: string) => void;
}) {
  const front = "text-2xl leading-snug sm:text-[1.75rem]";
  if (card.kind === "cloze") {
    return (
      <p className={front}>
        {clozeParts(card.prompt).map((part, i) =>
          !part.hidden ? (
            <span key={i}>{part.text}</span>
          ) : revealed ? (
            <span key={i} className="border-b-2 border-accent font-medium text-accent">
              {part.text}
            </span>
          ) : (
            <span key={i} aria-label="blank" className="inline-block w-[4.5em] border-b-2 border-foreground" />
          ),
        )}
      </p>
    );
  }
  if (card.kind === "mcq") {
    return (
      <>
        <p className={front}>{card.prompt}</p>
        <div className="flex flex-col gap-2.5">
          {card.choices.map((choice, i) => {
            const answered = picked !== null;
            const tone =
              answered && choice === card.answer
                ? "border-success bg-success/10"
                : answered && choice === picked
                  ? "border-danger bg-danger-soft"
                  : "border-border hover:border-accent";
            return (
              <button
                key={choice}
                type="button"
                disabled={answered}
                onClick={() => onPick(choice)}
                className={`flex min-h-13 items-center gap-3.5 rounded-lg border px-4 py-3 text-left text-lg ${tone}`}
              >
                <span className="grid size-7 shrink-0 place-items-center rounded-md border border-border text-sm font-semibold text-muted">
                  {i + 1}
                </span>
                {choice}
              </button>
            );
          })}
        </div>
      </>
    );
  }
  return (
    <>
      <p className={front}>{card.prompt}</p>
      {revealed && (
        <p className="border-t border-dashed border-border pt-5 text-xl leading-relaxed">{card.answer}</p>
      )}
    </>
  );
}

function CardActions({
  card,
  answered,
  picked,
  onReveal,
  onRate,
}: {
  card: ReviewCard;
  answered: boolean;
  picked: string | null;
  onReveal: () => void;
  onRate: (rating: Rating) => void;
}) {
  const now = new Date();
  if (card.kind === "mcq") {
    if (picked === null) return <p className="text-center text-muted">Pick an answer, or press 1–4</p>;
    const rating = choiceRating(card, picked);
    const when = whenLabel(card.next[rating], now);
    return (
      <>
        <p role="status" className={`text-center text-lg ${rating === 3 ? "text-success" : "text-danger"}`}>
          {rating === 3 ? "Correct." : `Not quite. It's ${card.answer}.`}{" "}
          {when === "see it again soon" ? "You'll see this one again soon." : `You'll see it again ${when}.`}
        </p>
        <div className="flex justify-center">
          <PrimaryButton onClick={() => onRate(rating)} hint="Space">
            Continue
          </PrimaryButton>
        </div>
      </>
    );
  }
  if (!answered) {
    return (
      <div className="flex justify-center">
        <PrimaryButton onClick={onReveal} hint="Space">
          Show answer
        </PrimaryButton>
      </div>
    );
  }
  return (
    <>
      <p className="text-center text-muted">How well did you remember it?</p>
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {RATINGS.map(({ rating, label, tone }) => (
          <button
            key={rating}
            type="button"
            onClick={() => onRate(rating)}
            className="flex min-h-16 flex-col items-center gap-0.5 rounded-lg border border-border bg-white px-2 py-3 hover:border-accent hover:bg-accent/5"
          >
            <b className={`text-lg ${tone}`}>{label}</b>
            <small className="text-sm text-muted">{whenLabel(card.next[rating], now)}</small>
            <kbd className="text-xs text-muted">{rating}</kbd>
          </button>
        ))}
      </div>
    </>
  );
}

function PrimaryButton({ onClick, hint, children }: { onClick: () => void; hint: string; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-3 rounded-lg bg-accent px-6 py-3 text-lg font-medium text-white hover:bg-accent-strong"
    >
      {children}
      <kbd className="rounded border border-white/40 px-1.5 text-sm font-normal">{hint}</kbd>
    </button>
  );
}

function FlagMenu({
  open,
  onToggle,
  onFlag,
}: {
  open: boolean;
  onToggle: () => void;
  onFlag: (reason: string) => void;
}) {
  return (
    <div className="relative border-t border-border pt-4">
      {open && (
        <div
          role="menu"
          aria-label="Report a problem"
          className="absolute top-full left-0 z-10 mt-2 w-full max-w-sm rounded-lg border border-border bg-white p-3 shadow-lg"
        >
          <p className="px-2 pb-2 text-sm text-muted">What&apos;s wrong with this card? It won&apos;t come up again.</p>
          {FLAG_REASONS.map(({ reason, label, detail }) => (
            <button
              key={reason}
              type="button"
              role="menuitem"
              onClick={() => onFlag(reason)}
              className="block w-full rounded-md px-2 py-2 text-left hover:bg-accent/5"
            >
              <span className="block font-medium">{label}</span>
              <span className="block text-sm text-muted">{detail}</span>
            </button>
          ))}
        </div>
      )}
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex items-center gap-2 text-muted hover:text-foreground"
      >
        Something wrong with this card? <kbd className="rounded border border-border px-1.5 text-xs">F</kbd>
      </button>
    </div>
  );
}

function SourcePanel({ card, answered }: { card: ReviewCard; answered: boolean }) {
  const source = card.source;
  if (!source) return null;
  const where = [source.heading_path.at(-1), source.page !== null && `page ${source.page}`].filter(Boolean).join(" · ");
  if (!answered) {
    return (
      <aside aria-label="Where this comes from" className="rounded-2xl border border-dashed border-border p-6">
        <p className="font-semibold">From {source.book}</p>
        <p className="mt-2 text-muted">The passage this card comes from shows up here once you&apos;ve answered.</p>
      </aside>
    );
  }
  return <Passage source={source} where={where} />;
}

function Passage({ source, where }: { source: NonNullable<ReviewCard["source"]>; where: string }) {
  const { before, marked, after } = passageParts(source);
  const box = useRef<HTMLParagraphElement>(null);
  const mark = useRef<HTMLElement>(null);

  // Bring the quoted words into view; scrolling the box alone, not the page.
  useEffect(() => {
    const container = box.current;
    if (!container || !mark.current) return;
    const offset = mark.current.getBoundingClientRect().top - container.getBoundingClientRect().top;
    container.scrollTop += Math.max(0, offset - 48);
  }, [source]);

  return (
    <aside aria-label="Where this comes from" className="rounded-2xl border border-border bg-white p-6">
      <p className="font-semibold">From {source.book}</p>
      {where && <p className="text-sm text-muted">{where}</p>}
      <p ref={box} className="relative mt-4 max-h-[28rem] overflow-y-auto text-lg leading-relaxed whitespace-pre-line">
        {before}
        {marked && (
          <mark ref={mark} className="rounded bg-accent/15 px-0.5 text-foreground">
            {marked}
          </mark>
        )}
        {after}
      </p>
    </aside>
  );
}

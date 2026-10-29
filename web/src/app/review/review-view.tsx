"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { Toast, type ToastMessage } from "@/components/toast";
import { Button, ButtonLink } from "@/components/ui/button";
import { FlipCard } from "@/components/ui/flip-card";
import { IndexCard } from "@/components/ui/index-card";
import { Kbd } from "@/components/ui/kbd";
import { Notice } from "@/components/ui/notice";
import { ProgressBar } from "@/components/ui/progress";
import { RatingButton } from "@/components/ui/rating-button";
import { Skeleton } from "@/components/ui/skeleton";
import { Highlight, SourceBox } from "@/components/ui/source-box";
import { api, apiFetch } from "@/lib/api";
import { courseColors } from "@/lib/calendar";
import { clozeParts, KIND_LABEL } from "@/lib/cards";
import { splitChapterTitle, type CourseSummary } from "@/lib/courses";
import { cx } from "@/lib/cx";
import { useProfile } from "@/lib/profile";
import { msSince } from "@/lib/usage";
import {
  choiceRating,
  comesBackToday,
  FLAG_REASONS,
  passageParts,
  RATINGS,
  requeue,
  whenLabel,
  type Rating,
  type ReviewCard,
  type ReviewOrder,
  type ReviewQueue,
  type ReviewSession,
  type Reviewed,
} from "@/lib/review";

export function ReviewView() {
  const profile = useProfile();
  const session: ReviewSession = useSearchParams().get("session") === "quiz" ? "quiz" : "review";
  const [queue, setQueue] = useState<ReviewCard[] | null>(null);
  const [order, setOrder] = useState<ReviewOrder>("mixed");
  const [colors, setColors] = useState<Map<string, string>>(new Map());
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
  // When the current card appeared, for how long it took to rate (usage log).
  const shownAt = useRef(0);

  useEffect(() => {
    if (!profile) return;
    api<ReviewQueue>(`/review/queue?session=${session}`)
      .then((body) => {
        setOrder(body.order);
        setQueue(body.cards);
      })
      .catch(() => setFailed(true));
    // Each course's color, the same as on the calendar; the cards work without them.
    api<CourseSummary[]>("/courses")
      .then((courses) => setColors(courseColors(courses)))
      .catch(() => {});
  }, [profile, session]);

  const show = useCallback((text: string, undo?: () => void) => {
    toastId.current += 1;
    setToast({ id: toastId.current, text, undo });
  }, []);
  const hideToast = useCallback(() => setToast(null), []);

  const card = queue?.[0] ?? null;
  const answered = card?.kind === "mcq" ? picked !== null : revealed;

  useEffect(() => {
    shownAt.current = performance.now();
  }, [card?.id, answers]);

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
          body: JSON.stringify({ rating, ms: msSince(shownAt.current) }),
        });
        if (comesBackToday(saved.due, new Date())) {
          // Still being learned: it comes back later in this session.
          setQueue((q) => q && requeue(q, { ...card, new: false, next: saved.next }, order));
        } else {
          setFinished((n) => n + 1);
        }
      } catch {
        setQueue((q) => q && [card, ...q]);
        setAnswers((n) => n - 1);
        show("That rating couldn't be saved. Please try again.");
      }
    },
    [card, next, show, order],
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
        <Notice
          tone="error"
          action={
            <Button variant="secondary" onClick={() => window.location.reload()}>
              Try again
            </Button>
          }
        >
          Your reviews couldn&apos;t be loaded. Check your connection and try again.
        </Notice>
        <ButtonLink href="/" variant="quiet" className="mt-4 -ml-4">
          Back to Today
        </ButtonLink>
      </main>
    );
  }
  if (!queue) return <ReviewLoading />;

  const total = answers + queue.length;
  return (
    <main className="mx-auto max-w-6xl px-6 py-6 sm:py-8">
      <div className="flex items-center gap-4">
        <ButtonLink href="/" variant="quiet" className="-ml-4 shrink-0">
          {card ? "Stop for now" : "Back to Today"}
        </ButtonLink>
        {card && (
          <div className="flex flex-1 items-center gap-3 text-muted tabular-nums">
            <span className="shrink-0">
              {answers} of {total}
            </span>
            <ProgressBar value={answers} max={total} label="Cards reviewed" className="flex-1" />
          </div>
        )}
      </div>

      {card ? (
        <div className="mt-8 grid items-start gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          {/* A new key per answer, so each card arrives face up instead of turning back. */}
          <div key={`${card.id}-${answers}`} className="rise-in flex flex-col gap-6">
            <Card
              card={card}
              color={colors.get(card.course_id)}
              revealed={revealed}
              picked={picked}
              onPick={setPicked}
              report={
                <ReportMenu
                  open={flagOpen}
                  onToggle={() => setFlagOpen((o) => !o)}
                  onClose={() => setFlagOpen(false)}
                  onFlag={flag}
                />
              }
            />
            <CardActions
              card={card}
              answered={answered}
              picked={picked}
              onReveal={() => setRevealed(true)}
              onRate={rate}
            />
          </div>
          <SourcePanel card={card} answered={answered} />
        </div>
      ) : (
        <section className="rise-in mt-16 max-w-2xl">
          <h1 className="text-3xl font-bold">That&apos;s everything for now.</h1>
          <p className="mt-3 text-lg text-muted">
            {finished ? `You reviewed ${finished} ${finished === 1 ? "card" : "cards"}. ` : ""}
            New cards and the ones due again will be here next time.
          </p>
          <ButtonLink href="/" size="lg" className="mt-6">
            Back to Today
          </ButtonLink>
        </section>
      )}

      <Toast key={toast?.id} toast={toast} onDone={hideToast} />
    </main>
  );
}

function ReviewLoading() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-6 sm:py-8" role="status" aria-label="Loading your reviews">
      <Skeleton className="h-11 w-full max-w-md" />
      <div className="mt-8 grid items-start gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <Skeleton className="h-80" />
        <Skeleton className="h-48" />
      </div>
    </main>
  );
}

/** The card on the desk. Flashcards turn over to show the answer; multiple choice doesn't. */
function Card({
  card,
  color,
  revealed,
  picked,
  onPick,
  report,
}: {
  card: ReviewCard;
  color: string | undefined;
  revealed: boolean;
  picked: string | null;
  onPick: (choice: string) => void;
  report: ReactNode;
}) {
  const face = (children: ReactNode, pile = true) => (
    <IndexCard label={card.course} labelColor={color} corner={report} pile={pile}>
      <CardMeta card={card} />
      <div className="mt-3 min-h-44">{children}</div>
    </IndexCard>
  );
  if (card.kind === "mcq") return face(<Choices card={card} picked={picked} onPick={onPick} />);
  // The pile underneath stays put while the top card turns over.
  return (
    <div className="relative isolate">
      <div aria-hidden className="index-card-under -z-10" />
      <FlipCard
        flipped={revealed}
        front={face(<Front card={card} />, false)}
        back={face(<Back card={card} />, false)}
      />
    </div>
  );
}

function CardMeta({ card }: { card: ReviewCard }) {
  const chapter = card.chapter ? splitChapterTitle(card.chapter) : null;
  const parts = [chapter && (chapter.number ? `Chapter ${chapter.number}` : chapter.title), KIND_LABEL[card.kind]];
  return (
    <p className="flex flex-wrap items-center gap-x-2 text-sm text-muted">
      {parts.filter(Boolean).join(" · ")}
      {card.new && (
        <span className="rounded-full bg-accent-soft px-2 text-xs leading-5 font-semibold text-accent">New</span>
      )}
    </p>
  );
}

const PROMPT = "font-read text-2xl leading-snug sm:text-[1.75rem]";

function Front({ card }: { card: ReviewCard }) {
  if (card.kind === "cloze") return <Cloze prompt={card.prompt} filled={false} />;
  return <p className={PROMPT}>{card.prompt}</p>;
}

/** The back repeats the question, smaller, above the answer. */
function Back({ card }: { card: ReviewCard }) {
  if (card.kind === "cloze") return <Cloze prompt={card.prompt} filled />;
  return (
    <>
      <p className="font-read text-lg leading-snug text-muted">{card.prompt}</p>
      <p className="mt-5 font-read text-2xl leading-snug font-semibold">{card.answer}</p>
    </>
  );
}

function Cloze({ prompt, filled }: { prompt: string; filled: boolean }) {
  return (
    <p className={PROMPT}>
      {clozeParts(prompt).map((part, i) =>
        !part.hidden ? (
          <span key={i}>{part.text}</span>
        ) : filled ? (
          <span key={i} className="border-b-2 border-accent font-semibold text-accent">
            {part.text}
          </span>
        ) : (
          <span key={i} aria-label="blank" className="inline-block w-[4.5em] border-b-2 border-foreground" />
        ),
      )}
    </p>
  );
}

/**
 * Multiple choice grades itself in the rating inks: the right answer in "Got it" teal, a
 * wrong pick in "Forgot" plum. Never red, so a wrong answer doesn't read as failing.
 */
function Choices({
  card,
  picked,
  onPick,
}: {
  card: ReviewCard;
  picked: string | null;
  onPick: (choice: string) => void;
}) {
  const answered = picked !== null;
  return (
    <>
      <p className={PROMPT}>{card.prompt}</p>
      <div className="mt-6 flex flex-col gap-2.5">
        {card.choices.map((choice, i) => {
          const ink = answered && choice === card.answer ? 3 : answered && choice === picked ? 1 : null;
          return (
            <button
              key={choice}
              type="button"
              disabled={answered}
              onClick={() => onPick(choice)}
              style={
                ink
                  ? {
                      color: `var(--rate-${ink})`,
                      background: `var(--rate-${ink}-soft)`,
                      borderColor: `var(--rate-${ink}-line)`,
                    }
                  : undefined
              }
              className={cx(
                "flex min-h-13 items-center gap-3.5 rounded-control border px-4 py-3 text-left text-lg transition-colors duration-150",
                ink ? "font-semibold" : "border-border-strong bg-surface",
                !answered && "hover:border-accent hover:bg-accent-soft/40",
                answered && !ink && "opacity-60",
              )}
            >
              <Kbd>{i + 1}</Kbd>
              {choice}
            </button>
          );
        })}
      </div>
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
      <div className="flex flex-col items-center gap-4">
        <p role="status" className="text-center text-lg font-semibold" style={{ color: `var(--rate-${rating})` }}>
          {rating === 3 ? "Correct." : `Not quite. It's ${card.answer}.`}{" "}
          <span className="font-normal text-muted">
            {when === "see it again soon" ? "You'll see this one again soon." : `You'll see it again ${when}.`}
          </span>
        </p>
        <Button size="lg" hint="Space" onClick={() => onRate(rating)}>
          Continue
        </Button>
      </div>
    );
  }
  if (!answered) {
    return (
      <div className="flex justify-center">
        <Button size="lg" hint="Space" onClick={onReveal}>
          Show answer
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-center text-muted">How well did you remember it?</p>
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {RATINGS.map(({ rating, label }) => (
          <RatingButton
            key={rating}
            rating={rating}
            label={label}
            when={whenLabel(card.next[rating], now)}
            onClick={() => onRate(rating)}
          />
        ))}
      </div>
    </div>
  );
}

/** A small control in the card's corner: rarely needed, so it stays out of the way (D52). */
function ReportMenu({
  open,
  onToggle,
  onClose,
  onFlag,
}: {
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  onFlag: (reason: string) => void;
}) {
  const root = useRef<HTMLDivElement>(null);

  // A click anywhere else closes the menu.
  useEffect(() => {
    if (!open) return;
    function onPointer(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) onClose();
    }
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open, onClose]);

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-muted transition-colors duration-150 hover:bg-foreground/5 hover:text-foreground"
      >
        Report <Kbd>F</Kbd>
      </button>
      {open && (
        <div
          role="menu"
          aria-label="Report a problem with this card"
          className="rise-in absolute top-full right-0 z-20 mt-2 w-80 max-w-[calc(100vw-3rem)] rounded-control border border-border bg-surface p-2 shadow-lifted"
        >
          <p className="px-3 pt-1 pb-2 text-sm text-muted">
            What&apos;s wrong with this card? It won&apos;t come up again.
          </p>
          {FLAG_REASONS.map(({ reason, label, detail }) => (
            <button
              key={reason}
              type="button"
              role="menuitem"
              onClick={() => onFlag(reason)}
              className="block w-full rounded-md px-3 py-2 text-left hover:bg-accent-soft/60"
            >
              <span className="block font-semibold">{label}</span>
              <span className="block text-sm text-muted">{detail}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function SourcePanel({ card, answered }: { card: ReviewCard; answered: boolean }) {
  const source = card.source;
  if (!source) return null;
  if (!answered) {
    return (
      <SourceBox quiet title={`From ${source.book}`}>
        <p className="font-sans text-base text-muted">
          The passage this card comes from shows up here once you&apos;ve answered.
        </p>
      </SourceBox>
    );
  }
  return <Passage source={source} />;
}

function Passage({ source }: { source: NonNullable<ReviewCard["source"]> }) {
  const { before, marked, after } = passageParts(source);
  const where = [source.heading_path.at(-1), source.page !== null && `page ${source.page}`].filter(Boolean).join(" · ");
  const box = useRef<HTMLDivElement>(null);
  const mark = useRef<HTMLElement>(null);

  // Bring the quoted words into view; scrolling the box alone, not the page.
  useEffect(() => {
    const container = box.current;
    if (!container || !mark.current) return;
    const offset = mark.current.getBoundingClientRect().top - container.getBoundingClientRect().top;
    container.scrollTop += Math.max(0, offset - 48);
  }, [source]);

  return (
    <SourceBox title={`From ${source.book}`} where={where} className="rise-in">
      <div ref={box} className="relative max-h-[28rem] overflow-y-auto whitespace-pre-line">
        {before}
        {marked && <Highlight ref={mark}>{marked}</Highlight>}
        {after}
      </div>
    </SourceBox>
  );
}

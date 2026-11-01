"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";

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
  answerText,
  choiceRating,
  comesBackToday,
  FLAG_REASONS,
  passageParts,
  RATINGS,
  requeue,
  textStep,
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
  const [order, setOrder] = useState<ReviewOrder>("blocked");
  const [colors, setColors] = useState<Map<string, string>>(new Map());
  const [failed, setFailed] = useState(false);
  // Answers given this session (a card still being learned is answered more than once),
  // and cards finished for today.
  const [answers, setAnswers] = useState(0);
  const [finished, setFinished] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const [flagOpen, setFlagOpen] = useState(false);
  // The card just answered, sliding off the pile while the next one shows underneath.
  const [leaving, setLeaving] = useState<Leaving | null>(null);
  const leavingId = useRef(0);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const toastId = useRef(0);
  // When the current card appeared, for how long it took to rate (usage log).
  const shownAt = useRef(0);
  // The pile, and the buttons under it: pinned to the bottom of the screen when an unusually
  // long card would push them out of sight.
  const pile = useRef<HTMLDivElement>(null);
  const actions = useRef<HTMLDivElement>(null);
  const actionsHeight = useOffScreen(pile, actions, [queue?.[0]?.id, revealed, picked, flagOpen]);

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
    if (card) {
      leavingId.current += 1;
      setLeaving({ id: leavingId.current, card, revealed, picked });
    }
    setRevealed(false);
    setPicked(null);
    setFlagOpen(false);
  }, [card, revealed, picked]);

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
  const mcqAnswered = card?.kind === "mcq" && picked !== null;
  // Multiple choice is answered on the card itself, so until then there's nothing to pin.
  const pinnable = !(card?.kind === "mcq" && picked === null);
  const pinned = pinnable && actionsHeight !== null;
  return (
    <main
      className="mx-auto max-w-6xl px-6 py-6 max-sm:px-4 max-sm:pb-40 sm:py-8"
      // Room to scroll the source clear of the pinned buttons.
      style={pinned ? { paddingBottom: actionsHeight + 32 } : undefined}
    >
      <div className="flex items-center gap-4">
        <ButtonLink href="/" variant="secondary" className="shrink-0">
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
          <div className="flex flex-col gap-6">
            {/* The pile. The next card is already underneath, so only the answered one moves. */}
            <div ref={pile} className="relative isolate">
              <div aria-hidden className="index-card-under -z-10" />
              {/* A new key per answer, so each card arrives face up instead of turning back. */}
              <Card
                key={`${card.id}-${answers}`}
                card={card}
                color={colors.get(card.course_id)}
                revealed={revealed}
                picked={picked}
                onPick={setPicked}
                report={<ReportButton open={flagOpen} onToggle={() => setFlagOpen((o) => !o)} />}
              />
              {leaving && (
                <div
                  key={leaving.id}
                  aria-hidden
                  inert
                  className="card-leave absolute inset-x-0 top-0 z-10"
                  onAnimationEnd={(event) => event.target === event.currentTarget && setLeaving(null)}
                >
                  <Card
                    card={leaving.card}
                    color={colors.get(leaving.card.course_id)}
                    revealed={leaving.revealed}
                    picked={leaving.picked}
                    onPick={() => {}}
                    report={<ReportButton open={false} onToggle={() => {}} />}
                  />
                </div>
              )}
            </div>
            {flagOpen && <ReportPanel onFlag={flag} onCancel={() => setFlagOpen(false)} />}
            {/* On a phone the actions are pinned to the bottom of the screen, so the source can follow
                the card directly and both stay in reach while reading (D68). Elsewhere they're pinned
                only when a long card would push them out of sight. */}
            <div
              className={cx(
                pinnable &&
                  "max-sm:fixed max-sm:inset-x-0 max-sm:bottom-0 max-sm:z-20 max-sm:border-t max-sm:border-border max-sm:bg-desk/95 max-sm:px-4 max-sm:pt-3 max-sm:pb-[max(0.75rem,env(safe-area-inset-bottom))] max-sm:backdrop-blur-sm",
                pinned &&
                  "sm:fixed sm:inset-x-0 sm:bottom-0 sm:z-20 sm:border-t sm:border-border sm:bg-desk/95 sm:py-3 sm:backdrop-blur-sm",
                mcqAnswered && "lg:hidden",
              )}
            >
              {/* Pinned, the buttons stay in line with the card above them. */}
              <div
                className={cx(
                  pinned &&
                    "sm:mx-auto sm:grid sm:max-w-6xl sm:gap-x-10 sm:px-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]",
                )}
              >
                <div ref={actions}>
                  <CardActions
                    card={card}
                    answered={answered}
                    picked={picked}
                    onReveal={() => setRevealed(true)}
                    onRate={rate}
                  />
                </div>
              </div>
            </div>
          </div>
          <div className="flex flex-col gap-4">
            {/* A long multiple-choice card fills a short laptop screen on its own, so beside it the
                result and Continue sit above the source, where they're always in view (D63). */}
            {mcqAnswered && (
              <div className="max-lg:hidden">
                <CardActions card={card} answered={answered} picked={picked} onReveal={() => {}} onRate={rate} />
              </div>
            )}
            <SourcePanel card={card} answered={answered} />
          </div>
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

      <Toast key={toast?.id} toast={toast} onDone={hideToast} above="bottom-6 max-sm:bottom-40" />
    </main>
  );
}

/**
 * The height of the buttons under the card when they'd fall below the bottom of the screen,
 * measured from where they'd sit, under the pile; null when they fit. Re-measured when the
 * card, the pile's size or the window changes.
 */
function useOffScreen(
  pile: RefObject<HTMLDivElement | null>,
  actions: RefObject<HTMLDivElement | null>,
  deps: unknown[],
): number | null {
  const [height, setHeight] = useState<number | null>(null);

  useLayoutEffect(() => {
    const measure = () => {
      if (!pile.current || !actions.current) return setHeight(null);
      const below = pile.current.getBoundingClientRect().bottom + window.scrollY;
      const tall = actions.current.offsetHeight;
      // The column's gap between the pile and the buttons (it shrinks on short screens).
      const column = pile.current.parentElement;
      const gap = column ? parseFloat(getComputedStyle(column).rowGap) || 0 : 0;
      // Hidden (0 tall) when Continue sits beside the card instead.
      setHeight(tall > 0 && below + gap + tall > window.innerHeight ? tall : null);
    };
    measure();
    const observer = new ResizeObserver(measure);
    if (pile.current) observer.observe(pile.current);
    if (actions.current) observer.observe(actions.current);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-measured per card and state
  }, deps);

  return height;
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

type Leaving = { id: number; card: ReviewCard; revealed: boolean; picked: string | null };

/**
 * One card, without the pile beneath it. Flashcards turn over to show the answer; multiple
 * choice doesn't.
 */
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
  const face = (children: ReactNode) => (
    <IndexCard label={card.course} labelColor={color} corner={report} pile={false}>
      <CardMeta card={card} />
      <div className="mt-3 min-h-44">{children}</div>
    </IndexCard>
  );
  if (card.kind === "mcq") return face(<Choices card={card} picked={picked} onPick={onPick} />);
  return <FlipCard flipped={revealed} front={face(<Front card={card} />)} back={face(<Back card={card} />)} />;
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

/** Card text, a size smaller for each step down (see `textStep`). */
const STEP = ["text-2xl sm:text-[1.75rem]", "text-2xl", "text-xl sm:text-[1.375rem]"];
const prompt = (text: string, quiz = false) => cx("font-read leading-snug", STEP[textStep(text, quiz)]);

function Front({ card }: { card: ReviewCard }) {
  if (card.kind === "cloze") return <Cloze text={card.prompt} filled={false} />;
  return <p className={prompt(card.prompt)}>{card.prompt}</p>;
}

/** The back repeats the question, smaller, above the answer. */
function Back({ card }: { card: ReviewCard }) {
  if (card.kind === "cloze") return <Cloze text={card.prompt} filled />;
  return (
    <>
      <p className="font-read text-lg leading-snug text-muted">{card.prompt}</p>
      <p className={cx("mt-5 font-semibold", prompt(card.answer))}>{card.answer}</p>
    </>
  );
}

function Cloze({ text, filled }: { text: string; filled: boolean }) {
  return (
    <p className={prompt(text)}>
      {clozeParts(text).map((part, i) =>
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

/** How a multiple-choice answer is marked: the right answer in "Got it" teal, a wrong pick in pink. */
const CHOICE_INK = {
  right: { color: "var(--rate-3)", background: "var(--rate-3-soft)", borderColor: "var(--rate-3-line)" },
  wrong: { color: "var(--wrong)", background: "var(--wrong-soft)", borderColor: "var(--wrong-line)" },
};

/**
 * Multiple choice grades itself. Unlike "Forgot", a wrong pick really is wrong, so it's
 * marked in a soft pink rather than a rating ink, and still never a harsh red.
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
      <p className={prompt(card.prompt, true)}>{card.prompt}</p>
      <div className="mt-6 flex flex-col gap-2.5">
        {card.choices.map((choice, i) => {
          const ink = answered && choice === card.answer ? "right" : answered && choice === picked ? "wrong" : null;
          return (
            <button
              key={choice}
              type="button"
              disabled={answered}
              onClick={() => onPick(choice)}
              style={ink ? CHOICE_INK[ink] : undefined}
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
    // On a phone the choices on the card are the action; there's nothing to pin.
    if (picked === null) return <p className="text-center text-muted max-sm:hidden">Pick an answer, or press 1–4</p>;
    const rating = choiceRating(card, picked);
    const when = whenLabel(card.next[rating], now);
    return (
      // One line beside Continue: the colors on the answers already show which was right (D63).
      <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2">
        <p role="status" className="font-semibold" style={{ color: rating === 3 ? "var(--rate-3)" : "var(--wrong)" }}>
          {rating === 3 ? "Correct" : "Not quite"}
          <span className="font-normal text-muted">
            {" · "}
            {when === "see it again soon" ? "see it again soon" : `see it again ${when}`}
          </span>
          {rating !== 3 && <span className="sr-only">. The answer is: {answerText(card.answer)}.</span>}
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
        <Button size="lg" hint="Space" onClick={onReveal} className="max-sm:w-full">
          Show answer
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3 max-sm:gap-2">
      <p className="text-center text-muted max-sm:text-sm">How well did you remember it?</p>
      <div className="grid grid-cols-4 gap-1.5 sm:gap-2.5">
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
function ReportButton({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-controls="report-panel"
      className="flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-muted transition-colors duration-150 hover:bg-foreground/5 hover:text-foreground"
    >
      Report <Kbd>F</Kbd>
    </button>
  );
}

/** The reasons, opened below the card so they never cover what's on it. */
function ReportPanel({ onFlag, onCancel }: { onFlag: (reason: string) => void; onCancel: () => void }) {
  return (
    <section
      id="report-panel"
      aria-labelledby="report-heading"
      className="rise-in rounded-control border border-border bg-surface p-4 shadow-card"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="report-heading" className="font-semibold">
            What&apos;s wrong with this card?
          </h2>
          <p className="text-sm text-muted">It won&apos;t come up again.</p>
        </div>
        <Button variant="quiet" hint="Esc" onClick={onCancel} className="-mt-1 -mr-2">
          Cancel
        </Button>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        {FLAG_REASONS.map(({ reason, label, detail }) => (
          <button
            key={reason}
            type="button"
            onClick={() => onFlag(reason)}
            className="rounded-control border border-border-strong px-3 py-2.5 text-left transition-colors duration-150 hover:border-accent hover:bg-accent-soft/40"
          >
            <span className="block font-semibold">{label}</span>
            <span className="block text-sm text-muted">{detail}</span>
          </button>
        ))}
      </div>
    </section>
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
    <SourceBox title={`From ${source.book}`} where={where} className="after-flip">
      <div ref={box} className="relative max-h-[28rem] overflow-y-auto whitespace-pre-line">
        {before}
        {marked && <Highlight ref={mark}>{marked}</Highlight>}
        {after}
      </div>
    </SourceBox>
  );
}

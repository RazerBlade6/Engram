"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { Button, ButtonLink } from "@/components/ui/button";
import { IndexCard } from "@/components/ui/index-card";
import { Kbd } from "@/components/ui/kbd";
import { cx } from "@/lib/cx";

/**
 * Remembered in this browser only, so a new device shows the tour once more. Recording it on
 * the account needs the API (see docs/BACKEND_PENDING.md).
 */
const SEEN_KEY = "engram.welcomed";

export function tourSeen(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) !== null;
  } catch {
    // Storage blocked: don't show a tour that would come back on every visit.
    return true;
  }
}

function markSeen() {
  try {
    localStorage.setItem(SEEN_KEY, new Date().toISOString());
  } catch {}
}

type Step = {
  label: string;
  title: string;
  body: ReactNode;
  /** The link in the top bar to point at, if the step is about a page. */
  nav?: "/" | "/calendar" | "/ask";
};

const STEPS: Step[] = [
  {
    label: "Welcome",
    title: "Engram turns your course materials into practice.",
    body: "It makes flashcards from your textbooks and slides, and brings each one back just before you'd forget it. Here's a quick look around.",
  },
  {
    label: "Today",
    title: "What's due is waiting here",
    body: "Each day, Today shows how many cards are due and about how long they'll take. One button starts them.",
    nav: "/",
  },
  {
    label: "Your courses",
    title: "Mark chapters as your class covers them",
    body: "Open a course from Today and press “We've covered this” on a chapter. Its cards are made for you.",
  },
  {
    label: "Reviewing",
    title: "Turn the card, then say how it went",
    body: (
      <>
        Press <Kbd>Space</Kbd> to turn a card over, then <Kbd>1</Kbd> to <Kbd>4</Kbd> for how well you knew it. The page
        it came from is right beside it.
      </>
    ),
  },
  {
    label: "Calendar",
    title: "Keep your exams and deadlines in one place",
    body: "Add exams, quizzes and deadlines. The next ones show up on Today.",
    nav: "/calendar",
  },
  {
    label: "Ask",
    title: "Stuck? Ask in your own words",
    body: "Answers come from your materials, with a link to the exact page.",
    nav: "/ask",
  },
];

/** Where a student is when the tour ends, which decides its last card. */
export type Stage = "new" | "covering" | "due";

/** The last card always points at the one thing to do next. */
const FINALE: Record<Stage, Step> = {
  new: {
    label: "First step",
    title: "Start with a course",
    body: "Add one for each subject you're studying. Your textbook and slides go on its page.",
  },
  covering: {
    label: "Next step",
    title: "Mark what you've covered",
    body: "Open a course and mark the chapters your class has covered. Their cards will be waiting on Today.",
  },
  due: {
    label: "That's it",
    title: "Nothing to set up",
    body: "Study when it suits you. Skip a day and nothing is lost; Engram just picks up where you left off.",
  },
};

/**
 * A short walk through the app on a first visit: one card per page, with back, next and skip.
 * The card leaves the pile on Next, the way an answered card does in review.
 */
export function WelcomeTour({
  stage,
  onAddCourse,
  onDone,
}: {
  stage: Stage;
  /** Opens the form to add a course, for a student who has none yet. */
  onAddCourse: () => void;
  onDone: () => void;
}) {
  const steps = [...STEPS, FINALE[stage]];
  const [step, setStep] = useState(0);
  const [leaving, setLeaving] = useState<{ id: number; step: number } | null>(null);
  const leavingId = useRef(0);
  const primary = useRef<HTMLButtonElement & HTMLAnchorElement>(null);
  const last = step === steps.length - 1;

  const finish = useCallback(() => {
    markSeen();
    onDone();
  }, [onDone]);

  const go = useCallback(
    (to: number) => {
      if (to < 0 || to >= steps.length) return;
      // Forward deals the card off the pile; back simply brings the previous one up.
      if (to > step) {
        leavingId.current += 1;
        setLeaving({ id: leavingId.current, step });
      } else {
        setLeaving(null);
      }
      setStep(to);
    },
    [step, steps.length],
  );

  useEffect(() => {
    primary.current?.focus();
  }, [step]);

  // Point at the page's link in the top bar, lifted above the dimmed page.
  const nav = steps[step].nav;
  useEffect(() => {
    const root = document.documentElement;
    if (nav) root.dataset.tour = nav;
    else delete root.dataset.tour;
    return () => {
      delete root.dataset.tour;
    };
  }, [nav]);

  useEffect(() => {
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(event: KeyboardEvent) {
      if (event.key === "ArrowRight") go(step + 1);
      else if (event.key === "ArrowLeft") go(step - 1);
      else if (event.key === "Escape") finish();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [go, step, finish]);

  return (
    <div className="fade-in fixed inset-0 z-40 grid place-items-center overflow-y-auto bg-foreground/60 p-4 backdrop-blur-[2px]">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        aria-describedby="tour-body"
        className="w-full max-w-lg"
      >
        <div className="relative isolate">
          <div aria-hidden className="index-card-under -z-10" />
          <StepCard key={`step-${step}`} step={steps[step]} />
          {leaving && (
            <div
              key={`leaving-${leaving.id}`}
              aria-hidden
              inert
              className="card-leave absolute inset-x-0 top-0 z-10"
              onAnimationEnd={(e) => e.target === e.currentTarget && setLeaving(null)}
            >
              <StepCard step={steps[leaving.step]} />
            </div>
          )}
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          {!last && (
            // Plain, light text on the dimmed page: always there, never the obvious choice.
            <button
              type="button"
              onClick={finish}
              className="flex min-h-11 items-center gap-2 rounded-control px-3 font-semibold text-paper/90 transition-colors duration-150 hover:bg-paper/10 hover:text-paper"
            >
              Skip the tour <Kbd tone="inverse">Esc</Kbd>
            </button>
          )}
          <Dots step={step} count={steps.length} />
          <div className="ml-auto flex gap-2">
            {step > 0 && (
              <Button variant="secondary" onClick={() => go(step - 1)} hint="←">
                Back
              </Button>
            )}
            {!last ? (
              <Button ref={primary} onClick={() => go(step + 1)} hint="→">
                {step === 0 ? "Show me around" : "Next"}
              </Button>
            ) : stage === "due" ? (
              <ButtonLink ref={primary} href="/review" onClick={markSeen} size="lg">
                Start your first review
              </ButtonLink>
            ) : stage === "new" ? (
              <Button
                ref={primary}
                size="lg"
                onClick={() => {
                  finish();
                  onAddCourse();
                }}
              >
                Add your first course
              </Button>
            ) : (
              <Button ref={primary} onClick={finish} size="lg">
                Go to Today
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function StepCard({ step }: { step: Step }) {
  const { label, title, body } = step;
  return (
    <IndexCard label={label} pile={false}>
      <h2 id="tour-title" className="text-2xl font-bold text-balance">
        {title}
      </h2>
      <p id="tour-body" className="mt-3 font-read text-lg leading-relaxed">
        {body}
      </p>
    </IndexCard>
  );
}

function Dots({ step, count }: { step: number; count: number }) {
  return (
    <p className="flex items-center gap-1.5" aria-label={`Step ${step + 1} of ${count}`}>
      {Array.from({ length: count }, (_, i) => (
        <span
          key={i}
          aria-hidden
          className={cx("size-2 rounded-full transition-colors duration-200", i === step ? "bg-paper" : "bg-paper/35")}
        />
      ))}
    </p>
  );
}

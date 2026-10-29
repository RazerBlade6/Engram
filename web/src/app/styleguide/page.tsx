"use client";

import { useEffect, useState, type ReactNode } from "react";

import { AdminOnly } from "@/components/admin-only";
import { Toast, type ToastMessage } from "@/components/toast";
import { Button, ButtonLink } from "@/components/ui/button";
import { DateField } from "@/components/ui/date-field";
import { Drawer } from "@/components/ui/drawer";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Select } from "@/components/ui/field";
import { FlipCard } from "@/components/ui/flip-card";
import { IndexCard } from "@/components/ui/index-card";
import { Kbd } from "@/components/ui/kbd";
import { Notice } from "@/components/ui/notice";
import { ProgressBar } from "@/components/ui/progress";
import { RatingButton } from "@/components/ui/rating-button";
import { Row, RowList } from "@/components/ui/row-list";
import { Loading } from "@/components/ui/skeleton";
import { Highlight, SourceBox } from "@/components/ui/source-box";
import { RATINGS } from "@/lib/review";

/** Every token and component in one place, for reviewing the design system. Admins only. */
export default function StyleguidePage() {
  return (
    <AdminOnly>
      <Styleguide />
    </AdminOnly>
  );
}

const SURFACES = ["desk", "bar", "surface", "paper", "paper-under"];
const INK = [
  "foreground",
  "muted",
  "border",
  "border-strong",
  "accent",
  "accent-soft",
  "highlight",
  "highlight-edge",
  "card-rule",
  "card-line",
];
const STATUS = ["danger", "danger-soft", "success", "success-soft", "caution", "caution-soft", "caution-line"];
// The four rating inks; none is red, so "Forgot" never reads as failing.
const RATING_INKS = [1, 2, 3, 4].flatMap((n) => [`rate-${n}`, `rate-${n}-soft`]);
// A wrong multiple-choice pick, which really is wrong: soft pink, still not a harsh red.
const WRONG = ["wrong", "wrong-soft", "wrong-line"];
const COURSES = [1, 2, 3, 4, 5, 6].map((n) => `course-${n}`);
const WHEN = ["see it again soon", "tomorrow", "in 3 days", "in 8 days"];

function Styleguide() {
  const [flipped, setFlipped] = useState(false);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const [day, setDay] = useState("2026-11-13");
  const [drawer, setDrawer] = useState(false);

  // Space turns the sample card over, as it will in review.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== " " || (event.target instanceof HTMLElement && event.target.matches("input, select, button")))
        return;
      event.preventDefault();
      setFlipped((f) => !f);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <h1 className="text-3xl font-bold">Style guide</h1>
      <p className="mt-2 max-w-prose text-muted">
        The Desk design system: tokens in <code>globals.css</code>, components in <code>components/ui</code>. All course
        content below is made-up sample text.
      </p>

      <Section title="Color">
        <Swatches label="Surfaces, back to front" names={SURFACES} />
        <Swatches label="Text, lines and accent" names={INK} />
        <Swatches label="Status" names={STATUS} />
        <Swatches label="Rating inks" names={RATING_INKS} />
        <Swatches label="A wrong multiple-choice answer" names={WRONG} />
        <Swatches label="Courses" names={COURSES} />
      </Section>

      <Section title="Type">
        <div className="flex flex-col gap-3">
          <p className="text-3xl font-bold">Page title · Figtree bold</p>
          <p className="text-xl font-semibold">Section heading · Figtree semibold</p>
          <p className="text-lg">Body text · Figtree regular, at the larger base size</p>
          <p className="text-sm text-muted">Small print and secondary details · muted</p>
          <p className="mt-4 font-read text-2xl leading-snug">
            Which brain structure is most involved in turning new experiences into lasting memories?
          </p>
          <p className="text-sm text-muted">Card and source text · Literata, used only for what a student reads</p>
          <p className="mt-4 font-hand text-2xl font-medium text-muted">Introduction to Psychology</p>
          <p className="text-sm text-muted">Notes on a card, like its course · Caveat, a light handwritten touch</p>
        </div>
      </Section>

      <Section title="Buttons">
        <div className="flex flex-wrap items-center gap-4">
          <ButtonLink href="/styleguide" size="lg">
            Start review
          </ButtonLink>
          <Button size="lg" hint="Space">
            Show answer
          </Button>
          <Button variant="secondary">Add a course</Button>
          <Button variant="quiet">Cancel</Button>
          <Button disabled>Adding…</Button>
          <Button variant="danger">Delete</Button>
        </div>
        <p className="mt-3 text-sm text-muted">
          One primary button per screen. Danger is only for deleting, never the main action. Shortcuts show as keys:{" "}
          <Kbd>Space</Kbd> <Kbd>1</Kbd> <Kbd>F</Kbd>
        </p>
      </Section>

      <Section title="Fields">
        <div className="grid max-w-xl gap-5">
          <Field label="Course name" placeholder="e.g. Introduction to Psychology" />
          <Select label="Type" hint="What kind of date this is" defaultValue="quiz">
            <option value="exam">Exam</option>
            <option value="quiz">Quiz</option>
            <option value="deadline">Deadline</option>
          </Select>
          <div className="max-w-60">
            <DateField label="Date" value={day} onChange={setDay} />
          </div>
          <p className="text-sm text-muted">
            Dates are typed day/month/year and written out underneath (D54); the calendar button picks one by clicking.
          </p>
        </div>
      </Section>

      <Section title="Index card">
        <div className="grid gap-10 md:grid-cols-2">
          <IndexCard label="Due today">
            <p className="text-3xl font-bold">
              <span className="font-read text-5xl font-semibold text-accent">23</span> cards to review
            </p>
            <p className="mt-2 text-lg text-muted">About 8 minutes, from Introduction to Psychology and Biology 2e.</p>
            <ButtonLink href="/styleguide" size="lg" className="mt-5">
              Start review
            </ButtonLink>
          </IndexCard>
          <IndexCard label="Biology 2e" labelColor="var(--course-2)" ruled={false} pile={false}>
            <p className="text-lg">Unruled and on its own, for long or dense content.</p>
          </IndexCard>
        </div>
      </Section>

      <Section title="Card flip">
        <p className="mb-6 text-muted">
          The one generous animation. Press <Kbd>Space</Kbd> or the button. With reduced motion, the faces swap in
          place.
        </p>
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
          <div className="flex flex-col gap-6">
            <FlipCard
              flipped={flipped}
              front={
                <SampleCard>
                  <p className="font-read text-2xl leading-snug">
                    Which brain structure is most involved in turning new experiences into lasting memories?
                  </p>
                </SampleCard>
              }
              back={
                <SampleCard>
                  <p className="font-read text-lg leading-snug text-muted">
                    Which brain structure is most involved in turning new experiences into lasting memories?
                  </p>
                  <p className="mt-4 font-read text-2xl font-semibold">The hippocampus</p>
                </SampleCard>
              }
            />
            {flipped ? (
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                {RATINGS.map(({ rating, label }) => (
                  <RatingButton
                    key={rating}
                    rating={rating}
                    label={label}
                    when={WHEN[rating - 1]}
                    onClick={() => setFlipped(false)}
                  />
                ))}
              </div>
            ) : (
              <div className="flex justify-center">
                <Button size="lg" hint="Space" onClick={() => setFlipped(true)}>
                  Show answer
                </Button>
              </div>
            )}
          </div>
          <SourceBox
            title="From Introduction to Psychology"
            where="8.2 Parts of the Brain Involved with Memory · page 274"
            action={<a className="font-semibold text-accent underline">Open the page</a>}
          >
            … patients with damage to the <Highlight>hippocampus</Highlight> keep their older memories, but can no
            longer form new explicit ones …
          </SourceBox>
        </div>
      </Section>

      <Section title="Lists on the desk">
        <RowList className="max-w-xl">
          <Row className="flex items-center gap-3">
            <span className="size-2.5 rounded-full" style={{ background: "var(--course-1)" }} />
            <span className="flex-1">
              <b className="block">Quiz: Memory</b>
              <span className="text-sm text-muted">Introduction to Psychology</span>
            </span>
            <span className="text-right font-semibold tabular-nums">
              Tue 4 Nov <small className="block font-normal text-muted">in 6 days</small>
            </span>
          </Row>
          <Row className="flex items-center gap-3">
            <span className="size-2.5 rounded-full" style={{ background: "var(--course-2)" }} />
            <span className="flex-1">
              <b className="block">Midterm exam</b>
              <span className="text-sm text-muted">Biology 2e</span>
            </span>
            <span className="text-right font-semibold tabular-nums">
              Mon 17 Nov <small className="block font-normal text-muted">in 19 days</small>
            </span>
          </Row>
        </RowList>
      </Section>

      <Section title="Messages and progress">
        <div className="grid max-w-xl gap-4">
          <Notice>Reading your textbook… you can leave, it&apos;ll be ready when you&apos;re back.</Notice>
          <Notice tone="success">Chapter 8 is covered. Its cards are in your reviews.</Notice>
          <Notice tone="caution">
            <span className="font-semibold">Not from your Introduction to Psychology materials.</span> This answer comes
            from general knowledge, so check it against your course.
          </Notice>
          <p className="flex items-center gap-2 text-sm text-muted">
            {/* The pile a chapter shows while its cards are made (course page). */}
            <span aria-hidden className="making-cards relative inline-block h-3.5 w-5">
              <i />
              <i />
              <i />
            </span>
            Covered on 27 October · Making cards…
          </p>
          <Notice tone="error" action={<Button variant="secondary">Try again</Button>}>
            That upload stopped partway. Your file is safe.
          </Notice>
          <ProgressBar value={7} max={23} label="Cards reviewed" />
          <Button
            variant="secondary"
            className="justify-self-start"
            onClick={() =>
              setToast({
                id: Date.now(),
                text: "Thanks. That card is out of your reviews.",
                undo: () => {},
              })
            }
          >
            Show a toast
          </Button>
        </div>
      </Section>

      <Section title="Loading and empty">
        <div className="grid gap-8 md:grid-cols-2">
          <Loading label="Loading your courses" />
          <EmptyState title="No courses yet" action={<Button variant="secondary">Add a course</Button>}>
            Add one for each subject you&apos;re studying.
          </EmptyState>
        </div>
      </Section>

      <Section title="Drawer">
        <p className="mb-4 text-muted">
          A panel from the right, for a form beside a list (the admin page&apos;s invites). Esc or a click outside
          closes it.
        </p>
        <Button variant="secondary" onClick={() => setDrawer(true)}>
          Open a drawer
        </Button>
        {drawer && (
          <Drawer title="Invite people" onClose={() => setDrawer(false)}>
            <Field label="Email" type="email" placeholder="name@example.com" />
          </Drawer>
        )}
      </Section>

      <Toast key={toast?.id} toast={toast} onDone={() => setToast(null)} />
    </main>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-14 border-t border-border pt-6">
      <h2 className="mb-6 text-xl font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function Swatches({ label, names }: { label: string; names: string[] }) {
  return (
    <div className="mb-6">
      <p className="mb-2 text-sm font-semibold text-muted">{label}</p>
      <ul className="flex flex-wrap gap-4">
        {names.map((name) => (
          <li key={name} className="w-28">
            <span
              className="block h-14 rounded-control border border-foreground/10"
              style={{ background: `var(--${name})` }}
            />
            <code className="mt-1 block text-xs text-muted">{name}</code>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SampleCard({ children }: { children: ReactNode }) {
  return (
    <IndexCard
      label="Introduction to Psychology"
      labelColor="var(--course-1)"
      corner={<button className="rounded-md px-2 py-0.5 text-sm text-muted hover:bg-foreground/5">Report</button>}
    >
      <div className="min-h-40">{children}</div>
    </IndexCard>
  );
}

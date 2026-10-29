"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { SourceViewer } from "@/components/source-viewer";
import { Toast, type ToastMessage } from "@/components/toast";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { CONTROL } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { Loading, Skeleton } from "@/components/ui/skeleton";
import { api, apiFetch } from "@/lib/api";
import {
  applyEvent,
  emptyAnswer,
  historyOf,
  parseEvents,
  quoteFor,
  sourceLabel,
  type AnswerMessage,
  type ChatSource,
  type Message,
} from "@/lib/chat";
import type { CourseSummary } from "@/lib/courses";
import { cx } from "@/lib/cx";
import { useProfile } from "@/lib/profile";
import { msSince, track } from "@/lib/usage";

/** Each course's conversation lasts as long as the browser tab; nothing is kept on the server. */
const storageKey = (course: string) => `engram.ask.${course}`;

function load(course: string): Message[] {
  try {
    const saved = sessionStorage.getItem(storageKey(course));
    // An answer cut off by leaving the page can't resume.
    return saved ? (JSON.parse(saved) as Message[]).filter((m) => m.role === "user" || m.status === "done") : [];
  } catch {
    return [];
  }
}

function save(course: string, messages: Message[]) {
  try {
    sessionStorage.setItem(storageKey(course), JSON.stringify(messages));
  } catch {}
}

export function AskView() {
  const profile = useProfile();
  const requested = useSearchParams().get("course");
  const [courses, setCourses] = useState<CourseSummary[] | null>(null);

  useEffect(() => {
    if (profile) api<CourseSummary[]>("/courses").then(setCourses);
  }, [profile]);

  if (!profile) return null;
  if (!courses) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <Loading label="Loading your courses" lines={1} />
      </main>
    );
  }
  const course = courses.find((c) => c.id === requested) ?? courses[0];
  if (!course) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1 className="text-3xl font-bold">Ask a question</h1>
        <div className="mt-8">
          <EmptyState title="No courses yet">
            Once you&apos;ve added a course and its materials on Today, you can ask about them here.
          </EmptyState>
        </div>
      </main>
    );
  }
  return <Conversation key={course.id} course={course} courses={courses} />;
}

function Conversation({ course, courses }: { course: CourseSummary; courses: CourseSummary[] }) {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>(() => load(course.id));
  const [question, setQuestion] = useState("");
  const [open, setOpen] = useState<{ chunkId: string; quote: string | null } | null>(null);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const hideToast = useCallback(() => setToast(null), []);
  const input = useRef<HTMLInputElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const busy = messages.at(-1)?.role === "assistant" && (messages.at(-1) as AnswerMessage).status === "streaming";

  useEffect(() => {
    if (!busy) save(course.id, messages);
  }, [course, messages, busy]);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  const ask = useCallback(
    async (text: string) => {
      const q = text.trim();
      if (!q || busy) return;
      const history = historyOf(messages);
      const started = performance.now();
      // For the usage log: how the answer went, never what it said.
      const outcome = { firstText: null as number | null, grounded: false, outside: false, sources: 0, failed: false };
      setQuestion("");
      setMessages((ms) => [...ms, { role: "user", text: q }, emptyAnswer()]);
      const update = (change: (a: AnswerMessage) => AnswerMessage) =>
        setMessages((ms) => [...ms.slice(0, -1), change(ms.at(-1) as AnswerMessage)]);
      try {
        const response = await apiFetch(`/courses/${course.id}/ask`, {
          method: "POST",
          body: JSON.stringify({ question: q, history }),
        });
        const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          const { events, rest } = parseEvents(buffer + value);
          buffer = rest;
          for (const e of events) {
            if (e.event === "text" && outcome.firstText === null) outcome.firstText = msSince(started);
            else if (e.event === "source") outcome.sources += 1;
            else if (e.event === "outside") outcome.outside = true;
            else if (e.event === "done") outcome.grounded = e.data.grounded;
            else if (e.event === "error") outcome.failed = true;
          }
          if (events.length) update((a) => events.reduce(applyEvent, a));
        }
        update((a) => (a.status === "streaming" ? { ...a, status: "done" } : a));
      } catch {
        outcome.failed = true;
        update((a) => ({ ...a, status: "error", error: "That question couldn't be answered. Please try again." }));
      }
      track({
        name: "chat_question",
        course_id: course.id,
        first_text_ms: outcome.firstText,
        total_ms: msSince(started),
        grounded: outcome.grounded,
        outside: outcome.outside,
        sources: outcome.sources,
        follow_up: history.length > 0,
        failed: outcome.failed,
      });
      input.current?.focus();
    },
    [course, busy, messages],
  );

  // Clears the conversation from the screen (and this tab's copy of it), with a moment to undo.
  const clear = useCallback(() => {
    const cleared = messages;
    setMessages([]);
    setToast({ id: Date.now(), text: "Chat cleared.", undo: () => setMessages(cleared) });
    input.current?.focus();
  }, [messages]);

  // A failed answer is taken away and its question put back, ready to send again.
  const askAgain = useCallback(() => {
    const last = messages.at(-2);
    if (last?.role !== "user") return;
    setMessages((ms) => ms.slice(0, -2));
    setQuestion(last.text);
    input.current?.focus();
  }, [messages]);

  return (
    <main className="mx-auto flex min-h-[calc(100dvh-4rem)] max-w-3xl flex-col px-6 pt-10">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">Ask a question</h1>
        {messages.length > 0 && (
          <Button variant="secondary" disabled={busy} onClick={clear}>
            Clear chat
          </Button>
        )}
      </div>
      {courses.length > 1 && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-muted">Answering from</span>
          {courses.map((c) => (
            <button
              key={c.id}
              type="button"
              aria-pressed={c.id === course.id}
              disabled={busy}
              onClick={() => router.replace(`/ask?course=${c.id}`)}
              className={cx(
                "rounded-full border px-3.5 py-1 transition-colors duration-150 disabled:opacity-60",
                c.id === course.id
                  ? "border-accent bg-accent-soft font-semibold text-accent"
                  : "border-border-strong bg-surface hover:border-accent",
              )}
            >
              {c.title}
            </button>
          ))}
        </div>
      )}
      {messages.length === 0 && (
        <p className="mt-6 max-w-prose text-lg text-muted">
          Stuck on something in {course.title}? Ask in your own words. Answers come from your textbook, slides and
          notes, with a link to the exact page.
        </p>
      )}

      <div className="mt-8 flex flex-1 flex-col gap-6" aria-live="polite">
        {messages.map((m, i) =>
          m.role === "user" ? (
            <p key={i} className="rise-in max-w-[80%] self-end rounded-control rounded-br-sm bg-accent-soft px-4 py-3">
              {m.text}
            </p>
          ) : (
            <Answer
              key={i}
              answer={m}
              course={course.title}
              onOpen={(chunkId, quote) => setOpen({ chunkId, quote })}
              onAskAgain={i === messages.length - 1 ? askAgain : undefined}
            />
          ),
        )}
        <div ref={end} />
      </div>

      {/* Stays at the bottom of the screen; the desk fades in behind it as answers scroll under. */}
      <form
        className="sticky bottom-0 mt-6 flex gap-3 bg-linear-to-t from-desk from-75% to-transparent pt-6 pb-5"
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
      >
        <label htmlFor="ask-input" className="sr-only">
          Your question
        </label>
        <input
          ref={input}
          id="ask-input"
          type="text"
          autoComplete="off"
          autoFocus
          maxLength={2000}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={`Ask about ${course.title}…`}
          className={cx(CONTROL, "min-w-0 flex-1 text-lg shadow-card")}
        />
        <Button type="submit" size="lg" disabled={busy || !question.trim()}>
          Ask
        </Button>
      </form>

      {open && <SourceViewer chunkId={open.chunkId} quote={open.quote} origin="chat" onClose={() => setOpen(null)} />}
      {/* Above the question box. */}
      <Toast key={toast?.id} toast={toast} onDone={hideToast} above="bottom-28" />
    </main>
  );
}

/** An answer is a sheet of notes on the desk: reading text, with its sources at the foot. */
function Answer({
  answer,
  course,
  onOpen,
  onAskAgain,
}: {
  answer: AnswerMessage;
  course: string;
  onOpen: (chunkId: string, quote: string | null) => void;
  /** Only for the latest answer, if it failed. */
  onAskAgain?: () => void;
}) {
  const byNumber = new Map(answer.sources.map((s) => [s.number, s]));
  const open = (s: ChatSource, quote?: string) => onOpen(s.chunk_id, quote ?? quoteFor(answer, s.number));
  const waiting = answer.status === "streaming" && !answer.segments.some((s) => s.text);

  if (answer.status === "error" && !answer.segments.length) {
    return (
      <Notice
        tone="error"
        action={
          onAskAgain && (
            <Button variant="secondary" onClick={onAskAgain}>
              Ask again
            </Button>
          )
        }
      >
        {answer.error}
      </Notice>
    );
  }

  return (
    <article className="rise-in flex flex-col gap-4 rounded-card bg-paper px-6 py-5 shadow-card sm:px-8 sm:py-6">
      {answer.outside && (
        <Notice tone="caution">
          <span className="font-semibold">Not from your {course} materials.</span> This answer comes from general
          knowledge, so check it against your course.
        </Notice>
      )}
      {waiting && (
        <div role="status" className="flex flex-col gap-3">
          <p className="text-muted">Looking through your materials…</p>
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      )}
      {answer.segments.length > 0 && (
        <p className="font-read text-lg leading-relaxed whitespace-pre-line">
          {answer.segments.map((s) => (
            <span key={s.block}>
              {s.text}
              {s.cites.map((c) => {
                const source = byNumber.get(c.source);
                return (
                  source && (
                    <button
                      key={c.source}
                      type="button"
                      onClick={() => open(source, c.quote)}
                      aria-label={`Source ${c.source}: ${sourceLabel(source)}`}
                      className="mx-0.5 inline-grid h-5 min-w-5 place-items-center rounded-sm bg-accent-soft px-1 align-[3px] font-sans text-xs font-bold text-accent transition-colors duration-150 hover:bg-accent hover:text-on-accent"
                    >
                      {c.source}
                    </button>
                  )
                );
              })}
            </span>
          ))}
        </p>
      )}
      {answer.sources.length > 0 && (
        <footer className="border-t border-dashed border-border pt-3">
          <p className="text-sm font-semibold text-muted">Sources</p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {answer.sources.map((s) => (
              <li key={s.number}>
                <button
                  type="button"
                  onClick={() => open(s)}
                  className="flex w-full items-baseline gap-2.5 rounded-r-md border-l-2 border-accent px-3 py-1 text-left transition-colors duration-150 hover:bg-accent-soft/50"
                >
                  <b className="text-sm text-accent">{s.number}</b>
                  <span>{sourceLabel(s)}</span>
                  <span className="ml-auto shrink-0 text-sm text-accent">Open</span>
                </button>
              </li>
            ))}
          </ul>
        </footer>
      )}
      {answer.status === "error" && (
        <Notice
          tone="error"
          action={
            onAskAgain && (
              <Button variant="secondary" onClick={onAskAgain}>
                Ask again
              </Button>
            )
          }
        >
          {answer.error}
        </Notice>
      )}
    </article>
  );
}

"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { SourceViewer } from "@/components/source-viewer";
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
import { useProfile } from "@/lib/profile";

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

  if (!profile || !courses) return null;
  const course = courses.find((c) => c.id === requested) ?? courses[0];
  if (!course) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <BackLink />
        <h1 className="mt-4 text-3xl font-semibold">Ask a question</h1>
        <p className="mt-3 text-muted">Once you have a course with materials, you can ask about it here.</p>
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
          if (events.length) update((a) => events.reduce(applyEvent, a));
        }
        update((a) => (a.status === "streaming" ? { ...a, status: "done" } : a));
      } catch {
        update((a) => ({ ...a, status: "error", error: "That question couldn't be answered. Please try again." }));
      }
      input.current?.focus();
    },
    [course, busy, messages],
  );

  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col px-6 pt-12">
      <BackLink />
      <h1 className="mt-4 text-3xl font-semibold">Ask a question</h1>
      {courses.length > 1 && (
        <div className="mt-4 flex flex-wrap items-center gap-2 text-muted">
          <span>Answering from</span>
          {courses.map((c) => (
            <button
              key={c.id}
              type="button"
              aria-pressed={c.id === course.id}
              disabled={busy}
              onClick={() => router.replace(`/ask?course=${c.id}`)}
              className={`rounded-full border px-3 py-1 ${
                c.id === course.id ? "border-accent bg-accent font-semibold text-white" : "border-border bg-white text-foreground"
              }`}
            >
              {c.title}
            </button>
          ))}
        </div>
      )}
      {messages.length === 0 && (
        <p className="mt-6 text-lg text-muted">
          Ask anything about {course.title}. Answers come from your textbook, slides and notes, with links to the exact
          page.
        </p>
      )}

      <div className="mt-8 flex flex-1 flex-col gap-6" aria-live="polite">
        {messages.map((m, i) =>
          m.role === "user" ? (
            <p key={i} className="max-w-[80%] self-end rounded-2xl rounded-br-sm bg-accent/10 px-4 py-3">
              {m.text}
            </p>
          ) : (
            <Answer key={i} answer={m} course={course.title} onOpen={(chunkId, quote) => setOpen({ chunkId, quote })} />
          ),
        )}
        <div ref={end} />
      </div>

      <form
        className="sticky bottom-0 mt-6 flex gap-3 bg-background py-4"
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
          className="min-w-0 flex-1 rounded-lg border border-border bg-white px-4 py-3 text-lg"
        />
        <button
          type="submit"
          disabled={busy || !question.trim()}
          className="rounded-lg bg-accent px-6 py-3 text-lg font-medium text-white hover:bg-accent-strong disabled:opacity-50"
        >
          Ask
        </button>
      </form>

      {open && <SourceViewer chunkId={open.chunkId} quote={open.quote} onClose={() => setOpen(null)} />}
    </main>
  );
}

function BackLink() {
  return (
    <Link href="/" className="text-muted underline hover:text-foreground">
      Back to Today
    </Link>
  );
}

function Answer({
  answer,
  course,
  onOpen,
}: {
  answer: AnswerMessage;
  course: string;
  onOpen: (chunkId: string, quote: string | null) => void;
}) {
  const byNumber = new Map(answer.sources.map((s) => [s.number, s]));
  const open = (s: ChatSource, quote?: string) => onOpen(s.chunk_id, quote ?? quoteFor(answer, s.number));
  const waiting = answer.status === "streaming" && !answer.segments.some((s) => s.text);

  return (
    <div className="flex flex-col gap-3">
      {answer.outside && (
        <p className="rounded-lg border border-border bg-white px-4 py-3">
          <span className="font-semibold">Not from your {course} materials.</span> This answer comes from general
          knowledge, so check it against your course.
        </p>
      )}
      {waiting && (
        <p className="text-muted" role="status">
          Looking through your materials…
        </p>
      )}
      {answer.segments.length > 0 && (
        <p className="text-lg leading-relaxed whitespace-pre-line">
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
                      className="mx-0.5 inline-grid h-6 min-w-6 place-items-center rounded-md border border-accent bg-accent/10 px-1 align-[2px] text-sm font-bold text-accent hover:bg-accent hover:text-white"
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
        <div className="flex flex-wrap gap-2">
          {answer.sources.map((s) => (
            <button
              key={s.number}
              type="button"
              onClick={() => open(s)}
              className="flex items-center gap-2 rounded-lg border border-border bg-white px-3 py-1.5 text-left hover:border-accent"
            >
              <b className="text-accent">{s.number}</b>
              {sourceLabel(s)}
            </button>
          ))}
        </div>
      )}
      {answer.status === "error" && <p className="text-danger">{answer.error}</p>}
    </div>
  );
}

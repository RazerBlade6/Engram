/** Types and helpers for asking questions (see backend `api/routes/chat.py`). */

export type ChatSource = {
  number: number;
  chunk_id: string;
  material_id: string;
  book: string;
  heading_path: string[];
  page: number | null;
};

/** A stretch of the answer, with the sources it cites (and the words it quotes from each). */
export type Segment = { block: number; text: string; cites: { source: number; quote: string }[] };

export type UserMessage = { role: "user"; text: string };
export type AnswerMessage = {
  role: "assistant";
  segments: Segment[];
  sources: ChatSource[];
  /** Not from the course materials: shown with a label. */
  outside: boolean;
  status: "streaming" | "done" | "error";
  error?: string;
};
export type Message = UserMessage | AnswerMessage;
export type Turn = { role: "user" | "assistant"; text: string };

export type ChatEvent =
  | { event: "text"; data: { block: number; text: string } }
  | { event: "source"; data: ChatSource }
  | { event: "cite"; data: { block: number; source: number; quote: string } }
  | { event: "outside"; data: Record<string, never> }
  | { event: "done"; data: { grounded: boolean } }
  | { event: "error"; data: { message: string } };

/** Earlier turns sent with each question, so follow-ups make sense. */
const HISTORY_TURNS = 6;

/** Splits server-sent events out of `buffer`; `rest` is an incomplete event to keep for later. */
export function parseEvents(buffer: string): { events: ChatEvent[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  const events: ChatEvent[] = [];
  for (const part of parts) {
    let name = "";
    let data = "";
    for (const line of part.split("\n")) {
      if (line.startsWith("event: ")) name = line.slice(7);
      else if (line.startsWith("data: ")) data += line.slice(6);
    }
    if (name && data) events.push({ event: name, data: JSON.parse(data) } as ChatEvent);
  }
  return { events, rest };
}

export function emptyAnswer(): AnswerMessage {
  return { role: "assistant", segments: [], sources: [], outside: false, status: "streaming" };
}

/** The answer with one more event applied. */
export function applyEvent(answer: AnswerMessage, e: ChatEvent): AnswerMessage {
  const segment = (block: number, change: (s: Segment) => Segment): Segment[] => {
    const found = answer.segments.some((s) => s.block === block);
    const segments = found ? answer.segments : [...answer.segments, { block, text: "", cites: [] }];
    return segments.map((s) => (s.block === block ? change(s) : s));
  };
  switch (e.event) {
    case "text":
      return { ...answer, segments: segment(e.data.block, (s) => ({ ...s, text: s.text + e.data.text })) };
    case "cite": {
      const { source, quote } = e.data;
      return {
        ...answer,
        segments: segment(e.data.block, (s) =>
          s.cites.some((c) => c.source === source) ? s : { ...s, cites: [...s.cites, { source, quote }] },
        ),
      };
    }
    case "source":
      return { ...answer, sources: [...answer.sources, e.data] };
    case "outside":
      return { ...answer, outside: true };
    case "done":
      return { ...answer, status: "done", outside: answer.outside || !e.data.grounded };
    case "error":
      return { ...answer, status: "error", error: e.data.message };
  }
}

export function answerText(answer: AnswerMessage): string {
  return answer.segments.map((s) => s.text).join("");
}

/** The recent conversation as the API expects it. Unfinished answers are left out. */
export function historyOf(messages: Message[]): Turn[] {
  const turns = messages.flatMap((m): Turn[] =>
    m.role === "user" ? [{ role: m.role, text: m.text }] : m.status === "done" ? [{ role: m.role, text: answerText(m) }] : [],
  );
  return turns.slice(-HISTORY_TURNS);
}

/** The first words the answer quotes from a source, to highlight when it's opened. */
export function quoteFor(answer: AnswerMessage, source: number): string | null {
  for (const s of answer.segments) {
    const cite = s.cites.find((c) => c.source === source);
    if (cite) return cite.quote;
  }
  return null;
}

/** Where `quote` sits in `passage`, allowing for differences in spacing and punctuation. */
export function findQuote(passage: string, quote: string): [number, number] | null {
  const words = quote.match(/[\p{L}\p{N}_]+/gu);
  if (!words) return null;
  const escaped = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const match = new RegExp(escaped.join("[^\\p{L}\\p{N}_]+"), "iu").exec(passage);
  return match ? [match.index, match.index + match[0].length] : null;
}

export function sourceLabel(source: { book: string; heading_path: string[]; page: number | null }): string {
  return [source.book, source.page !== null ? `p. ${source.page}` : source.heading_path.at(-1)]
    .filter(Boolean)
    .join(" · ");
}

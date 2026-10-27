import { describe, expect, it } from "vitest";

import {
  applyEvent,
  emptyAnswer,
  findQuote,
  historyOf,
  parseEvents,
  quoteFor,
  type AnswerMessage,
  type ChatEvent,
  type Message,
} from "./chat";

const source = { number: 1, chunk_id: "c", material_id: "m", book: "Bio", heading_path: ["Cells"], page: 4 };

describe("parseEvents", () => {
  it("splits complete events and keeps the incomplete rest", () => {
    const { events, rest } = parseEvents(
      'event: text\ndata: {"block": 0, "text": "Hi"}\n\nevent: done\ndata: {"grounded": true}\n\nevent: te',
    );
    expect(events).toEqual([
      { event: "text", data: { block: 0, text: "Hi" } },
      { event: "done", data: { grounded: true } },
    ]);
    expect(rest).toBe("event: te");
  });
});

describe("applyEvent", () => {
  const play = (events: ChatEvent[]): AnswerMessage => events.reduce(applyEvent, emptyAnswer());

  it("groups text by block and attaches each block's citations, even when they come first", () => {
    const answer = play([
      { event: "text", data: { block: 0, text: "Myelin " } },
      { event: "text", data: { block: 0, text: "insulates. " } },
      { event: "source", data: source },
      { event: "cite", data: { block: 1, source: 1, quote: "a fatty sheath" } },
      { event: "text", data: { block: 1, text: "It is fatty." } },
      { event: "cite", data: { block: 1, source: 1, quote: "again" } },
      { event: "done", data: { grounded: true } },
    ]);
    expect(answer.segments).toEqual([
      { block: 0, text: "Myelin insulates. ", cites: [] },
      { block: 1, text: "It is fatty.", cites: [{ source: 1, quote: "a fatty sheath" }] },
    ]);
    expect(answer).toMatchObject({ status: "done", outside: false, sources: [source] });
    expect(quoteFor(answer, 1)).toBe("a fatty sheath");
  });

  it("labels an answer outside the materials, or one that cites nothing", () => {
    expect(play([{ event: "outside", data: {} }]).outside).toBe(true);
    expect(play([{ event: "done", data: { grounded: false } }]).outside).toBe(true);
  });
});

describe("historyOf", () => {
  it("sends recent finished turns as text", () => {
    const done = applyEvent(applyEvent(emptyAnswer(), { event: "text", data: { block: 0, text: "A1" } }), {
      event: "done",
      data: { grounded: true },
    });
    const messages: Message[] = [{ role: "user", text: "Q1" }, done, { role: "user", text: "Q2" }, emptyAnswer()];
    expect(historyOf(messages)).toEqual([
      { role: "user", text: "Q1" },
      { role: "assistant", text: "A1" },
      { role: "user", text: "Q2" },
    ]);
  });
});

describe("findQuote", () => {
  it("finds the quote despite line breaks and punctuation", () => {
    const passage = "Glial cells form\na fatty substance — the myelin sheath, which coats the axon.";
    const span = findQuote(passage, "a fatty substance, the myelin sheath");
    expect(span && passage.slice(...span)).toBe("a fatty substance — the myelin sheath");
    expect(findQuote(passage, "nodes of Ranvier")).toBeNull();
  });
});

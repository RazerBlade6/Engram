"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { clozeParts, KIND_LABEL, sourceLabel, type Card } from "@/lib/cards";

/** A chapter's cards, answers shown, for looking over what was made. Reviewing happens
 * elsewhere; this is only a list. */
export function CardList({ sectionId }: { sectionId: string }) {
  const [cards, setCards] = useState<Card[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api<Card[]>(`/sections/${sectionId}/cards`)
      .then(setCards)
      .catch(() => setFailed(true));
  }, [sectionId]);

  if (failed) return <p className="mt-4 text-danger">The cards couldn&apos;t be loaded. Please try again.</p>;
  if (!cards) return <p className="mt-4 text-muted">Loading the cards…</p>;

  return (
    <ol className="mt-4 space-y-3 sm:ml-12">
      {cards.map((card) => (
        <li key={card.id} className="rounded-lg border border-border bg-background px-4 py-3">
          <div className="text-xs font-semibold tracking-wide text-muted uppercase">{KIND_LABEL[card.kind]}</div>
          <CardBody card={card} />
          {card.sources[0] && <p className="mt-2 text-sm text-muted">From {sourceLabel(card.sources[0])}</p>}
        </li>
      ))}
    </ol>
  );
}

function CardBody({ card }: { card: Card }) {
  if (card.kind === "cloze") {
    return (
      <p className="mt-1">
        {clozeParts(card.prompt).map((part, i) =>
          part.hidden ? (
            <mark key={i} className="rounded bg-accent/15 px-1 font-semibold text-foreground">
              {part.text}
            </mark>
          ) : (
            <span key={i}>{part.text}</span>
          ),
        )}
      </p>
    );
  }
  return (
    <>
      <p className="mt-1 font-medium">{card.prompt}</p>
      {card.kind === "mcq" ? (
        <ul className="mt-2 space-y-1">
          {card.choices.map((choice) => (
            <li key={choice} className={choice === card.answer ? "font-semibold text-success" : "text-muted"}>
              {choice === card.answer ? "✓ " : "• "}
              {choice}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-muted">{card.answer}</p>
      )}
    </>
  );
}

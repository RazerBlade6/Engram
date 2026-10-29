"use client";

import { useEffect, useState } from "react";

import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Highlight } from "@/components/ui/source-box";
import { api } from "@/lib/api";
import { clozeParts, KIND_LABEL, sourceLabel, type Card } from "@/lib/cards";

/** A chapter's cards, answers shown, for looking over what was made. Reviewing happens
 * elsewhere; this is only a list, each card a small one on the page. */
export function CardList({ sectionId }: { sectionId: string }) {
  const [cards, setCards] = useState<Card[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api<Card[]>(`/sections/${sectionId}/cards`)
      .then(setCards)
      .catch(() => setFailed(true));
  }, [sectionId]);

  if (failed) {
    return (
      <div className="mt-4 sm:ml-12">
        <Notice tone="error">The cards couldn&apos;t be loaded. Close and open them again.</Notice>
      </div>
    );
  }
  if (!cards) {
    return (
      <div role="status" aria-label="Loading the cards" className="mt-4 grid gap-3 sm:ml-12 md:grid-cols-2">
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
      </div>
    );
  }

  return (
    <ol className="rise-in mt-4 grid gap-3 sm:ml-12 md:grid-cols-2">
      {cards.map((card) => (
        <li key={card.id} className="rounded-card border border-border/70 bg-paper px-4 py-3 shadow-card">
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
      <p className="mt-1 font-read">
        {clozeParts(card.prompt).map((part, i) =>
          part.hidden ? <Highlight key={i}>{part.text}</Highlight> : <span key={i}>{part.text}</span>,
        )}
      </p>
    );
  }
  return (
    <>
      <p className="mt-1 font-read font-semibold">{card.prompt}</p>
      {card.kind === "mcq" ? (
        <ul className="mt-2 space-y-1 border-t border-dotted border-border pt-2">
          {card.choices.map((choice) => (
            <li
              key={choice}
              className={choice === card.answer ? "font-semibold" : "text-muted"}
              style={choice === card.answer ? { color: "var(--rate-3)" } : undefined}
            >
              {choice === card.answer ? "✓ " : "• "}
              {choice}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 border-t border-dotted border-border pt-2 font-read text-muted">{card.answer}</p>
      )}
    </>
  );
}

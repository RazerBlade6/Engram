"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Highlight } from "@/components/ui/source-box";
import { api } from "@/lib/api";
import { clozeParts, KIND_LABEL, sourceLabel, type Card } from "@/lib/cards";

/** Shown under the chapter; the rest open in a sheet in front of the page. */
const PREVIEW = 10;

/** A chapter's cards, answers shown, for looking over what was made. Reviewing happens
 * elsewhere; this is only a list, each card a small one on the page. */
export function CardList({ sectionId, chapter }: { sectionId: string; chapter: string }) {
  const [cards, setCards] = useState<Card[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [all, setAll] = useState(false);

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
    <div className="rise-in mt-4 sm:ml-12">
      <Cards cards={cards.slice(0, PREVIEW)} />
      {cards.length > PREVIEW && (
        <Button variant="secondary" onClick={() => setAll(true)} className="mt-3">
          See all {cards.length} cards
        </Button>
      )}
      {all && <AllCards chapter={chapter} cards={cards} onClose={() => setAll(false)} />}
    </div>
  );
}

function Cards({ cards }: { cards: Card[] }) {
  return (
    <ol className="grid gap-3 md:grid-cols-2">
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

/** Every card in a chapter, in a sheet in front of the page that scrolls on its own. */
function AllCards({ chapter, cards, onClose }: { chapter: string; cards: Card[]; onClose: () => void }) {
  const close = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    // The page behind stays put while the sheet scrolls.
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [onClose]);

  return (
    <div className="fade-in fixed inset-0 z-40 flex justify-center bg-foreground/40 p-4 sm:p-8" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="all-cards-title"
        className="rise-in flex max-h-full w-full max-w-4xl flex-col overflow-hidden rounded-control bg-desk shadow-lifted"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4 border-b border-border bg-bar px-6 py-4">
          <div>
            <h2 id="all-cards-title" className="text-xl font-semibold">
              {chapter}
            </h2>
            <p className="text-sm text-muted">{cards.length} cards</p>
          </div>
          <Button ref={close} variant="secondary" hint="Esc" onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="overflow-y-auto p-6">
          <Cards cards={cards} />
        </div>
      </div>
    </div>
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
